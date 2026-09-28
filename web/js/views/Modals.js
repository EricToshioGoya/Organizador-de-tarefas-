// Modais globais: confirmação, revisão semanal (RF51), nova tarefa e nova meta.
import { html, cx } from "../lib/html.js";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Button } from "../ui/core.js";
import { Modal } from "../ui/overlay.js";
import { fmtDate, fmtNumber } from "../lib/format.js";
import { markReviewSeen } from "../actions.js";
import { TaskFormModal } from "./TaskForm.js";
import { GoalFormModal } from "./GoalsView.js";

export function ConfirmModal({ title, text, confirmLabel, danger, onResult }) {
  return html`<${Modal}
    title=${title}
    size="sm"
    icon=${danger ? "alert" : "info"}
    onClose=${() => onResult(false)}
    footer=${html`
      <${Button} variant="ghost" onClick=${() => onResult(false)}>Cancelar<//>
      <${Button} variant=${danger ? "danger" : "primary"} data-autofocus onClick=${() => onResult(true)}>${confirmLabel}<//>`}
  >
    <p class="muted">${text}</p>
  <//>`;
}

function ReviewStat({ label, icon, current, previous, better }) {
  const diff = current - previous;
  const good = better === "up" ? diff > 0 : diff < 0;
  return html`<div class="kpi">
    <span class="kpi-label"><${Icon} name=${icon} />${label}</span>
    <span class="kpi-value">${fmtNumber(current, 0)}</span>
    <span class=${cx("kpi-delta", diff !== 0 && (good ? "good" : "bad"))}>
      ${diff === 0 ? "igual à semana anterior" : html`<${Icon} name=${diff > 0 ? "arrowUp" : "arrowDown"} size=${12} />${diff > 0 ? "+" : "−"}${Math.abs(diff)} vs. semana anterior (${previous})`}
    </span>
  </div>`;
}

export function WeeklyReviewModal({ review, accountId }) {
  const summary = review.summary;
  const current = summary.current;
  const previous = summary.previous;
  const close = () => markReviewSeen(accountId, review.week_start);
  const list = (title, items) =>
    items.length
      ? html`<div>
          <div class="small muted" style="font-weight:600;margin-bottom:4px">${title}</div>
          <ul class="list">${items.map((t, i) => html`<li key=${i} class="list-item" style="padding:3px 0">• ${t}</li>`)}</ul>
        </div>`
      : null;
  return html`<${Modal}
    title=${`Revisão da semana · ${fmtDate(summary.week_start)} a ${fmtDate(summary.week_end)}`}
    icon="history"
    size="lg"
    soft
    onClose=${close}
    footer=${html`<${Button} variant="primary" icon="check" data-autofocus onClick=${close}>Começar a semana<//>`}
  >
    <p class="muted small" style="margin-bottom:14px">Resumo da semana anterior comparado à semana precedente. Fica guardado em Desempenho → Revisões semanais.</p>
    <div class="review-grid">
      <${ReviewStat} label="Concluídas" icon="checkCircle" current=${current.done} previous=${previous.done} better="up" />
      <${ReviewStat} label="Atrasadas" icon="alert" current=${current.late} previous=${previous.late} better="down" />
      <${ReviewStat} label="Adiamentos" icon="calendar" current=${current.postponed} previous=${previous.postponed} better="down" />
    </div>
    <p class="small muted" style="margin:14px 0">
      Pontos entregues: <strong class="mono">${current.points}</strong> (semana anterior: <span class="mono">${previous.points}</span>).
    </p>
    <div class="grid-2">
      ${list("Concluídas", current.done_titles)} ${list("Atrasadas", current.late_titles)} ${list("Adiadas", current.postponed_titles)}
    </div>
  <//>`;
}

/** Registro dos modais abertos via estado global (openModal). */
export function ModalHost() {
  const modal = useStore((s) => s.modal);
  if (!modal) return null;
  const { kind, props, key } = modal;
  switch (kind) {
    case "confirm":
      return html`<${ConfirmModal} key=${key} ...${props} />`;
    case "newTask":
      return html`<${TaskFormModal} key=${key} ...${props} />`;
    case "newGoal":
      return html`<${GoalFormModal} key=${key} ...${props} />`;
    case "weeklyReview":
      return html`<${WeeklyReviewModal} key=${key} ...${props} />`;
    default:
      return null;
  }
}
