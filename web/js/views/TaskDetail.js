// Detalhe da tarefa em gaveta lateral (RF04): atributos editáveis com salvamento automático (RF02, RF06),
// etapas (RF07–RF11), anotações, links e anexos (RF46), histórico de prazos (RN21), sugestão (RF53),
// linha do tempo (RF48) e comentários (RF66–RF68). Contas de terceiros ficam em modo somente leitura (RF37).
import { html, cx } from "../lib/html.js";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { Icon } from "../ui/icons.js";
import { Drawer, Menu, Modal } from "../ui/overlay.js";
import { Avatar, Badge, Button, Checkbox, DifficultyBadge, IconButton, PhaseBadge, Progress, Segmented, StatusBadge } from "../ui/core.js";
import { AutoText, Autocomplete, DateInput, Field, Select, useFieldId } from "../ui/forms.js";
import { StepsEditor } from "./StepsEditor.js";
import { copyableFrom } from "./TaskForm.js";
import { api } from "../lib/api.js";
import { useStore, getState, setState } from "../lib/store.js";
import { loadDraft, saveDraft, clearDraft } from "../lib/drafts.js";
import {
  DIFFICULTIES,
  DIFFICULTY_LABEL,
  PHASES,
  POSTPONE_REASONS,
  TITLE_MAX,
  classifyDueChange,
  isDone,
  isOverdue,
  isStale,
  orderedSteps,
  overdueDays,
} from "../lib/rules.js";
import { dueLabel, fmtDate, fmtDateTime, fmtNumber, fmtSize, hostOf, plural, relativeTime, todayISO } from "../lib/format.js";
import {
  addComment,
  addSteps,
  confirmDialog,
  deleteAttachment,
  deleteComment,
  deleteStep,
  deleteTask,
  editComment,
  ensureBoard,
  loadComments,
  markAssignmentSeen,
  markCommentsRead,
  openModal,
  renameStep,
  reorderSteps,
  setTaskDone,
  toast,
  toggleStep,
  updateTask,
  uploadAttachment,
} from "../actions.js";

const REASON_LABEL = Object.fromEntries(POSTPONE_REASONS.map((r) => [r.key, r.label]));

/** RF47: motivo obrigatório ao adiar a entrega. */
export function PostponeModal({ oldDue, newDue, onConfirm, onClose }) {
  const [reason, setReason] = useState(null);
  const [text, setText] = useState("");
  const valid = reason && (reason !== "outro" || text.trim());
  return html`<${Modal}
    title="Por que a entrega foi adiada?"
    icon="calendar"
    size="sm"
    onClose=${onClose}
    footer=${html`
      <${Button} variant="ghost" onClick=${onClose}>Cancelar<//>
      <${Button} variant="primary" disabled=${!valid} onClick=${() => onConfirm(reason, reason === "outro" ? text.trim() : "")}>Adiar entrega<//>`}
  >
    <p class="muted small" style="margin-bottom:14px">
      De <strong class="mono">${fmtDate(oldDue)}</strong> para <strong class="mono">${fmtDate(newDue)}</strong>. O motivo fica no histórico
      de prazos e alimenta o gráfico de causas de atraso (G9).
    </p>
    <div class="stack" style="gap:8px" role="radiogroup" aria-label="Motivo do adiamento">
      ${POSTPONE_REASONS.map(
        (r) => html`<label key=${r.key} class="list-item boxed" style="cursor:pointer">
          <input type="radio" name="reason" value=${r.key} checked=${reason === r.key} onChange=${() => setReason(r.key)} />
          ${r.label}
        </label>`,
      )}
      ${reason === "outro"
        ? html`<input
            class="input"
            placeholder="Descreva o motivo"
            maxLength="500"
            value=${text}
            aria-label="Descreva o motivo"
            ref=${(el) => el && !text && el.focus()}
            onInput=${(e) => setText(e.currentTarget.value)}
          />`
        : null}
    </div>
  <//>`;
}

