// Ações do app: navegação, carga de dados, mutações otimistas com fila offline e atualização periódica.
import { api, ApiError, isNetworkError } from "./lib/api.js";
import { cacheGet, cacheSet, prefs } from "./lib/cache.js";
import { uid } from "./lib/ids.js";
import { enqueue, onDrain, onMutationError, onSyncChange, pendingFor, hasPending, startQueue } from "./lib/queue.js";
import { normalizeTask, recomputeGoals, isDone, orderedSteps } from "./lib/rules.js";
import { normalizeEntry } from "./lib/calendar.js";
import { getState, setState } from "./lib/store.js";
import { addDays, diffDays, plural, todayISO } from "./lib/format.js";

const POLL_MS = 10_000; // RNF19: alterações de outras contas visíveis em até 30 s
let lastSeq = 0;
let pollTimer = null;
let refreshTimers = {};

// ---------------------------------------------------------------------------------------------
// Toasts (RNF10) e diálogos
// ---------------------------------------------------------------------------------------------

export function toast(text, kind = "success", options = {}) {
  const id = uid();
  setState((s) => ({ toasts: [...s.toasts, { id, text, kind, action: options.action }] }));
  setTimeout(() => dismissToast(id), options.duration || (kind === "error" ? 6000 : 3500));
  return id;
}

export function dismissToast(id) {
  setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
}

export function openModal(kind, props = {}) {
  setState({ modal: { kind, props, key: uid() } });
}

export function closeModal() {
  setState({ modal: null });
}

/** Confirmação para ações irreversíveis (RF03, RF27, RF31). Resolve true/false. */
export function confirmDialog({ title, text, confirmLabel = "Confirmar", danger = false }) {
  return new Promise((resolve) => {
    openModal("confirm", {
      title,
      text,
      confirmLabel,
      danger,
      onResult: (ok) => {
        closeModal();
        resolve(ok);
      },
    });
  });
}

// ---------------------------------------------------------------------------------------------
// Navegação por hash
// ---------------------------------------------------------------------------------------------

export function parseHash(hash = location.hash) {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const params = Object.fromEntries(new URLSearchParams(query));
  const [name = "", a, b] = parts;
  switch (name) {
    case "hoje":
    case "daily":
    case "listas":
    case "tarefas":
    case "calendario":
    case "metas":
    case "desempenho":
    case "equipe":
    case "conta":
      if (name === "metas" && a) return { name: "meta", params: { goalId: a, ...params } };
      if (name === "equipe" && a) return { name: "membro", params: { accountId: a, tab: b || "tarefas", ...params } };
      return { name, params };
    case "tarefa":
      return { name: "tarefa", params: { taskId: a, ...params } };
    default:
      return { name: "", params };
  }
}

export function navigate(path) {
  const target = path.startsWith("#") ? path : `#/${path.replace(/^\//, "")}`;
  if (location.hash === target) applyRoute();
  else location.hash = target;
}

export function homeRoute(account) {
  return account?.role === "gestor" ? "equipe" : "hoje"; // RN34
}

function applyRoute() {
  const route = parseHash();
  const s = getState();
  if (route.name === "tarefa" && route.params.taskId) {
    history.replaceState(null, "", "#/tarefas");
    setState({ route: { name: "tarefas", params: {} }, drawer: { taskId: route.params.taskId } });
    return;
  }
  if (!route.name) {
    const me = s.accounts?.find((a) => a.id === s.meId);
    history.replaceState(null, "", `#/${homeRoute(me)}`);
    setState({ route: { name: homeRoute(me), params: {} } });
    return;
  }
  const previous = getState().route;
  setState({ route, panel: null });
  if (route.name === "membro") ensureBoard(route.params.accountId);
  // Nova tela começa no topo (instantâneo: a rolagem suave seria interrompida pela nova renderização)
  if (previous.name !== route.name || previous.params?.accountId !== route.params?.accountId) {
    setTimeout(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }), 0);
  }
}

// ---------------------------------------------------------------------------------------------
// Carga de dados
// ---------------------------------------------------------------------------------------------

export async function loadMeta() {
  try {
    const meta = await api.get("/api/meta");
    setState({ meta });
    cacheSet("meta", meta);
  } catch {
    const cached = await cacheGet("meta");
    if (cached) setState({ meta: cached });
  }
}

export async function loadAccounts() {
  const s = getState();
  try {
    const accounts = await api.get("/api/accounts", { account: s.meId });
    setState({ accounts });
    cacheSet("accounts", accounts);
    return accounts;
  } catch (error) {
    if (!s.accounts) {
      const cached = await cacheGet("accounts");
      setState({ accounts: cached || [] });
    }
    if (!isNetworkError(error)) toast(error.message, "error");
    return getState().accounts;
  }
}

const boardCacheTimers = {};

function persistBoard(accountId) {
  const s = getState();
  if (s.meId && s.boards[accountId]) cacheSet(`board:${s.meId}:${accountId}`, s.boards[accountId]);
}

