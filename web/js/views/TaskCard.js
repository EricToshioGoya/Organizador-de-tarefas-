// Cartão de tarefa (RF13, RF15, RF45, RF49, RF58, RF65, RF67) com marcação direta (RF40).
import { html, cx } from "../lib/html.js";
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "../ui/icons.js";
import { Checkbox, DifficultyBadge, PhaseBadge, PriorityBadge, StatusBadge, Progress, Badge, IconButton, priorityText } from "../ui/core.js";
import { AutoText } from "../ui/forms.js";
import { Menu } from "../ui/overlay.js";
import { dueLabel, todayISO, fmtDate, plural } from "../lib/format.js";
import {
  isOverdue,
  isDueSoon,
  isStale,
  isDone,
  nextStep,
  orderedSteps,
  overdueDays,
  priorityOf,
  DIFFICULTIES,
  DIFFICULTY_COLOR,
  DIFFICULTY_LABEL,
  staleDaysOf,
  PHASES,
  PHASE_COLOR,
  PHASE_LABEL,
  PRIORITIES,
  PRIORITY_COLOR,
  PRIORITY_LABEL,
} from "../lib/rules.js";
import { setTaskDone, toggleStep, confirmDialog, updateTask, deleteTask, addSteps, deleteStep, reorderSteps } from "../actions.js";
import { useReorder } from "../lib/reorder.js";
import { setState } from "../lib/store.js";

export function openTask(task) {
  setState({ drawer: { taskId: task.id, accountId: task.account_id } });
}

function PhasePicker({ task, readOnly }) {
  if (readOnly) return html`<${PhaseBadge} value=${task.phase} short />`;
  const current = PHASES.find((p) => p.key === task.phase);
  return html`<${Menu}
    align="left"
    header=${html`<div class="menu-header xsmall faint">Mudar fase</div>`}
    trigger=${(props) => html`<button
      type="button"
      class=${cx("badge", "badge-btn", `phase-${task.phase}`)}
      title="Alterar fase"
      aria-label=${`Fase: ${PHASE_LABEL[task.phase]}. Alterar fase`}
      aria-haspopup=${props["aria-haspopup"]}
      aria-expanded=${props["aria-expanded"]}
      onClick=${props.toggle}
    >
      <span class="dot" aria-hidden="true"></span>${current?.short}<${Icon} name="chevronDown" />
    </button>`}
    items=${PHASES.map((p) => ({
      label: p.label,
      dot: PHASE_COLOR[p.key],
      checked: p.key === task.phase,
      onClick: () => p.key !== task.phase && updateTask(task.account_id, task.id, { phase: p.key }),
    }))}
  />`;
}

function PriorityPicker({ task, readOnly }) {
  const current = priorityOf(task);
  if (readOnly) return html`<${PriorityBadge} value=${current} />`;
  return html`<${Menu}
    align="left"
    header=${html`<div class="menu-header xsmall faint">Mudar prioridade</div>`}
    trigger=${(props) => html`<button
      type="button"
      class=${cx("badge", "badge-btn", `prio-${current}`)}
      title="Alterar prioridade"
      aria-label=${`Prioridade: ${PRIORITY_LABEL[current]}. Alterar prioridade`}
      aria-haspopup=${props["aria-haspopup"]}
      aria-expanded=${props["aria-expanded"]}
      onClick=${props.toggle}
    >
      <${Icon} name="flag" class="prio-flag" />${priorityText(current)}<${Icon} name="chevronDown" />
    </button>`}
    items=${[...PRIORITIES].reverse().map((p) => ({
      label: p.label,
      dot: PRIORITY_COLOR[p.key],
      checked: p.key === current,
      onClick: () => p.key !== current && updateTask(task.account_id, task.id, { priority: p.key }),
    }))}
  />`;
}