function useTask(taskId, hintAccountId) {
  const task = useStore((s) => {
    if (hintAccountId && s.boards[hintAccountId]) {
      const found = s.boards[hintAccountId].tasks.find((t) => t.id === taskId);
      if (found) return found;
    }
    for (const board of Object.values(s.boards)) {
      const found = board?.tasks.find((t) => t.id === taskId);
      if (found) return found;
    }
    return null;
  });
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    if (task) return;
    let cancelled = false;
    api
      .get(`/api/tasks/${taskId}`, { account: getState().meId })
      .then((remote) => !cancelled && ensureBoard(remote.account_id))
      .catch(() => !cancelled && setMissing(true));
    return () => {
      cancelled = true;
    };
  }, [taskId, !!task]);
  return { task, missing };
}

export function TaskDrawer({ taskId, accountId }) {
  const close = () => setState({ drawer: null });
  const { task, missing } = useTask(taskId, accountId);
  const meId = useStore((s) => s.meId);
  const board = useStore((s) => (task ? s.boards[task.account_id] : null));
  const owner = useStore((s) => (task ? (s.accounts || []).find((a) => a.id === task.account_id) : null));

  useEffect(() => {
    if (task && task.account_id === meId) markAssignmentSeen(task.account_id, task.id);
  }, [task?.id]);

  if (!task) {
    return html`<${Drawer} onClose=${close} label="Tarefa" header=${html`<div class="grow"></div>`}>
      ${missing
        ? html`<div class="empty"><div class="empty-title">Tarefa não encontrada</div><div class="empty-text">Ela pode ter sido excluída.</div></div>`
        : html`<div class="skeleton" style="height:320px"></div>`}
    <//>`;
  }
  const readOnly = task.account_id !== meId;
  return html`<${Drawer}
    onClose=${close}
    wide
    label=${`Tarefa: ${task.title}`}
    header=${html`<${DrawerHeader} task=${task} board=${board} readOnly=${readOnly} owner=${owner} />`}
  >
    <${TaskDetail} task=${task} board=${board} readOnly=${readOnly} owner=${owner} />
  <//>`;
}