/** Atualiza o quadro na tela e no cache local, para que alterações offline sobrevivam a recarregamentos. */
function setBoard(accountId, board) {
  setState((s) => ({ boards: { ...s.boards, [accountId]: board } }));
  clearTimeout(boardCacheTimers[accountId]);
  boardCacheTimers[accountId] = setTimeout(() => persistBoard(accountId), 200);
}

window.addEventListener("pagehide", () => Object.keys(getState().boards).forEach(persistBoard));

export async function loadBoard(accountId, { silent = false } = {}) {
  const s = getState();
  if (!accountId) return null;
  if (!silent) setState((st) => ({ loadingBoards: { ...st.loadingBoards, [accountId]: true } }));
  try {
    const board = await api.get(`/api/accounts/${accountId}/board`, { account: s.meId });
    // Não sobrescreve alterações locais ainda não confirmadas; a fila recarrega ao esvaziar.
    if (!pendingFor((meta) => meta.accountId === accountId)) setBoard(accountId, board);
    return board;
  } catch (error) {
    if (!getState().boards[accountId]) {
      const cached = await cacheGet(`board:${s.meId}:${accountId}`);
      if (cached) setBoard(accountId, cached);
    }
    if (error instanceof ApiError && error.status === 404) toast("Conta não encontrada.", "error");
    return null;
  } finally {
    setState((st) => ({ loadingBoards: { ...st.loadingBoards, [accountId]: false } }));
  }
}

export function ensureBoard(accountId) {
  const s = getState();
  if (!s.boards[accountId]) {
    cacheGet(`board:${s.meId}:${accountId}`).then((cached) => {
      if (cached && !getState().boards[accountId]) setBoard(accountId, cached);
    });
  }
  return loadBoard(accountId, { silent: !!s.boards[accountId] });
}

function scheduleRefresh(accountId, delay = 400) {
  clearTimeout(refreshTimers[accountId]);
  refreshTimers[accountId] = setTimeout(() => {
    if (!hasPending()) {
      loadBoard(accountId, { silent: true });
      invalidateDashboards(accountId);
    }
  }, delay);
}

export async function loadDashboard(accountId, period, { force = false } = {}) {
  const key = `${accountId}:${period}`;
  const s = getState();
  const current = s.dashboards[key];
  if (current && !current.stale && !force) return current.data;
  setState((st) => ({ dashboards: { ...st.dashboards, [key]: { ...(current || {}), loading: true } } }));
  try {
    const data = await api.get(`/api/accounts/${accountId}/dashboard?period=${period}`, { account: s.meId });
    setState((st) => ({ dashboards: { ...st.dashboards, [key]: { data, loading: false, stale: false } } }));
    cacheSet(`dash:${key}`, data);
    return data;
  } catch (error) {
    const cached = current?.data || (await cacheGet(`dash:${key}`));
    setState((st) => ({ dashboards: { ...st.dashboards, [key]: { data: cached || null, loading: false, stale: false, error: error.message } } }));
    return cached;
  }
}

export function invalidateDashboards(accountId) {
  setState((s) => {
    const dashboards = { ...s.dashboards };
    let changed = false;
    for (const key of Object.keys(dashboards)) {
      if (key.startsWith(`${accountId}:`) && !dashboards[key].stale) {
        dashboards[key] = { ...dashboards[key], stale: true };
        changed = true;
      }
    }
    return changed ? { dashboards } : null;
  });
}

export async function loadTeam(period) {
  const s = getState();
  try {
    const data = await api.get(`/api/team/overview?period=${period}`, { account: s.meId });
    setState((st) => ({ team: { ...st.team, [period]: data } }));
    cacheSet(`team:${period}`, data);
  } catch {
    const cached = await cacheGet(`team:${period}`);
    if (cached) setState((st) => ({ team: { ...st.team, [period]: cached } }));
  }
}

// ---------------------------------------------------------------------------------------------
// Conta em uso (RF23, RF26, RF28)
// ---------------------------------------------------------------------------------------------

export async function selectAccount(accountId) {
  prefs.set("me", accountId);
  setState({ meId: accountId, drawer: null, panel: null, modal: null });
  const accounts = getState().accounts || [];
  const me = accounts.find((a) => a.id === accountId);
  navigate(homeRoute(me));
  await loadBoard(accountId);
  checkWeeklyReview(accountId);
}

export function switchAccount() {
  prefs.set("me", null);
  setState({ meId: null, drawer: null, panel: null, modal: null });
  history.replaceState(null, "", "#/");
  loadAccounts();
}

