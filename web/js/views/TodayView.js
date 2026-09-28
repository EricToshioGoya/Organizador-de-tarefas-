// Aba Hoje (RF38–RF40): Atrasadas, Vencem hoje e Top 3 do dia, com avisos de novas atribuições (RF65),
// comentários não lidos (RF67), tarefas paradas (RF49) e sobrecarga (RF50).
import { html } from "../lib/html.js";
import { useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Banner, Button, Checkbox, EmptyState, SectionTitle, Skeleton } from "../ui/core.js";
import { Modal } from "../ui/overlay.js";
import { TaskCard } from "./TaskCard.js";
import { fmtLongDate, fmtNumber, greeting, todayISO, dueLabel } from "../lib/format.js";
import { isOverdue, isPending, isStale, sortPending, top3Today } from "../lib/rules.js";
import { navigate, openModal, setTop3 } from "../actions.js";

function Top3Picker({ board, onClose }) {
  const today = todayISO();
  const current = top3Today(board, today);
  const [selected, setSelected] = useState(current);
  const pending = sortPending(board.tasks.filter(isPending));
  const toggle = (id) =>
    setSelected((list) => (list.includes(id) ? list.filter((x) => x !== id) : list.length >= 3 ? list : [...list, id]));
  return html`<${Modal}
    title="Top 3 do dia"
    icon="star"
    onClose=${onClose}
    footer=${html`
      <span class="small muted" style="margin-right:auto">${selected.length}/3 selecionadas</span>
      <${Button} variant="ghost" onClick=${onClose}>Cancelar<//>
      <${Button}
        variant="primary"
        icon="check"
        onClick=${() => {
          setTop3(board.account.id, selected);
          onClose();
        }}
        >Salvar Top 3<//
      >`}
  >
    <p class="muted small" style="margin-bottom:12px">Escolha até 3 tarefas pendentes para focar hoje. A seleção vale só para hoje.</p>
    ${pending.length
      ? html`<ul class="list" style="gap:6px">
          ${pending.map((task) => {
            const checked = selected.includes(task.id);
            const blocked = !checked && selected.length >= 3;
            return html`<li key=${task.id} class="list-item boxed" style=${blocked ? "opacity:0.55" : ""}>
              <${Checkbox} checked=${checked} disabled=${blocked} label=${checked ? `Remover do Top 3: ${task.title}` : `Adicionar ao Top 3: ${task.title}`} onChange=${() => toggle(task.id)} />
              <span class="grow">${task.title}</span>
              <span class="xsmall faint">${dueLabel(task.due_date)}</span>
            </li>`;
          })}
        </ul>`
      : html`<${EmptyState} compact icon="checkCircle" title="Nenhuma tarefa pendente" text="Crie uma tarefa para escolher o Top 3." />`}
  <//>`;
}