function DrawerHeader({ task, board, readOnly, owner }) {
  const done = isDone(task);
  const onToggle = async (checked) => {
    if (checked && task.steps.length) {
      const remaining = task.steps.filter((s) => !s.done).length;
      const ok = await confirmDialog({
        title: "Concluir tarefa?",
        text: `Isso marcará ${plural(remaining, "etapa restante", "etapas restantes")} como concluída${remaining > 1 ? "s" : ""}.`,
        confirmLabel: "Concluir",
      });
      if (!ok) return;
    }
    if (!checked && task.steps.length) {
      toast("Desmarque uma etapa para reabrir esta tarefa.", "info");
      return;
    }
    setTaskDone(task.account_id, task.id, checked);
  };
  const remove = async () => {
    const ok = await confirmDialog({
      title: "Excluir tarefa?",
      text: `“${task.title}” e todo o seu conteúdo serão excluídos. Esta ação não pode ser desfeita.`,
      confirmLabel: "Excluir",
      danger: true,
    });
    if (ok) deleteTask(task.account_id, task.id);
  };
  // Toda tarefa serve de modelo (RF42): a cópia leva título, descrição, dificuldade e etapas desmarcadas (RN20).
  // De outra conta, a cópia vai para as minhas tarefas, sem solicitante nem meta.
  const duplicate = () => {
    const goal = !readOnly && board?.goals.find((g) => g.id === task.goal_id && g.status === "andamento");
    setState({ drawer: null });
    openModal("newTask", {
      duplicate: true,
      preset: { ...copyableFrom(task), requester: readOnly ? "" : task.requester || "", goal_id: goal ? goal.id : null, template_name: task.title },
    });
  };
  const copyLink = async () => {
    const url = `${location.origin}/#/tarefa/${task.id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copiado.");
    } catch {
      toast(url, "info");
    }
  };
  return html`
    <${Checkbox} checked=${done} disabled=${readOnly} onChange=${onToggle} round label=${done ? "Reabrir tarefa" : "Concluir tarefa"} />
    <div class="grow row" style="gap:8px;min-width:0">
      ${done ? html`<${StatusBadge} kind="good" icon="checkCircle">Concluída<//>` : html`<span class="badge neutral">Pendente</span>`}
      ${readOnly && owner
        ? html`<span class="badge violet" title="Modo somente leitura"><${Icon} name="eye" />${owner.name} · somente leitura</span>`
        : null}
    </div>
    <${Menu}
      trigger=${(props) => html`<${IconButton} icon="more" label="Mais ações" onClick=${props.toggle} aria-haspopup=${props["aria-haspopup"]} aria-expanded=${props["aria-expanded"]} />`}
      items=${[
        { icon: "copy", label: readOnly ? "Copiar para minhas tarefas" : "Duplicar tarefa", onClick: duplicate },
        { icon: "link", label: "Copiar link da tarefa", onClick: copyLink },
        !readOnly && "-",
        !readOnly && { icon: "trash", label: "Excluir tarefa", danger: true, onClick: remove },
      ]}
    />
  `;
}

function TaskDetail({ task, board, readOnly, owner }) {
  const ids = { title: useFieldId("title"), diff: useFieldId("diff"), due: useFieldId("due"), req: useFieldId("req"), goal: useFieldId("goal"), phase: useFieldId("phase"), desc: useFieldId("desc"), notes: useFieldId("notes") };
  const [postpone, setPostpone] = useState(null);
  const [requester, setRequester] = useState(task.requester);
  const [suggestion, setSuggestion] = useState(null);
  const [suggesting, setSuggesting] = useState(false);
  const staleDays = board?.account?.settings?.stale_days || 5;
  const today = todayISO();
  const accountId = task.account_id;

  useEffect(() => setRequester(task.requester), [task.requester]);

  const changeDue = (value) => {
    const kind = classifyDueChange(task.due_date, value);
    if (!kind) return;
    if (kind === "adiamento") setPostpone({ oldDue: task.due_date, newDue: value });
    else updateTask(accountId, task.id, { due_date: value });
  };

  const commitRequester = (value) => {
    const clean = (value || "").trim();
    if (clean !== task.requester) updateTask(accountId, task.id, { requester: clean });
  };

  const suggest = async () => {
    setSuggesting(true);
    try {
      const result = await api.post(`/api/accounts/${accountId}/suggestions`, { title: task.title, description: task.description }, { account: getState().meId });
      setSuggestion(result);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setSuggesting(false);
    }
  };

  const applySuggestion = () => {
    const changes = {};
    if (suggestion.difficulty !== task.difficulty) changes.difficulty = suggestion.difficulty;
    const dueKind = classifyDueChange(task.due_date, suggestion.due_date);
    if (Object.keys(changes).length) updateTask(accountId, task.id, changes);
    if (dueKind === "adiamento") setPostpone({ oldDue: task.due_date, newDue: suggestion.due_date });
    else if (dueKind) updateTask(accountId, task.id, { due_date: suggestion.due_date });
    setSuggestion(null);
    toast("Sugestão aplicada.");
  };

  const steps = orderedSteps(task.steps);
  const overdue = isOverdue(task, today);
  const stale = isStale(task, staleDays);

  return html`
    <section class="stack" style="gap:12px">
      ${readOnly
        ? html`<h2 class="goal-title" style="font-size:var(--text-xl)">${task.title}</h2>`
        : html`<${AutoText}
            id=${ids.title}
            value=${task.title}
            ariaLabel="Título da tarefa"
            inputClass="input-inline input-title"
            maxLength=${TITLE_MAX}
            draftKey=${`title:${task.id}`}
            validate=${(v) => (!v.trim() ? "O título é obrigatório." : v.trim().length > TITLE_MAX ? `Máximo de ${TITLE_MAX} caracteres.` : null)}
            onSave=${(value) => updateTask(accountId, task.id, { title: value.trim() })}
          />`}
      <div class="row-wrap">
        <${DifficultyBadge} value=${task.difficulty} />
        <${PhaseBadge} value=${task.phase} />
        ${overdue ? html`<${StatusBadge} kind="critical" icon="alert">Atrasada há ${plural(overdueDays(task, today), "dia", "dias")}<//>` : null}
        ${stale ? html`<${StatusBadge} kind="serious" icon="pause">Parada (sem atividade há mais de ${staleDays} dias)<//>` : null}
        ${task.assigned_by_name ? html`<${Badge} tone="violet" icon="inbox">Atribuída por ${task.assigned_by_name}<//>` : null}
      </div>
    </section>

    <section class="stack" style="gap:16px" aria-label="Atributos">
      <div class="form-grid">
        <${Field} label="Dificuldade" id=${ids.diff} class="span-2">
          <${Segmented}
            label="Dificuldade"
            disabled=${readOnly}
            value=${task.difficulty}
            options=${DIFFICULTIES.map((d) => ({ value: d.key, label: d.label, dot: `var(--diff-${d.key})` }))}
            onChange=${(value) => updateTask(accountId, task.id, { difficulty: value })}
          />
        <//>
        <${Field} label="Data de entrega" id=${ids.due} hint=${task.due_date ? dueLabel(task.due_date, today) : "Sem data: não entra nos cálculos de atraso."}>
          <div class="row">
            <${DateInput} id=${ids.due} value=${task.due_date} disabled=${readOnly} onChange=${changeDue} ariaLabel="Data de entrega" />
            ${task.due_date && !readOnly
              ? html`<${IconButton} icon="x" size="sm" label="Remover data de entrega" onClick=${() => updateTask(accountId, task.id, { due_date: null })} />`
              : null}
          </div>
        <//>
        <${Field} label="Fase" id=${ids.phase}>
          <${Select}
            id=${ids.phase}
            value=${task.phase}
            disabled=${readOnly}
            options=${PHASES.map((p) => ({ value: p.key, label: p.label }))}
            onChange=${(value) => value && updateTask(accountId, task.id, { phase: value })}
          />
        <//>
        <${Field} label="Solicitante" id=${ids.req}>
          ${readOnly
            ? html`<input class="input" disabled value=${task.requester || "—"} id=${ids.req} />`
            : html`<${Autocomplete}
                id=${ids.req}
                value=${requester}
                options=${board?.requesters || []}
                placeholder="Quem pediu?"
                ariaLabel="Solicitante"
                onChange=${setRequester}
                onCommit=${commitRequester}
              />`}
        <//>
        <${Field} label="Meta" id=${ids.goal}>
          <${Select}
            id=${ids.goal}
            value=${task.goal_id || ""}
            disabled=${readOnly}
            placeholder="Sem meta"
            options=${(board?.goals || []).map((g) => ({ value: g.id, label: g.status === "concluida" ? `${g.title} (concluída)` : g.title }))}
            onChange=${(value) => updateTask(accountId, task.id, { goal_id: value || null })}
          />
        <//>
      </div>

      ${!readOnly
        ? html`<div>
            ${suggestion
              ? suggestion.active && suggestion.found
                ? html`<div class="banner violet">
                    <${Icon} name="sparkles" />
                    <div class="banner-text">
                      Sugestão: <strong>${DIFFICULTY_LABEL[suggestion.difficulty]}</strong> · entrega em <strong class="mono">${fmtDate(suggestion.due_date)}</strong>
                      <div class="xsmall muted">Mediana de ${fmtNumber(suggestion.median_days)} dias em ${suggestion.based_on.length} tarefas semelhantes: ${suggestion.based_on.map((b) => b.title).join(", ")}</div>
                    </div>
                    <${Button} size="sm" variant="primary" onClick=${applySuggestion}>Aplicar<//>
                    <${IconButton} icon="x" size="sm" label="Dispensar sugestão" onClick=${() => setSuggestion(null)} />
                  </div>`
                : html`<div class="banner">
                    <${Icon} name="info" />
                    <div class="banner-text">
                      ${suggestion.active
                        ? "Nenhuma tarefa concluída parecida com esta ainda."
                        : `As sugestões começam com ${suggestion.min_done} tarefas concluídas (agora: ${suggestion.done_count}).`}
                    </div>
                    <${IconButton} icon="x" size="sm" label="Fechar" onClick=${() => setSuggestion(null)} />
                  </div>`
              : html`<${Button} size="sm" icon="wand" loading=${suggesting} onClick=${suggest}>Sugerir dificuldade e prazo<//>`}
          </div>`
        : null}
    </section>

    <section class="stack" style="gap:10px" aria-labelledby=${`steps-${task.id}`}>
      <div class="section-head">
        <h3 class="section-title" id=${`steps-${task.id}`}><${Icon} name="list" />Etapas <span class="counter">${task.steps.filter((s) => s.done).length}/${task.steps.length}</span></h3>
      </div>
      ${task.steps.length
        ? html`<div class="task-progress"><${Progress} value=${task.progress} done=${isDone(task)} /><span class="progress-label">${task.progress}%</span></div>`
        : null}
      <${StepsEditor}
        steps=${steps}
        readOnly=${readOnly}
        getContext=${() => ({ title: task.title, description: task.description })}
        onAdd=${(texts, source) => addSteps(accountId, task.id, texts, source)}
        onToggle=${(stepId, done) => toggleStep(accountId, task.id, stepId, done)}
        onRename=${(stepId, text) => renameStep(accountId, task.id, stepId, text)}
        onDelete=${(stepId) => deleteStep(accountId, task.id, stepId)}
        onReorder=${(order) => reorderSteps(accountId, task.id, order)}
      />
      ${!task.steps.length && readOnly ? html`<p class="small faint">Sem etapas.</p>` : null}
    </section>

    <section class="stack" style="gap:14px">
      <${Field} label="Descrição" id=${ids.desc}>
        ${readOnly
          ? html`<p class="small" style="white-space:pre-wrap">${task.description || "—"}</p>`
          : html`<${AutoText}
              id=${ids.desc}
              multiline
              rows=${3}
              value=${task.description}
              placeholder="Contexto, critérios de aceite…"
              draftKey=${`desc:${task.id}`}
              onSave=${(value) => updateTask(accountId, task.id, { description: value })}
            />`}
      <//>
      <${Field} label="Anotações" id=${ids.notes} hint=${readOnly ? null : "Registro livre durante a execução — salvo automaticamente."}>
        ${readOnly
          ? html`<p class="small" style="white-space:pre-wrap">${task.notes || "—"}</p>`
          : html`<${AutoText}
              id=${ids.notes}
              multiline
              rows=${4}
              value=${task.notes}
              placeholder="Decisões, pendências, contatos…"
              draftKey=${`notes:${task.id}`}
              onSave=${(value) => updateTask(accountId, task.id, { notes: value })}
            />`}
      <//>
    </section>

    <${LinksSection} task=${task} readOnly=${readOnly} />
    <${AttachmentsSection} task=${task} readOnly=${readOnly} />
    <${DueHistory} task=${task} />
    ${board?.can_comment ? html`<${Comments} task=${task} />` : null}
    <${Timeline} task=${task} />

    <section class="kv small" aria-label="Datas">
      <dt>Criada em</dt><dd class="mono">${fmtDateTime(task.created_at)}</dd>
      <dt>Concluída em</dt><dd class="mono">${task.completed_at ? fmtDateTime(task.completed_at) : "—"}</dd>
      <dt>Última atividade</dt><dd>${relativeTime(task.last_activity_at)}</dd>
      ${owner ? html`<dt>Conta</dt><dd class="row"><${Avatar} account=${owner} size="xs" />${owner.name}</dd>` : null}
    </section>

    ${postpone
      ? html`<${PostponeModal}
          oldDue=${postpone.oldDue}
          newDue=${postpone.newDue}
          onClose=${() => setPostpone(null)}
          onConfirm=${(reason, text) => {
            updateTask(accountId, task.id, { due_date: postpone.newDue, due_reason: reason, due_reason_text: text });
            setPostpone(null);
          }}
        />`
      : null}
  `;
}

function LinksSection({ task, readOnly }) {
  const [url, setUrl] = useState("");
  const add = () => {
    const clean = url.trim();
    if (!clean) return;
    const normalized = /^[a-z][a-z0-9+.-]*:/i.test(clean) ? clean : `https://${clean}`;
    if (!/^(https?:\/\/|mailto:)[^\s<>"'`]+$/i.test(normalized)) {
      toast("URL inválida: use http://, https:// ou mailto:.", "error");
      return;
    }
    if (task.links.includes(normalized)) {
      setUrl("");
      return;
    }
    updateTask(task.account_id, task.id, { links: [...task.links, normalized] });
    setUrl("");
  };
  if (readOnly && !task.links.length) return null;
  return html`<section class="stack" style="gap:8px">
    <h3 class="section-title"><${Icon} name="link" />Links</h3>
    <ul class="list">
      ${task.links.map(
        (link) => html`<li key=${link} class="list-item">
          <${Icon} name=${link.startsWith("mailto:") ? "mail" : "external"} />
          <a class="grow truncate" href=${link} target="_blank" rel="noopener noreferrer">${hostOf(link)}</a>
          ${!readOnly
            ? html`<${IconButton}
                icon="x"
                size="sm"
                danger
                label=${`Remover link ${hostOf(link)}`}
                onClick=${() => updateTask(task.account_id, task.id, { links: task.links.filter((l) => l !== link) })}
              />`
            : null}
        </li>`,
      )}
    </ul>
    ${!readOnly
      ? html`<div class="row">
          <input
            class="input"
            type="url"
            placeholder="https://…"
            aria-label="Novo link"
            value=${url}
            onInput=${(e) => setUrl(e.currentTarget.value)}
            onKeyDown=${(e) => e.key === "Enter" && (e.preventDefault(), add())}
          />
          <${Button} icon="plus" onClick=${add} disabled=${!url.trim()}>Link<//>
        </div>`
      : null}
  </section>`;
}

function AttachmentsSection({ task, readOnly }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const online = useStore((s) => s.online);
  const maxMb = useStore((s) => s.meta?.max_upload_mb || 20);
  if (readOnly && !task.attachments.length) return null;
  const onFiles = async (event) => {
    const files = [...event.currentTarget.files];
    event.currentTarget.value = "";
    setBusy(true);
    for (const file of files) {
      if (file.size > maxMb * 1024 * 1024) {
        toast(`“${file.name}” excede ${maxMb} MB.`, "error");
        continue;
      }
      try {
        await uploadAttachment(task.account_id, task.id, file);
      } catch (error) {
        toast(error.message || "Não foi possível enviar o anexo.", "error");
      }
    }
    setBusy(false);
  };
  return html`<section class="stack" style="gap:8px">
    <div class="section-head">
      <h3 class="section-title"><${Icon} name="paperclip" />Anexos</h3>
      <div class="grow"></div>
      ${!readOnly
        ? html`<${Button}
            size="sm"
            icon="upload"
            loading=${busy}
            disabled=${!online}
            title=${online ? `Até ${maxMb} MB por arquivo` : "Anexos exigem conexão"}
            onClick=${() => inputRef.current?.click()}
            >Anexar<//
          >
          <input ref=${inputRef} type="file" multiple hidden onChange=${onFiles} />`
        : null}
    </div>
    ${task.attachments.length
      ? html`<ul class="list">
          ${task.attachments.map(
            (file) => html`<li key=${file.id} class="list-item">
              <${Icon} name="file" />
              <a class="grow truncate" href=${`/api/attachments/${file.id}`} target="_blank" rel="noopener" download=${file.filename}>${file.filename}</a>
              <span class="xsmall faint mono">${fmtSize(file.size)}</span>
              ${!readOnly
                ? html`<${IconButton}
                    icon="trash"
                    size="sm"
                    danger
                    label=${`Remover anexo ${file.filename}`}
                    onClick=${async () => {
                      const ok = await confirmDialog({ title: "Remover anexo?", text: `“${file.filename}” será excluído.`, confirmLabel: "Remover", danger: true });
                      if (ok) deleteAttachment(task.account_id, task.id, file.id);
                    }}
                  />`
                : null}
            </li>`,
          )}
        </ul>`
      : html`<p class="small faint">Nenhum anexo.</p>`}
  </section>`;
}

function DueHistory({ task }) {
  if (!task.due_history?.length) return null;
  const kinds = { adiamento: "Adiada", antecipacao: "Antecipada", definicao: "Definida", remocao: "Removida" };
  return html`<section class="stack" style="gap:8px">
    <h3 class="section-title"><${Icon} name="calendar" />Histórico de prazos</h3>
    <table class="data-table">
      <thead>
        <tr><th>Quando</th><th>Mudança</th><th>De → para</th><th>Motivo</th></tr>
      </thead>
      <tbody>
        ${[...task.due_history].reverse().map(
          (entry, index) => html`<tr key=${index}>
            <td class="mono">${fmtDateTime(entry.at)}</td>
            <td>${kinds[entry.kind] || entry.kind}</td>
            <td class="mono">${entry.old ? fmtDate(entry.old) : "—"} → ${entry.new ? fmtDate(entry.new) : "—"}</td>
            <td>${entry.reason ? REASON_LABEL[entry.reason] : "—"}${entry.reason_text ? `: ${entry.reason_text}` : ""}</td>
          </tr>`,
        )}
      </tbody>
    </table>
  </section>`;
}

function Comments({ task }) {
  const meId = useStore((s) => s.meId);
  const online = useStore((s) => s.online);
  const [comments, setComments] = useState(null);
  const [error, setError] = useState(null);
  const draftKey = `comment:${task.id}`;
  const [text, setText] = useState(() => loadDraft(draftKey) || "");
  const [sending, setSending] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = () =>
    loadComments(task.id)
      .then((list) => {
        setComments(list);
        setError(null);
      })
      .catch((err) => setError(err.message || "Sem conexão: comentários indisponíveis offline."));

  useEffect(() => {
    load();
    markCommentsRead(task.account_id, task.id);
  }, [task.id, task.comments?.total]);

  const send = async () => {
    const body = text.trim();
    if (!body) return;
    setSending(true);
    try {
      const comment = await addComment(task.account_id, task.id, body);
      setComments((list) => [...(list || []), comment]);
      setText("");
      clearDraft(draftKey);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSending(false);
    }
  };

  const saveEdit = async (comment) => {
    const body = editing.text.trim();
    if (!body || body === comment.text) {
      setEditing(null);
      return;
    }
    try {
      const updated = await editComment(task.account_id, comment.id, body);
      setComments((list) => list.map((c) => (c.id === comment.id ? updated : c)));
      setEditing(null);
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const remove = async (comment) => {
    const ok = await confirmDialog({ title: "Excluir comentário?", text: "Esta ação não pode ser desfeita.", confirmLabel: "Excluir", danger: true });
    if (!ok) return;
    await deleteComment(task.account_id, task.id, comment.id);
    setComments((list) => list.filter((c) => c.id !== comment.id));
  };

  return html`<section class="stack" style="gap:10px" aria-labelledby=${`comments-${task.id}`}>
    <h3 class="section-title" id=${`comments-${task.id}`}>
      <${Icon} name="message" />Comentários ${comments ? html`<span class="counter">${comments.length}</span>` : null}
    </h3>
    <p class="xsmall faint">Visíveis somente para o Gestor e para o responsável pela tarefa.</p>
    ${error ? html`<p class="small faint">${error}</p>` : null}
    ${comments === null && !error ? html`<div class="skeleton" style="height:60px"></div>` : null}
    ${comments?.length === 0 ? html`<p class="small faint">Nenhum comentário ainda.</p>` : null}
    <div class="comments">
      ${(comments || []).map((comment) => {
        const mine = comment.author_id === meId;
        const author = (getState().accounts || []).find((a) => a.id === comment.author_id);
        return html`<div key=${comment.id} class=${cx("comment", mine && "mine")}>
          ${author ? html`<${Avatar} account=${author} size="sm" />` : html`<span class="avatar sm">?</span>`}
          <div class="comment-bubble">
            <div class="comment-head">
              <strong>${comment.author_name}</strong>
              <span class="mono">${fmtDateTime(comment.created_at)}</span>
              ${comment.edited_at ? html`<span>(editado)</span>` : null}
              <div class="grow"></div>
              ${mine && editing?.id !== comment.id
                ? html`<${IconButton} icon="edit" size="sm" label="Editar comentário" onClick=${() => setEditing({ id: comment.id, text: comment.text })} />
                    <${IconButton} icon="trash" size="sm" danger label="Excluir comentário" onClick=${() => remove(comment)} />`
                : null}
            </div>
            ${editing?.id === comment.id
              ? html`<div class="stack" style="gap:6px">
                  <textarea
                    class="textarea"
                    rows="3"
                    value=${editing.text}
                    aria-label="Editar comentário"
                    onInput=${(e) => setEditing({ ...editing, text: e.currentTarget.value })}
                  ></textarea>
                  <div class="row" style="justify-content:flex-end">
                    <${Button} size="sm" variant="ghost" onClick=${() => setEditing(null)}>Cancelar<//>
                    <${Button} size="sm" variant="primary" onClick=${() => saveEdit(comment)}>Salvar<//>
                  </div>
                </div>`
              : html`<div class="comment-text">${comment.text}</div>`}
          </div>
        </div>`;
      })}
    </div>
    <div class="stack" style="gap:6px">
      <textarea
        class="textarea"
        rows="2"
        placeholder=${online ? "Escreva um comentário… (Ctrl+Enter envia)" : "Sem conexão: o rascunho fica salvo no dispositivo."}
        aria-label="Novo comentário"
        value=${text}
        maxLength="5000"
        onInput=${(e) => {
          setText(e.currentTarget.value);
          saveDraft(draftKey, e.currentTarget.value);
        }}
        onKeyDown=${(e) => e.key === "Enter" && (e.ctrlKey || e.metaKey) && (e.preventDefault(), send())}
      ></textarea>
      <div class="row" style="justify-content:flex-end">
        <${Button} size="sm" variant="primary" icon="send" loading=${sending} disabled=${!text.trim() || !online} onClick=${send}>Comentar<//>
      </div>
    </div>
  </section>`;
}

const TIMELINE_CLASS = {
  done: "done",
  check: "done",
  postpone: "postpone",
  phase: "phase",
};

function Timeline({ task }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const stamp = task.last_activity_at;

  useEffect(() => {
    if (!open) return;
    api
      .get(`/api/tasks/${task.id}/timeline`)
      .then((list) => {
        setItems(list);
        setError(null);
      })
      .catch(() => setError("Linha do tempo indisponível offline."));
  }, [open, task.id, stamp]);

  return html`<section class="stack" style="gap:10px">
    <button type="button" class="section-head" style="background:none;border:0;padding:0;color:inherit" aria-expanded=${open ? "true" : "false"} onClick=${() => setOpen((v) => !v)}>
      <h3 class="section-title"><${Icon} name="history" />Linha do tempo</h3>
      <div class="grow"></div>
      <${Icon} name=${open ? "chevronUp" : "chevronDown"} size=${16} />
    </button>
    ${open
      ? error
        ? html`<p class="small faint">${error}</p>`
        : !items
          ? html`<div class="skeleton" style="height:80px"></div>`
          : html`<ol class="timeline">
              ${items.map(
                (item) => html`<li key=${item.seq} class=${cx("timeline-item", TIMELINE_CLASS[item.icon])}>
                  <div>${item.text}${item.count > 1 && !item.text.startsWith(String(item.count)) ? html` <span class="faint">(${item.count}×)</span>` : null}</div>
                  ${item.detail ? html`<div class="small muted">${item.detail}</div>` : null}
                  <div class="timeline-meta">${item.actor_name} · <span class="mono">${fmtDateTime(item.at)}</span></div>
                </li>`,
              )}
            </ol>`
      : null}
  </section>`;
}