export async function createAccount(name) {
  const account = await api.post("/api/accounts", { name, id: uid() }, { key: uid() });
  setState((s) => ({ accounts: [...(s.accounts || []), account].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")) }));
  toast(`Conta “${account.name}” criada.`);
  await selectAccount(account.id);
  return account;
}

async function checkWeeklyReview(accountId) {
  try {
    const { review } = await api.post(`/api/accounts/${accountId}/weekly-review`, undefined, { account: accountId });
    if (review && !review.seen_at && getState().meId === accountId) openModal("weeklyReview", { review, accountId });
  } catch {
    /* offline: a revisão aparece no próximo acesso */
  }
}

export async function markReviewSeen(accountId, week) {
  closeModal();
  try {
    await api.post(`/api/accounts/${accountId}/weekly-reviews/${week}/seen`, undefined, { account: accountId });
  } catch {
    /* tentará de novo no próximo acesso */
  }
}

// ---------------------------------------------------------------------------------------------
// Mutações com atualização otimista (RF06, RN35)
// ---------------------------------------------------------------------------------------------

function me() {
  return getState().meId;
}

function mutate({ method, path, body, accountId, taskId, itemId, apply, onResult, success }) {
  apply?.(); // a interface responde na hora (RNF09: ≤ 100 ms); o servidor confirma em seguida
  const promise = enqueue({ method, path, body, account: me(), meta: { accountId, taskId, itemId } });
  // itemId identifica eventos do calendário, itens da Daily, listas e itens de listas
  const sameItem = (meta) => (taskId ? meta.taskId === taskId : itemId ? meta.itemId === itemId : meta.accountId === accountId);
  return promise.then(
    (result) => {
      // Aplica a resposta do servidor só se não houver outra alteração pendente no mesmo item.
      if (onResult && !pendingFor(sameItem)) onResult(result);
      if (success) toast(success);
      return result;
    },
    (error) => {
      scheduleRefresh(accountId, 50);
      throw error;
    },
  );
}

function updateBoard(accountId, fn) {
  const board = getState().boards[accountId];
  if (!board) return;
  const next = fn(board);
  if (next && next !== board) setBoard(accountId, next);
}

function withTasks(board, tasks) {
  return { ...board, tasks, goals: recomputeGoals(board.goals, tasks) };
}

export function localTask(accountId, taskId) {
  return getState().boards[accountId]?.tasks.find((t) => t.id === taskId) || null;
}

function patchTaskLocal(accountId, taskId, fn) {
  const now = new Date().toISOString();
  updateBoard(accountId, (board) =>
    withTasks(
      board,
      board.tasks.map((t) => (t.id === taskId ? normalizeTask({ ...fn(t), last_activity_at: now }, now) : t)),
    ),
  );
}

function replaceTask(task) {
  updateBoard(task.account_id, (board) => {
    const exists = board.tasks.some((t) => t.id === task.id);
    const tasks = exists ? board.tasks.map((t) => (t.id === task.id ? task : t)) : [...board.tasks, task];
    return withTasks(board, tasks);
  });
}

export function createTask(accountId, data, { assign = false } = {}) {
  const id = uid();
  const steps = (data.steps || []).map((text, index) => ({ id: uid(), text, done: false, done_at: null, position: index }));
  const now = new Date().toISOString();
  const s = getState();
  const actor = s.accounts.find((a) => a.id === s.meId);
  const optimistic = normalizeTask({
    id,
    account_id: accountId,
    title: data.title,
    description: data.description || "",
    difficulty: data.difficulty || "medio",
    priority: data.priority || "media",
    due_date: data.due_date || null,
    requester: assign ? actor.name : data.requester || "",
    created_at: now,
    completed_at: null,
    status: "pendente",
    goal_id: data.goal_id || null,
    notes: data.notes || "",
    links: data.links || [],
    phase: data.phase || "planejamento",
    last_activity_at: now,
    due_history: [],
    assigned_by: assign ? actor.id : null,
    assigned_by_name: assign ? actor.name : null,
    assigned_seen_at: null,
    steps,
    attachments: [],
    comments: { total: 0, unread: 0 },
  });
  const body = {
    id,
    title: data.title,
    description: data.description || "",
    difficulty: data.difficulty || "medio",
    priority: data.priority || "media",
    due_date: data.due_date || null,
    requester: data.requester || "",
    goal_id: data.goal_id || null,
    notes: data.notes || "",
    links: data.links || [],
    phase: data.phase || "planejamento",
    steps: steps.map((st) => ({ id: st.id, text: st.text })),
    source: data.source || "form",
    ...(data.template_name ? { template_name: data.template_name } : {}),
  };
  return mutate({
    method: "POST",
    path: `/api/accounts/${accountId}/tasks`,
    body,
    accountId,
    taskId: id,
    apply: () => updateBoard(accountId, (board) => withTasks(board, [...board.tasks, optimistic])),
    onResult: replaceTask,
    success: assign ? "Tarefa atribuída." : "Tarefa criada.",
  }).then(() => id);
}

export function updateTask(accountId, taskId, changes, { success } = {}) {
  return mutate({
    method: "PATCH",
    path: `/api/tasks/${taskId}`,
    body: changes,
    accountId,
    taskId,
    apply: () =>
      patchTaskLocal(accountId, taskId, (t) => {
        const next = { ...t, ...changes };
        delete next.due_reason;
        delete next.due_reason_text;
        return next;
      }),
    onResult: replaceTask,
    success,
  });
}

export function setTaskDone(accountId, taskId, done) {
  const task = localTask(accountId, taskId);
  return mutate({
    method: "POST",
    path: `/api/tasks/${taskId}/status`,
    body: { done },
    accountId,
    taskId,
    apply: () =>
      patchTaskLocal(accountId, taskId, (t) => {
        if (t.steps.length) {
          const now = new Date().toISOString();
          return done ? { ...t, steps: t.steps.map((st) => (st.done ? st : { ...st, done: true, done_at: now })) } : t;
        }
        return { ...t, status: done ? "concluida" : "pendente", completed_at: done ? new Date().toISOString() : null };
      }),
    onResult: replaceTask,
    success: done ? "Tarefa concluída." : task && isDone(task) ? "Tarefa reaberta." : undefined,
  });
}

export function deleteTask(accountId, taskId) {
  const task = localTask(accountId, taskId);
  if (getState().drawer?.taskId === taskId) setState({ drawer: null });
  return mutate({
    method: "DELETE",
    path: `/api/tasks/${taskId}`,
    accountId,
    taskId,
    apply: () => updateBoard(accountId, (board) => withTasks(board, board.tasks.filter((t) => t.id !== taskId))),
    success: task ? `“${task.title}” excluída.` : "Tarefa excluída.",
  });
}

export function toggleStep(accountId, taskId, stepId, done) {
  const before = localTask(accountId, taskId);
  return mutate({
    method: "PATCH",
    path: `/api/tasks/${taskId}/steps/${stepId}`,
    body: { done },
    accountId,
    taskId,
    apply: () =>
      patchTaskLocal(accountId, taskId, (t) => ({
        ...t,
        steps: t.steps.map((st) => (st.id === stepId ? { ...st, done, done_at: done ? new Date().toISOString() : null } : st)),
      })),
    onResult: replaceTask,
  }).then((result) => {
    const after = localTask(accountId, taskId);
    if (before && after && !isDone(before) && isDone(after)) toast("Todas as etapas marcadas: tarefa concluída.");
    return result;
  });
}

export function renameStep(accountId, taskId, stepId, text) {
  return mutate({
    method: "PATCH",
    path: `/api/tasks/${taskId}/steps/${stepId}`,
    body: { text },
    accountId,
    taskId,
    apply: () =>
      patchTaskLocal(accountId, taskId, (t) => ({ ...t, steps: t.steps.map((st) => (st.id === stepId ? { ...st, text } : st)) })),
    onResult: replaceTask,
  });
}

export function addSteps(accountId, taskId, texts, source) {
  const task = localTask(accountId, taskId);
  const start = task ? Math.max(-1, ...task.steps.map((st) => st.position)) + 1 : 0;
  const steps = texts.map((text, index) => ({ id: uid(), text, done: false, done_at: null, position: start + index }));
  return mutate({
    method: "POST",
    path: `/api/tasks/${taskId}/steps`,
    body: { steps: steps.map((st) => ({ id: st.id, text: st.text })), ...(source ? { source } : {}) },
    accountId,
    taskId,
    apply: () => patchTaskLocal(accountId, taskId, (t) => ({ ...t, steps: [...t.steps, ...steps] })),
    onResult: replaceTask,
    success: texts.length > 1 ? `${texts.length} etapas adicionadas.` : undefined,
  });
}

export function deleteStep(accountId, taskId, stepId) {
  return mutate({
    method: "DELETE",
    path: `/api/tasks/${taskId}/steps/${stepId}`,
    accountId,
    taskId,
    apply: () => patchTaskLocal(accountId, taskId, (t) => ({ ...t, steps: t.steps.filter((st) => st.id !== stepId) })),
    onResult: replaceTask,
  });
}

export function reorderSteps(accountId, taskId, order) {
  return mutate({
    method: "PUT",
    path: `/api/tasks/${taskId}/steps/order`,
    body: { order },
    accountId,
    taskId,
    apply: () =>
      patchTaskLocal(accountId, taskId, (t) => ({
        ...t,
        steps: orderedSteps(t.steps).map((st) => ({ ...st, position: order.indexOf(st.id) === -1 ? 999 : order.indexOf(st.id) })),
      })),
    onResult: replaceTask,
  });
}

export function markAssignmentSeen(accountId, taskId) {
  const task = localTask(accountId, taskId);
  if (!task || !task.assigned_by || task.assigned_seen_at || accountId !== me()) return;
  mutate({
    method: "POST",
    path: `/api/tasks/${taskId}/seen`,
    accountId,
    taskId,
    apply: () => updateBoard(accountId, (board) => ({
      ...board,
      tasks: board.tasks.map((t) => (t.id === taskId ? { ...t, assigned_seen_at: new Date().toISOString() } : t)),
    })),
    onResult: replaceTask,
  }).catch(() => {});
}

export function setTop3(accountId, taskIds) {
  return mutate({
    method: "PUT",
    path: `/api/accounts/${accountId}/top3`,
    body: { task_ids: taskIds },
    accountId,
    apply: () => updateBoard(accountId, (board) => ({ ...board, top3: { day: todayISO(), task_ids: taskIds } })),
    onResult: (top3) => updateBoard(accountId, (board) => ({ ...board, top3 })),
    success: "Top 3 do dia atualizado.",
  });
}

export async function uploadAttachment(accountId, taskId, file) {
  const form = new FormData();
  form.append("file", file);
  const task = await api.post(`/api/tasks/${taskId}/attachments`, form, { account: me() });
  replaceTask(task);
  toast(`Anexo “${file.name}” enviado.`);
  return task;
}

export function deleteAttachment(accountId, taskId, attachmentId) {
  return mutate({
    method: "DELETE",
    path: `/api/attachments/${attachmentId}`,
    accountId,
    taskId,
    apply: () => patchTaskLocal(accountId, taskId, (t) => ({ ...t, attachments: t.attachments.filter((a) => a.id !== attachmentId) })),
    onResult: (task) => task && replaceTask(task),
    success: "Anexo removido.",
  });
}

// Metas (RF29–RF33)

export function createGoal(accountId, data) {
  const id = uid();
  const now = new Date().toISOString();
  const goal = {
    id,
    account_id: accountId,
    title: data.title,
    description: data.description || "",
    target_date: data.target_date || null,
    created_at: now,
    completed_at: null,
    status: "andamento",
    progress: 0,
    done_tasks: 0,
    total_tasks: 0,
    overdue: false,
  };
  return mutate({
    method: "POST",
    path: `/api/accounts/${accountId}/goals`,
    body: { id, ...data },
    accountId,
    apply: () =>
      updateBoard(accountId, (board) => {
        const tasks = board.tasks.map((t) => ((data.task_ids || []).includes(t.id) ? { ...t, goal_id: id } : t));
        return { ...board, tasks, goals: recomputeGoals([...board.goals, goal], tasks) };
      }),
    onResult: () => scheduleRefresh(accountId, 50),
    success: "Meta criada.",
  }).then(() => id);
}

export function updateGoal(accountId, goalId, changes) {
  return mutate({
    method: "PATCH",
    path: `/api/goals/${goalId}`,
    body: changes,
    accountId,
    apply: () => updateBoard(accountId, (board) => ({ ...board, goals: board.goals.map((g) => (g.id === goalId ? { ...g, ...changes } : g)) })),
    onResult: (goal) => updateBoard(accountId, (board) => ({ ...board, goals: board.goals.map((g) => (g.id === goalId ? goal : g)) })),
  });
}

export function deleteGoal(accountId, goalId) {
  const goal = getState().boards[accountId]?.goals.find((g) => g.id === goalId);
  return mutate({
    method: "DELETE",
    path: `/api/goals/${goalId}`,
    accountId,
    apply: () =>
      updateBoard(accountId, (board) => ({
        ...board,
        goals: board.goals.filter((g) => g.id !== goalId),
        tasks: board.tasks.map((t) => (t.goal_id === goalId ? { ...t, goal_id: null } : t)),
      })),
    success: goal ? `Meta “${goal.title}” excluída. As tarefas foram mantidas.` : "Meta excluída.",
  });
}

export function linkTasks(accountId, goalId, taskIds) {
  return mutate({
    method: "POST",
    path: `/api/goals/${goalId}/tasks`,
    body: { task_ids: taskIds },
    accountId,
    apply: () =>
      updateBoard(accountId, (board) =>
        withTasks(board, board.tasks.map((t) => (taskIds.includes(t.id) ? { ...t, goal_id: goalId } : t))),
      ),
    onResult: () => scheduleRefresh(accountId, 50),
    success: taskIds.length > 1 ? `${taskIds.length} tarefas vinculadas.` : "Tarefa vinculada.",
  });
}

// Calendário: eventos com horário ou de dia inteiro, repetição e ocorrências avulsas

function updateCalendar(accountId, fn) {
  updateBoard(accountId, (board) => ({ ...board, calendar: fn(board.calendar || []) }));
}

function replaceEntry(entry) {
  updateCalendar(entry.account_id, (list) =>
    list.some((e) => e.id === entry.id) ? list.map((e) => (e.id === entry.id ? entry : e)) : [...list, entry],
  );
}

function localEntry(accountId, entryId) {
  return (getState().boards[accountId]?.calendar || []).find((e) => e.id === entryId) || null;
}

export function createEntry(accountId, data) {
  const id = uid();
  const now = new Date().toISOString();
  const optimistic = normalizeEntry({
    id,
    account_id: accountId,
    notes: "",
    location: "",
    color: "azul",
    private: false,
    redacted: false,
    recurrence: null,
    ...data,
    exceptions: [],
    created_at: now,
    updated_at: now,
  });
  return mutate({
    method: "POST",
    path: `/api/accounts/${accountId}/calendar`,
    body: { id, ...data },
    accountId,
    itemId: id,
    apply: () => updateCalendar(accountId, (list) => [...list, optimistic]),
    onResult: replaceEntry,
    success: "Evento criado.",
  }).then(() => id);
}

/** Edita o evento (a série inteira, se repetir). */
export function updateEntry(accountId, entryId, changes, { success } = {}) {
  return mutate({
    method: "PATCH",
    path: `/api/calendar/${entryId}`,
    body: changes,
    accountId,
    itemId: entryId,
    apply: () => updateCalendar(accountId, (list) => list.map((e) => (e.id === entryId ? normalizeEntry({ ...e, ...changes, updated_at: new Date().toISOString() }) : e))),
    onResult: replaceEntry,
    success,
  });
}

export function deleteEntry(accountId, entryId, { success = "Evento excluído." } = {}) {
  return mutate({
    method: "DELETE",
    path: `/api/calendar/${entryId}`,
    accountId,
    itemId: entryId,
    apply: () => updateCalendar(accountId, (list) => list.filter((e) => e.id !== entryId)),
    success,
  });
}

/** Exclui só uma ocorrência; a série continua. */
export function excludeOccurrence(accountId, entryId, day) {
  return mutate({
    method: "DELETE",
    path: `/api/calendar/${entryId}/occurrences/${day}`,
    accountId,
    itemId: entryId,
    apply: () =>
      updateCalendar(accountId, (list) =>
        list.map((e) => (e.id === entryId ? { ...e, exceptions: [...new Set([...(e.exceptions || []), day])].sort() } : e)),
      ),
    onResult: replaceEntry,
    success: "Ocorrência excluída.",
  });
}

/** Altera só uma ocorrência: ela sai da série e vira um evento avulso (como no Outlook). */
export function detachOccurrence(accountId, entryId, day, changes, { success = "Só esta ocorrência foi alterada." } = {}) {
  const id = uid();
  const series = localEntry(accountId, entryId);
  return mutate({
    method: "POST",
    path: `/api/calendar/${entryId}/occurrences/${day}`,
    body: { id, ...changes },
    accountId,
    itemId: entryId,
    apply: () =>
      updateCalendar(accountId, (list) => {
        if (!series) return list;
        const span = diffDays(series.start_date, series.end_date);
        const single = normalizeEntry({
          ...series,
          start_date: day,
          end_date: addDays(day, span),
          ...changes,
          id,
          recurrence: null,
          exceptions: [],
        });
        return [...list.map((e) => (e.id === entryId ? { ...e, exceptions: [...new Set([...(e.exceptions || []), day])].sort() } : e)), single];
      }),
    onResult: (result) => {
      replaceEntry(result.series);
      replaceEntry(result.entry);
    },
    success,
  });
}

// Daily: tarefas simples do dia (como no Microsoft To Do)

function updateDaily(accountId, fn) {
  updateBoard(accountId, (board) => ({ ...board, daily: fn(board.daily || []) }));
}

function replaceDailyItem(item) {
  updateDaily(item.account_id, (list) =>
    list.some((i) => i.id === item.id) ? list.map((i) => (i.id === item.id ? item : i)) : [...list, item],
  );
}

export function createDailyItem(accountId, data, { id = uid() } = {}) {
  const now = new Date().toISOString();
  const optimistic = { id, account_id: accountId, note: "", ...data, done: false, done_at: null, created_at: now, updated_at: now };
  return mutate({
    method: "POST",
    path: `/api/accounts/${accountId}/daily`,
    body: { id, ...data },
    accountId,
    itemId: id,
    apply: () => updateDaily(accountId, (list) => [...list.filter((i) => i.id !== id), optimistic]),
    onResult: replaceDailyItem,
  }).then(() => id);
}

/** Título, anotação, dia (mover) e conclusão. */
export function updateDailyItem(accountId, itemId, changes) {
  return mutate({
    method: "PATCH",
    path: `/api/daily/${itemId}`,
    body: changes,
    accountId,
    itemId,
    apply: () =>
      updateDaily(accountId, (list) =>
        list.map((i) => {
          if (i.id !== itemId) return i;
          const now = new Date().toISOString();
          const next = { ...i, ...changes, updated_at: now };
          if ("done" in changes && changes.done !== i.done) next.done_at = changes.done ? now : null;
          return next;
        }),
      ),
    onResult: replaceDailyItem,
  });
}

/** Exclui na hora, com "Desfazer": o item volta com o mesmo ID, dia, anotação e conclusão. */
export function deleteDailyItem(accountId, itemId) {
  const item = (getState().boards[accountId]?.daily || []).find((i) => i.id === itemId);
  const promise = mutate({
    method: "DELETE",
    path: `/api/daily/${itemId}`,
    accountId,
    itemId,
    apply: () => updateDaily(accountId, (list) => list.filter((i) => i.id !== itemId)),
  });
  if (item) {
    toast(`“${item.title}” excluída.`, "success", {
      duration: 6000,
      action: {
        label: "Desfazer",
        onClick: () => {
          createDailyItem(accountId, { title: item.title, note: item.note, day: item.day }, { id: item.id });
          if (item.done) updateDailyItem(accountId, item.id, { done: true });
        },
      },
    });
  }
  return promise;
}

// Listas: listas com nome, no modelo tarefas (como a Daily) ou ranking (posição reordenável e quantidade)

function updateLists(accountId, fn) {
  updateBoard(accountId, (board) => ({ ...board, lists: fn(board.lists || []) }));
}

function updateListItems(accountId, fn) {
  updateBoard(accountId, (board) => ({ ...board, list_items: fn(board.list_items || []) }));
}

const upsert = (rows, row) => (rows.some((r) => r.id === row.id) ? rows.map((r) => (r.id === row.id ? row : r)) : [...rows, row]);

/** Cria a lista e devolve o ID na hora, para abri-la. */
export function createList(accountId, data) {
  const id = uid();
  const now = new Date().toISOString();
  mutate({
    method: "POST",
    path: `/api/accounts/${accountId}/lists`,
    body: { id, ...data },
    accountId,
    itemId: id,
    apply: () => updateLists(accountId, (lists) => [...lists, { id, account_id: accountId, ...data, created_at: now, updated_at: now }]),
    onResult: (list) => updateLists(accountId, (lists) => upsert(lists, list)),
  });
  return id;
}

/** Nome e modelo (tarefas ou ranking). */
export function updateList(accountId, listId, changes) {
  return mutate({
    method: "PATCH",
    path: `/api/lists/${listId}`,
    body: changes,
    accountId,
    itemId: listId,
    apply: () => updateLists(accountId, (lists) => lists.map((l) => (l.id === listId ? { ...l, ...changes, updated_at: new Date().toISOString() } : l))),
    onResult: (list) => updateLists(accountId, (lists) => upsert(lists, list)),
  });
}

/** Exclui a lista com todos os itens, depois de confirmar. Resolve true se excluiu. */
export async function deleteList(accountId, listId) {
  const board = getState().boards[accountId];
  const list = (board?.lists || []).find((l) => l.id === listId);
  if (!list) return false;
  const count = (board.list_items || []).filter((i) => i.list_id === listId).length;
  const ok = await confirmDialog({
    title: "Excluir lista?",
    text: count
      ? `A lista “${list.name}” e ${plural(count, "item", "itens")} serão excluídos. Esta ação não pode ser desfeita.`
      : `A lista “${list.name}” será excluída. Esta ação não pode ser desfeita.`,
    confirmLabel: "Excluir lista",
    danger: true,
  });
  if (!ok) return false;
  mutate({
    method: "DELETE",
    path: `/api/lists/${listId}`,
    accountId,
    itemId: listId,
    apply: () =>
      updateBoard(accountId, (b) => ({
        ...b,
        lists: (b.lists || []).filter((l) => l.id !== listId),
        list_items: (b.list_items || []).filter((i) => i.list_id !== listId),
      })),
    success: `Lista “${list.name}” excluída.`,
  });
  return true;
}

/** Sem posição, o item entra no fim do ranking (como no servidor). */
export function createListItem(accountId, listId, data, { id = uid() } = {}) {
  const now = new Date().toISOString();
  const siblings = (getState().boards[accountId]?.list_items || []).filter((i) => i.list_id === listId);
  const position = data.position ?? Math.max(-1, ...siblings.map((i) => i.position)) + 1;
  const optimistic = { id, list_id: listId, account_id: accountId, note: "", quantity: null, unit: "", ...data, position, done: false, done_at: null, created_at: now, updated_at: now };
  return mutate({
    method: "POST",
    path: `/api/lists/${listId}/items`,
    body: { id, ...data },
    accountId,
    itemId: id,
    apply: () => updateListItems(accountId, (items) => [...items.filter((i) => i.id !== id), optimistic]),
    onResult: (item) => updateListItems(accountId, (items) => upsert(items, item)),
  }).then(() => id);
}

/** Título, anotação, quantidade, unidade e conclusão. */
export function updateListItem(accountId, itemId, changes) {
  return mutate({
    method: "PATCH",
    path: `/api/list-items/${itemId}`,
    body: changes,
    accountId,
    itemId,
    apply: () =>
      updateListItems(accountId, (items) =>
        items.map((i) => {
          if (i.id !== itemId) return i;
          const now = new Date().toISOString();
          const next = { ...i, ...changes, updated_at: now };
          if ("done" in changes && changes.done !== i.done) next.done_at = changes.done ? now : null;
          return next;
        }),
      ),
    onResult: (item) => updateListItems(accountId, (items) => upsert(items, item)),
  });
}

/** Exclui na hora, com "Desfazer": o item volta com o mesmo ID, posição, quantidade e conclusão. */
export function deleteListItem(accountId, itemId) {
  const item = (getState().boards[accountId]?.list_items || []).find((i) => i.id === itemId);
  const promise = mutate({
    method: "DELETE",
    path: `/api/list-items/${itemId}`,
    accountId,
    itemId,
    apply: () => updateListItems(accountId, (items) => items.filter((i) => i.id !== itemId)),
  });
  if (item) {
    toast(`“${item.title}” excluído.`, "success", {
      duration: 6000,
      action: {
        label: "Desfazer",
        onClick: () => {
          const { title, note, quantity, unit, position } = item;
          createListItem(accountId, item.list_id, { title, note, quantity, unit, position }, { id: item.id });
          if (item.done) updateListItem(accountId, item.id, { done: true });
        },
      },
    });
  }
  return promise;
}

/** Ranking: `order` traz os IDs na nova ordem; a resposta do servidor só atualiza as posições. */
export function reorderListItems(accountId, listId, order) {
  const setPositions = (positions) =>
    updateListItems(accountId, (items) => items.map((i) => (positions.has(i.id) ? { ...i, position: positions.get(i.id) } : i)));
  return mutate({
    method: "PUT",
    path: `/api/lists/${listId}/order`,
    body: { order },
    accountId,
    itemId: listId,
    apply: () => setPositions(new Map(order.map((id, index) => [id, index]))),
    onResult: (items) => setPositions(new Map(items.map((i) => [i.id, i.position]))),
  });
}

// Comentários (RF66–RF68)

export async function loadComments(taskId) {
  return api.get(`/api/tasks/${taskId}/comments`, { account: me() });
}

export function addComment(accountId, taskId, text) {
  const id = uid();
  return mutate({ method: "POST", path: `/api/tasks/${taskId}/comments`, body: { id, text }, accountId }).then((comment) => {
    updateBoard(accountId, (board) => ({
      ...board,
      tasks: board.tasks.map((t) => (t.id === taskId ? { ...t, comments: { total: (t.comments?.total || 0) + 1, unread: 0 } } : t)),
    }));
    return comment;
  });
}

export function editComment(accountId, commentId, text) {
  return mutate({ method: "PATCH", path: `/api/comments/${commentId}`, body: { text }, accountId });
}

export function deleteComment(accountId, taskId, commentId) {
  return mutate({ method: "DELETE", path: `/api/comments/${commentId}`, accountId }).then(() => {
    updateBoard(accountId, (board) => ({
      ...board,
      tasks: board.tasks.map((t) => (t.id === taskId ? { ...t, comments: { ...t.comments, total: Math.max(0, (t.comments?.total || 1) - 1) } } : t)),
    }));
  });
}

export function markCommentsRead(accountId, taskId) {
  const task = localTask(accountId, taskId);
  if (!task?.comments?.unread) return;
  updateBoard(accountId, (board) => ({
    ...board,
    tasks: board.tasks.map((t) => (t.id === taskId ? { ...t, comments: { ...t.comments, unread: 0 } } : t)),
  }));
  api.post(`/api/tasks/${taskId}/comments/read`, undefined, { account: me() }).catch(() => {});
}

// Conta (RF27, RF61, RN22, RN29)

export async function updateAccount(accountId, changes, { success = "Configurações salvas." } = {}) {
  const account = await api.patch(`/api/accounts/${accountId}`, changes, { account: me(), key: uid() });
  setState((s) => ({ accounts: s.accounts.map((a) => (a.id === accountId ? { ...a, ...account } : a)) }));
  updateBoard(accountId, (board) => ({ ...board, account: { ...board.account, ...account } }));
  if (success) toast(success);
  return account;
}

export async function deleteAccount(accountId) {
  await api.delete(`/api/accounts/${accountId}`, { account: me(), key: uid() });
  toast("Conta excluída.");
  setState((s) => ({ accounts: s.accounts.filter((a) => a.id !== accountId), boards: { ...s.boards, [accountId]: undefined } }));
  switchAccount();
}

// ---------------------------------------------------------------------------------------------
// Inicialização e atualização periódica
// ---------------------------------------------------------------------------------------------

async function poll() {
  const s = getState();
  if (document.visibilityState !== "visible" || !navigator.onLine || !s.meId) return;
  try {
    const changes = await api.get(`/api/changes?since=${lastSeq}`);
    if (changes.seq === lastSeq) return;
    const first = lastSeq === 0;
    lastSeq = changes.seq;
    if (first) return;
    if (changes.directory) loadAccounts();
    const boards = getState().boards;
    for (const accountId of changes.accounts) {
      invalidateDashboards(accountId);
      if (boards[accountId]) scheduleRefresh(accountId, 100);
    }
    if (changes.directory) setState({ team: {} });
  } catch {
    /* offline: tenta no próximo ciclo */
  }
}

export async function init() {
  startQueue();
  onSyncChange((sync) => setState({ sync }));
  onMutationError((error) => toast(error.message || "Não foi possível salvar a alteração.", "error"));
  onDrain(() => {
    const s = getState();
    const visible = new Set([s.meId, s.route.params?.accountId].filter(Boolean));
    visible.forEach((id) => scheduleRefresh(id, 300));
  });
  window.addEventListener("online", () => setState({ online: true }));
  window.addEventListener("offline", () => setState({ online: false }));
  window.addEventListener("hashchange", applyRoute);

  const cachedAccounts = await cacheGet("accounts");
  if (cachedAccounts) setState({ accounts: cachedAccounts });
  await Promise.all([loadMeta(), loadAccounts()]);

  const saved = prefs.get("me");
  const accounts = getState().accounts || [];
  if (saved && accounts.some((a) => a.id === saved)) {
    setState({ meId: saved });
    const cachedBoard = await cacheGet(`board:${saved}:${saved}`);
    if (cachedBoard) setBoard(saved, cachedBoard);
    applyRoute();
    loadBoard(saved);
    checkWeeklyReview(saved);
  } else if (saved) {
    prefs.set("me", null);
  }
  setState({ ready: true });
  clearInterval(pollTimer);
  pollTimer = setInterval(poll, POLL_MS);
  poll();
}
