// Cartão de tarefa (RF13, RF15, RF45, RF49, RF58, RF65, RF67) com marcação direta (RF40).
import { html, cx } from "../lib/html.js";
import { useState } from "preact/hooks";
import { Icon } from "../ui/icons.js";
import { Checkbox, DifficultyBadge, PhaseBadge, StatusBadge, Progress, Badge, IconButton } from "../ui/core.js";
import { Menu } from "../ui/overlay.js";
import { dueLabel, todayISO, fmtDate, plural } from "../lib/format.js";
import { isOverdue, isDueSoon, isStale, isDone, nextStep, orderedSteps, overdueDays, staleDaysOf, PHASES, PHASE_COLOR, PHASE_LABEL } from "../lib/rules.js";
import { setTaskDone, toggleStep, confirmDialog, updateTask, deleteTask } from "../actions.js";
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

export function TaskCard({ task, readOnly, staleDays = 5, goals, showSteps = false, compact = false }) {
  const [completing, setCompleting] = useState(false);
  const [expanded, setExpanded] = useState(showSteps);
  const today = todayISO();
  const overdue = isOverdue(task, today);
  const soon = !overdue && isDueSoon(task, today);
  const stale = isStale(task, staleDays);
  const done = isDone(task);
  const next = nextStep(task);
  const goal = goals?.find((g) => g.id === task.goal_id);
  const isNew = !!task.assigned_by && !task.assigned_seen_at && !readOnly;
  const unread = task.comments?.unread || 0;

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

      <div class="task-meta">
        <${DifficultyBadge} value=${task.difficulty} />
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
        ? html`<ul class="inline-steps" aria-label="Etapas">
            ${orderedSteps(task.steps).map(
              (step) => html`<li key=${step.id} class=${cx("step", step.done && "done")} style="min-height:32px">
                <${Checkbox}
                  size="sm"
                  checked=${step.done}
                  disabled=${readOnly}
                  label=${step.done ? `Desmarcar: ${step.text}` : `Concluir: ${step.text}`}
                  onChange=${(value) => toggleStep(task.account_id, task.id, step.id, value)}
                />
                <span class="step-text">${step.text}</span>
              </li>`,
            )}
          </ul>`
        : null}
    </div>
  </article>`;
}
