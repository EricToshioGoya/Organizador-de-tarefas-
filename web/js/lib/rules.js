// Espelho no cliente das regras usadas para atualização otimista e uso offline.
// O servidor continua sendo a fonte da verdade (app/domain/rules.py, coberto por testes).
import { todayISO, diffDays, localDay } from "./format.js";

export const DIFFICULTIES = [
  { key: "facil", label: "Fácil", points: 1 },
  { key: "medio", label: "Médio", points: 2 },
  { key: "dificil", label: "Difícil", points: 3 },
];
export const DIFFICULTY_LABEL = Object.fromEntries(DIFFICULTIES.map((d) => [d.key, d.label]));

export const PRIORITIES = [
  { key: "baixa", label: "Baixa" },
  { key: "media", label: "Média" },
  { key: "alta", label: "Alta" },
  { key: "muito_alta", label: "Muito alta" },
];
export const PRIORITY_LABEL = Object.fromEntries(PRIORITIES.map((p) => [p.key, p.label]));
export const DEFAULT_PRIORITY = "media";
const PRIORITY_RANK = { muito_alta: 0, alta: 1, media: 2, baixa: 3 };
/** Tarefas guardadas no aparelho antes da prioridade existir contam como Média. */
export const priorityOf = (task) => (task.priority in PRIORITY_RANK ? task.priority : DEFAULT_PRIORITY);

export const PHASES = [
  { key: "planejamento", label: "Planejamento", short: "Planejamento" },
  { key: "producao", label: "Em produção", short: "Em produção" },
  { key: "alpha", label: "Versão alpha", short: "Alpha" },
  { key: "beta", label: "Versão beta (funcionando)", short: "Beta" },
  { key: "concluido", label: "Totalmente concluído", short: "Concluído" },
];
export const PHASE_LABEL = Object.fromEntries(PHASES.map((p) => [p.key, p.label]));
// Espelham os tokens --phase-* e --diff-* (web/css/tokens.css): fases do amarelo claro ao vermelho
// intenso, só Concluído em verde; dificuldade em semáforo.
export const PHASE_COLOR = {
  planejamento: "#fde047",
  producao: "#f59e0b",
  alpha: "#ea580c",
  beta: "#a91b25",
  concluido: "#16a34a",
};
export const DIFFICULTY_COLOR = { facil: "#16a34a", medio: "#eab308", dificil: "#dc2626" };
export const PRIORITY_COLOR = { baixa: "#94a3b8", media: "#2a78d6", alta: "#f97316", muito_alta: "#dc2626" };

export const POSTPONE_REASONS = [
  { key: "subestimei", label: "Subestimei o esforço" },
  { key: "prioridade", label: "Mudança de prioridade" },
  { key: "dependencia", label: "Dependência de outra pessoa" },
  { key: "outro", label: "Outro" },
];

export const TITLE_MAX = 120;

export const isDone = (task) => task.status === "concluida";
export const isPending = (task) => task.status === "pendente";

/** RN01: etapas concluídas ÷ total × 100 (para baixo; 100% só com tudo marcado). */
export function progress(task) {
  const total = task.steps?.length || 0;
  if (!total) return isDone(task) ? 100 : 0;
  const done = task.steps.filter((s) => s.done).length;
  return Math.floor((done * 100) / total);
}

export function orderedSteps(steps = []) {
  return [...steps].sort((a, b) => a.position - b.position);
}

/** RF45: primeira etapa não marcada. */
export function nextStep(task) {
  return orderedSteps(task.steps).find((s) => !s.done) || null;
}

/** RN02/RN04: com etapas, o status acompanha as marcações; sem etapas, mantém o atual (RN03). */
export function statusFromSteps(steps, current) {
  if (!steps?.length) return current;
  return steps.every((s) => s.done) ? "concluida" : "pendente";
}

/** Recalcula campos derivados depois de uma alteração otimista. */
export function normalizeTask(task, nowIso = new Date().toISOString()) {
  const status = statusFromSteps(task.steps, task.status);
  const next = { ...task, status };
  if (status !== task.status) next.completed_at = status === "concluida" ? nowIso : null;
  next.progress = progress(next);
  return next;
}