function DifficultyPicker({ task, readOnly }) {
  if (readOnly) return html`<${DifficultyBadge} value=${task.difficulty} />`;
  return html`<${Menu}
    align="left"
    header=${html`<div class="menu-header xsmall faint">Mudar dificuldade</div>`}
    trigger=${(props) => html`<button
      type="button"
      class=${cx("badge", "badge-btn", `diff-${task.difficulty}`)}
      title="Alterar dificuldade"
      aria-label=${`Dificuldade: ${DIFFICULTY_LABEL[task.difficulty]}. Alterar dificuldade`}
      aria-haspopup=${props["aria-haspopup"]}
      aria-expanded=${props["aria-expanded"]}
      onClick=${props.toggle}
    >
      <span class="dot" aria-hidden="true"></span>${DIFFICULTY_LABEL[task.difficulty]}<${Icon} name="chevronDown" />
    </button>`}
    items=${DIFFICULTIES.map((d) => ({
      label: d.label,
      dot: DIFFICULTY_COLOR[d.key],
      checked: d.key === task.difficulty,
      onClick: () => d.key !== task.difficulty && updateTask(task.account_id, task.id, { difficulty: d.key }),
    }))}
  />`;
}

/** Descrição no cartão: prévia de 2 linhas com "Ver mais"; um clique abre a edição ali mesmo (salva sozinha). */
function TaskDescription({ task, readOnly, editing, setEditing }) {
  const [open, setOpen] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const textRef = useRef(null);
  const editorRef = useRef(null);
  const text = task.description || "";

  useEffect(() => {
    const el = textRef.current;
    if (!el || open) return undefined;
    const check = () => setOverflow(el.scrollHeight > el.clientHeight + 1);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, open, editing]);

  useEffect(() => {
    const field = editing && editorRef.current?.querySelector("textarea");
    if (!field) return;
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
  }, [editing]);

  // Chaves distintas: se o Preact reaproveitasse a <div> da prévia, o foco saindo dela (removida) fecharia o editor.
  if (editing && !readOnly) {
    return html`<div
      key="editor"
      class="task-desc-editor"
      ref=${editorRef}
      onFocusOut=${(e) => !e.currentTarget.contains(e.relatedTarget) && setEditing(false)}
      onKeyDown=${(e) => e.key === "Escape" && e.target.blur()}
    >
      <${AutoText}
        multiline
        rows=${3}
        value=${text}
        ariaLabel=${`Descrição de ${task.title}`}
        placeholder="Contexto, critérios de aceite…"
        draftKey=${`desc:${task.id}`}
        onSave=${(value) => updateTask(task.account_id, task.id, { description: value })}
      />
    </div>`;
  }
  if (!text.trim()) return null;
  const edit = () => setEditing(true);
  return html`<div key="preview" class="task-desc">
    <div
      ref=${textRef}
      class=${cx("task-desc-text", !open && "clamped", !readOnly && "editable")}
      role=${readOnly ? undefined : "button"}
      tabIndex=${readOnly ? undefined : 0}
      title=${readOnly ? undefined : "Editar descrição"}
      onClick=${readOnly ? undefined : edit}
      onKeyDown=${readOnly
        ? undefined
        : (e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            edit();
          }}
    >${text}</div>
    ${open || overflow
      ? html`<button type="button" class="task-desc-toggle" aria-expanded=${open ? "true" : "false"} onClick=${() => setOpen(!open)}>
          ${open ? "Ver menos" : "Ver mais"}
        </button>`
      : null}
  </div>`;
}