export function TodayView() {
  const board = useStore((s) => s.boards[s.meId]);
  const me = useStore((s) => (s.accounts || []).find((a) => a.id === s.meId));
  const [picker, setPicker] = useState(false);
  const today = todayISO();

  if (!board) return html`<div class="stack"><div class="skeleton" style="height:60px"></div><${Skeleton} count=${4} /></div>`;

  const staleDays = board.account.settings?.stale_days || 5;
  const pending = board.tasks.filter(isPending);
  const overdue = sortPending(pending.filter((t) => isOverdue(t, today)));
  const dueToday = sortPending(pending.filter((t) => t.due_date === today));
  const topIds = top3Today(board, today);
  const top = topIds.map((id) => board.tasks.find((t) => t.id === id)).filter(Boolean);
  const assigned = board.tasks.filter((t) => t.assigned_by && !t.assigned_seen_at);
  const unread = board.tasks.filter((t) => (t.comments?.unread || 0) > 0);
  const stale = pending.filter((t) => isStale(t, staleDays));
  const overload = board.overload;
  const allClear = !overdue.length && !dueToday.length && !top.length;
  const cardProps = { staleDays, goals: board.goals };

  return html`<div class="stack" style="gap:28px">
    <header class="page-head">
      <div>
        <h1 class="page-title">${greeting()}, ${me?.name?.split(" ")[0]}</h1>
        <p class="page-subtitle">${fmtLongDate(today)}</p>
      </div>
      <${Button} icon="star" onClick=${() => setPicker(true)}>Escolher Top 3<//>
    </header>

    ${overload?.overloaded
      ? html`<${Banner}
          tone="warning"
          icon="alert"
          action=${html`<${Button} size="sm" variant="ghost" onClick=${() => navigate("desempenho")}>Ver carga<//>`}
        >
          <strong>Sobrecarga:</strong> a carga da semana (${fmtNumber(overload.load)} pts) supera sua capacidade média
          (${fmtNumber(overload.capacity)} pts/semana).
        <//>`
      : null}
    ${stale.length
      ? html`<${Banner}
          tone="serious"
          icon="pause"
          action=${html`<${Button} size="sm" variant="ghost" onClick=${() => navigate("tarefas?filtro=paradas")}>Ver<//>`}
        >
          <strong>${stale.length} tarefa${stale.length > 1 ? "s" : ""} parada${stale.length > 1 ? "s" : ""}</strong>
          ${` sem atividade há mais de ${staleDays} dias.`}
        <//>`
      : null}

    ${assigned.length
      ? html`<section class="section">
          <${SectionTitle} icon="inbox" count=${assigned.length}>Novas tarefas atribuídas<//>
          <div class="task-list">${assigned.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} />`)}</div>
        </section>`
      : null}

    ${unread.length
      ? html`<section class="section">
          <${SectionTitle} icon="message" count=${unread.length}>Comentários não lidos<//>
          <div class="task-list">${unread.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} compact />`)}</div>
        </section>`
      : null}

    <section class="section" aria-label="Top 3 do dia">
      <${SectionTitle}
        icon="star"
        tone="star"
        count=${top.length}
        extra=${html`<${Button} size="sm" variant="ghost" icon="edit" onClick=${() => setPicker(true)}>${top.length ? "Alterar" : "Escolher"}<//>`}
        >Top 3 do dia<//
      >
      ${top.length
        ? html`<div class="task-list">${top.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} showSteps=${task.steps.length > 0 && task.steps.length <= 6} />`)}</div>`
        : html`<${EmptyState}
            compact
            icon="star"
            title="Escolha até 3 prioridades"
            text="O Top 3 ajuda a focar no que importa hoje. A seleção vale só para o dia."
            action=${html`<${Button} size="sm" icon="star" onClick=${() => setPicker(true)}>Escolher Top 3<//>`}
          />`}
    </section>

    <section class="section" aria-label="Atrasadas">
      <${SectionTitle} icon="alert" tone=${overdue.length ? "critical" : undefined} count=${overdue.length}>Atrasadas<//>
      ${overdue.length
        ? html`<div class="task-list">${overdue.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} />`)}</div>`
        : html`<p class="small faint">Nenhuma tarefa atrasada. Ótimo trabalho!</p>`}
    </section>

    <section class="section" aria-label="Vencem hoje">
      <${SectionTitle} icon="clock" tone=${dueToday.length ? "warning" : undefined} count=${dueToday.length}>Vencem hoje<//>
      ${dueToday.length
        ? html`<div class="task-list">${dueToday.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} />`)}</div>`
        : html`<p class="small faint">Nada vence hoje.</p>`}
    </section>

    ${allClear && !pending.length
      ? html`<${EmptyState}
          icon="sparkles"
          title="Tudo em dia"
          text="Crie uma tarefa com o botão “Nova tarefa” ou use a criação rápida na aba Tarefas (ex.: “Apresentação sexta difícil @Carlos”)."
          action=${html`<${Button} variant="primary" icon="plus" onClick=${() => openModal("newTask", {})}>Nova tarefa<//>`}
        />`
      : null}

    ${picker ? html`<${Top3Picker} board=${board} onClose=${() => setPicker(false)} />` : null}
  </div>`;
}