/** RN06: pendente com entrega anterior a hoje. */
export function isOverdue(task, today = todayISO()) {
  return isPending(task) && !!task.due_date && task.due_date < today;
}

/** RF15: pendente com entrega entre hoje e daqui a 2 dias. */
export function isDueSoon(task, today = todayISO()) {
  if (!isPending(task) || !task.due_date) return false;
  const days = diffDays(today, task.due_date);
  return days >= 0 && days <= 2;
}

export function overdueDays(task, today = todayISO()) {
  return task.due_date ? diffDays(task.due_date, today) : 0;
}

/** RN22: pendente sem atividade há mais de N dias. */
export function isStale(task, staleDays = 5, now = Date.now()) {
  if (!isPending(task) || !task.last_activity_at) return false;
  return now - new Date(task.last_activity_at).getTime() > staleDays * 86_400_000;
}

export function staleDaysOf(task, now = Date.now()) {
  return Math.floor((now - new Date(task.last_activity_at).getTime()) / 86_400_000);
}

/** Pendentes por prioridade (Muito alta primeiro; no empate, a criada antes); concluídas pela conclusão (mais recente primeiro). */
export function sortPending(tasks) {
  return [...tasks].sort((a, b) => {
    const rank = PRIORITY_RANK[priorityOf(a)] - PRIORITY_RANK[priorityOf(b)];
    if (rank) return rank;
    return a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0;
  });
}

export function sortDone(tasks) {
  return [...tasks].sort((a, b) => ((a.completed_at || "") < (b.completed_at || "") ? 1 : -1));
}

/** RN14: tarefas concluídas ÷ vinculadas × 100 (0% sem tarefas). */
export function goalProgress(tasks) {
  if (!tasks.length) return 0;
  return Math.floor((tasks.filter(isDone).length * 100) / tasks.length);
}

/** RN15: concluída quando tem tarefas e todas estão concluídas. */
export function goalStatus(tasks) {
  return tasks.length && tasks.every(isDone) ? "concluida" : "andamento";
}

/** RN16: meta em andamento com data-alvo anterior a hoje. */
export function goalOverdue(goal, today = todayISO()) {
  return goal.status === "andamento" && !!goal.target_date && goal.target_date < today;
}

/** Recalcula as metas afetadas depois de mudanças locais nas tarefas. */
export function recomputeGoals(goals, tasks) {
  return goals.map((goal) => {
    const linked = tasks.filter((t) => t.goal_id === goal.id);
    const status = goalStatus(linked);
    return {
      ...goal,
      status,
      progress: goalProgress(linked),
      done_tasks: linked.filter(isDone).length,
      total_tasks: linked.length,
      completed_at: status === "concluida" ? goal.completed_at || new Date().toISOString() : null,
    };
  });
}

/** RN18: o Top 3 vale somente para o dia em que foi definido. */
export function top3Today(board, today = todayISO()) {
  if (!board?.top3 || board.top3.day !== today) return [];
  const ids = new Set(board.tasks.map((t) => t.id));
  return board.top3.task_ids.filter((id) => ids.has(id));
}

/** RN21: classifica a mudança de prazo. */
export function classifyDueChange(oldDue, newDue) {
  if (oldDue === newDue) return null;
  if (!oldDue) return "definicao";
  if (!newDue) return "remocao";
  return newDue > oldDue ? "adiamento" : "antecipacao";
}

export function completedOn(task) {
  return localDay(task.completed_at);
}

/** Busca simples por título, sem acentos e sem maiúsculas. */
export function normalizeText(text = "") {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/** RF44 (prévia local): uma etapa por linha, sem linhas vazias nem marcadores. */
export function splitPastedSteps(text = "") {
  const marker = /^\s*(?:[-*•·◦▪▫‣⁃–—+>]|\[\s?[xX✓]?\s?\]|\(?\d{1,3}[.)]|[a-z]\))\s+/;
  return text
    .split(/\r?\n/)
    .map((line) => {
      let current = line;
      for (let i = 0; i < 2; i += 1) {
        const stripped = current.replace(marker, "");
        if (stripped === current) break;
        current = stripped;
      }
      return current.replace(/\s+/g, " ").trim();
    })
    .filter(Boolean);
}