export function TaskCard({ task, readOnly, staleDays = 5, goals, showSteps = false, compact = false }) {
  const [completing, setCompleting] = useState(false);
  const [expanded, setExpanded] = useState(showSteps);
  const [newStep, setNewStep] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const today = todayISO();
  const overdue = isOverdue(task, today);
  const soon = !overdue && isDueSoon(task, today);
  const stale = isStale(task, staleDays);
  const done = isDone(task);
  const next = nextStep(task);
  const goal = goals?.find((g) => g.id === task.goal_id);
  const isNew = !!task.assigned_by && !task.assigned_seen_at && !readOnly;
  const unread = task.comments?.unread || 0;
  const hasDesc = !!task.description?.trim();
  const sortedSteps = orderedSteps(task.steps);
  const { listProps, handleProps, rowState } = useReorder(
    sortedSteps.map((s) => s.id),
    (order) => reorderSteps(task.account_id, task.id, order),
    readOnly,
  );

  const toggleTask = async (checked) => {
    if (readOnly) return;
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
      openTask(task);
      return;
    }
    if (checked) {
      setCompleting(true); // RF16: animação antes de mudar de seção
      setTimeout(() => setTaskDone(task.account_id, task.id, true), 280);
    } else {
      setTaskDone(task.account_id, task.id, false);
    }
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

  const checkboxLabel = done
    ? task.steps.length
      ? "Concluída — desmarque uma etapa para reabrir"
      : "Reabrir tarefa"
    : "Concluir tarefa";

  return html`<article
    class=${cx("task-card", {
      "is-overdue": overdue,
      "is-soon": soon,
      "is-done": done,
      "is-new": isNew,
      completing,
    })}
    aria-label=${task.title}
  >
    <${Checkbox} checked=${done} onChange=${toggleTask} label=${checkboxLabel} disabled=${readOnly} round />
    <div class="task-main">
      <div class="task-title-row">
        <button type="button" class="task-title" onClick=${() => openTask(task)}>${task.title}</button>
        ${isNew ? html`<span class="badge badge-new" title=${`Atribuída por ${task.assigned_by_name}`}>Nova</span>` : null}
        ${unread
          ? html`<${Badge} tone="accent" icon="message" title=${`${unread} comentário(s) não lido(s)`}>${unread}<//>`
          : null}
        ${!readOnly ? html`<${IconButton} icon="trash" size="sm" danger label="Excluir tarefa" onClick=${remove} />` : null}
      </div>

      <${TaskDescription} task=${task} readOnly=${readOnly} editing=${editingDesc} setEditing=${setEditingDesc} />

      <div class="task-meta">
        <${PriorityPicker} task=${task} readOnly=${readOnly} />
        <${DifficultyPicker} task=${task} readOnly=${readOnly} />
        ${!compact ? html`<${PhasePicker} task=${task} readOnly=${readOnly} />` : null}
        ${overdue
          ? html`<${StatusBadge} kind="critical" icon="alert">Atrasada há ${plural(overdueDays(task, today), "dia", "dias")}<//>`
          : soon
            ? html`<${StatusBadge} kind="warning" icon="clock">${dueLabel(task.due_date, today) === "Hoje" ? "Vence hoje" : `Vence ${dueLabel(task.due_date, today).toLowerCase()}`}<//>`
            : task.due_date
              ? html`<span class="meta-item" title=${`Entrega: ${fmtDate(task.due_date)}`}>
                  <${Icon} name="calendar" />${done ? `Entrega ${fmtDate(task.due_date)}` : dueLabel(task.due_date, today)}
                </span>`
              : null}
        ${stale && !compact
          ? html`<${StatusBadge} kind="serious" icon="pause" title="Sem atividade recente">Parada há ${plural(staleDaysOf(task), "dia", "dias")}<//>`
          : null}
        ${task.requester ? html`<span class="meta-item" title="Solicitante"><${Icon} name="user" />${task.requester}</span>` : null}
        ${goal && !compact ? html`<span class="meta-item" title="Meta"><${Icon} name="target" />${goal.title}</span>` : null}
        ${task.attachments?.length ? html`<span class="meta-item" title="Anexos"><${Icon} name="paperclip" />${task.attachments.length}</span>` : null}
        ${task.links?.length ? html`<span class="meta-item" title="Links"><${Icon} name="link" />${task.links.length}</span>` : null}
        ${done && task.completed_at ? html`<span class="meta-item"><${Icon} name="checkCircle" />Concluída em ${fmtDate(task.completed_at.slice(0, 10))}</span>` : null}
      </div>

      ${task.steps.length
        ? html`<div class="task-progress">
            <${Progress} value=${task.progress} done=${done} label=${`Progresso de ${task.title}`} />
            <span class="progress-label">${task.steps.filter((s) => s.done).length}/${task.steps.length}</span>
            <button
              type="button"
              class="icon-btn sm"
              aria-expanded=${expanded ? "true" : "false"}
              aria-label=${expanded ? "Ocultar etapas" : "Mostrar etapas"}
              title=${expanded ? "Ocultar etapas" : "Mostrar etapas"}
              onClick=${() => setExpanded((v) => !v)}
            >
              <${Icon} name=${expanded ? "chevronUp" : "chevronDown"} size=${16} />
            </button>
          </div>`
        : null}

      ${next && !expanded && !done
        ? html`<div class="next-step">
            <${Checkbox}
              size="sm"
              checked=${false}
              disabled=${readOnly}
              label=${`Concluir etapa: ${next.text}`}
              onChange=${() => toggleStep(task.account_id, task.id, next.id, true)}
            />
            <span class="label">Próxima</span>
            <span class="truncate">${next.text}</span>
          </div>`
        : null}

      ${expanded
        ? html`<ul class="inline-steps" aria-label="Etapas" ...${listProps}>
            ${sortedSteps.map(
              (step) => html`<li key=${step.id} data-step=${step.id} class=${cx("step", step.done && "done", rowState(step.id))} style="min-height:32px">
                ${!readOnly && sortedSteps.length > 1
                  ? html`<button
                      type="button"
                      class="drag-handle"
                      aria-label=${`Reordenar: ${step.text}. Use as setas para cima e para baixo.`}
                      title="Arraste para reordenar (ou use as setas)"
                      ...${handleProps(step.id)}
                    >
                      <${Icon} name="grip" size=${16} />
                    </button>`
                  : null}
                <${Checkbox}
                  size="sm"
                  checked=${step.done}
                  disabled=${readOnly}
                  label=${step.done ? `Desmarcar: ${step.text}` : `Concluir: ${step.text}`}
                  onChange=${(value) => toggleStep(task.account_id, task.id, step.id, value)}
                />
                <span class="step-text">${step.text}</span>
                ${!readOnly
                  ? html`<${IconButton} icon="x" size="sm" class="step-remove" label=${`Remover etapa: ${step.text}`} onClick=${() => deleteStep(task.account_id, task.id, step.id)} />`
                  : null}
              </li>`,
            )}
            ${!readOnly
              ? html`<li class="step step-add">
                  <input
                    class="input"
                    placeholder="Adicionar etapa e pressionar Enter"
                    aria-label="Adicionar etapa"
                    maxLength=${500}
                    value=${newStep}
                    onInput=${(e) => setNewStep(e.currentTarget.value)}
                    onKeyDown=${(e) => {
                      if (e.key !== "Enter" || !newStep.trim()) return;
                      addSteps(task.account_id, task.id, [newStep.trim()]);
                      setNewStep("");
                    }}
                  />
                </li>`
              : null}
          </ul>`
        : null}

      ${!readOnly && !compact && ((!task.steps.length && !expanded) || (!hasDesc && !editingDesc))
        ? html`<div class="row">
            ${!task.steps.length && !expanded
              ? html`<button type="button" class="btn btn-ghost btn-sm" onClick=${() => setExpanded(true)}><${Icon} name="plus" size=${16} />Etapas</button>`
              : null}
            ${!hasDesc && !editingDesc
              ? html`<button type="button" class="btn btn-ghost btn-sm" onClick=${() => setEditingDesc(true)}><${Icon} name="plus" size=${16} />Descrição</button>`
              : null}
          </div>`
        : null}
    </div>
  </article>`;
}
