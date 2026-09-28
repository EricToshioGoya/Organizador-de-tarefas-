// Aba Metas (RF29–RF33): cartões com progresso e destaque de atraso, detalhe com tarefas vinculadas,
// criação, edição, exclusão (mantendo as tarefas — RN17) e vínculo de tarefas (RF30).
import { html, cx } from "../lib/html.js";
import { useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Badge, Button, Checkbox, EmptyState, IconButton, Progress, Skeleton, StatusBadge } from "../ui/core.js";
import { Modal, Menu } from "../ui/overlay.js";
import { AutoText, DateInput, Field, useFieldId } from "../ui/forms.js";
import { TaskSections } from "./TasksView.js";
import { fmtDate, plural, todayISO, dueLabel } from "../lib/format.js";
import { TITLE_MAX, goalOverdue, isPending, sortPending } from "../lib/rules.js";
import { closeModal, confirmDialog, createGoal, deleteGoal, linkTasks, navigate, openModal, updateGoal, updateTask } from "../actions.js";

export function GoalFormModal({ accountId }) {
  const board = useStore((s) => s.boards[accountId]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [target, setTarget] = useState(null);
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState(null);
  const ids = { title: useFieldId("gt"), desc: useFieldId("gd"), date: useFieldId("gdate") };
  const available = sortPending((board?.tasks || []).filter((t) => !t.goal_id && isPending(t)));

  const submit = () => {
    if (!title.trim()) {
      setError("O título é obrigatório.");
      return;
    }
    createGoal(accountId, { title: title.trim(), description, target_date: target, task_ids: selected });
    closeModal();
  };

  return html`<${Modal}
    title="Nova meta"
    icon="target"
    onClose=${closeModal}
    footer=${html`<${Button} variant="ghost" onClick=${closeModal}>Cancelar<//><${Button} variant="primary" icon="check" onClick=${submit}>Criar meta<//>`}
  >
    <form class="stack" style="gap:14px" onSubmit=${(e) => (e.preventDefault(), submit())}>
      <${Field} label="Título" required id=${ids.title} error=${error} hint="Ex.: Passar em Cálculo">
        <input id=${ids.title} class="input" data-autofocus maxLength=${TITLE_MAX} value=${title} onInput=${(e) => (setTitle(e.currentTarget.value), setError(null))} />
      <//>
      <${Field} label="Descrição" id=${ids.desc}>
        <textarea id=${ids.desc} class="textarea" rows="2" value=${description} onInput=${(e) => setDescription(e.currentTarget.value)}></textarea>
      <//>
      <${Field} label="Data-alvo" id=${ids.date} hint="Opcional. Base do destaque de meta atrasada.">
        <${DateInput} id=${ids.date} value=${target} onChange=${setTarget} />
      <//>
      ${available.length
        ? html`<${Field} label="Vincular tarefas pendentes (opcional)">
            <ul class="list" style="max-height:220px;overflow:auto">
              ${available.map(
                (task) => html`<li key=${task.id} class="list-item">
                  <${Checkbox}
                    size="sm"
                    checked=${selected.includes(task.id)}
                    label=${`Vincular ${task.title}`}
                    onChange=${(on) => setSelected(on ? [...selected, task.id] : selected.filter((id) => id !== task.id))}
                  />
                  <span class="grow">${task.title}</span>
                  <span class="xsmall faint">${dueLabel(task.due_date)}</span>
                </li>`,
              )}
            </ul>
          <//>`
        : null}
      <button type="submit" hidden>Criar</button>
    </form>
  <//>`;
}

export function GoalCard({ goal, onOpen }) {
  const today = todayISO();
  const overdue = goalOverdue(goal, today);
  const done = goal.status === "concluida";
  return html`<button type="button" class=${cx("goal-card", overdue && "is-overdue", done && "is-done")} onClick=${onOpen} aria-label=${`Meta ${goal.title}`}>
    <div class="row" style="align-items:flex-start">
      <div class="goal-title grow">${goal.title}</div>
      ${done
        ? html`<${StatusBadge} kind="good" icon="checkCircle">Concluída<//>`
        : overdue
          ? html`<${StatusBadge} kind="critical" icon="alert">Atrasada<//>`
          : null}
    </div>
    <div class="goal-stats">
      <span class="goal-pct">${goal.progress}%</span>
      <span class="small muted"><span class="mono">${goal.done_tasks}/${goal.total_tasks}</span> tarefas concluídas</span>
    </div>
    <${Progress} value=${goal.progress} done=${done} label=${`Progresso da meta ${goal.title}`} />
    <div class="row small muted">
      <${Icon} name="calendar" size=${15} />
      ${goal.target_date ? html`Data-alvo: <span class="mono">${fmtDate(goal.target_date)}</span>` : "Sem data-alvo"}
    </div>
  </button>`;
}

export function GoalsList({ board, readOnly, onOpen }) {
  const active = board.goals.filter((g) => g.status === "andamento");
  const done = board.goals.filter((g) => g.status === "concluida");
  if (!board.goals.length) {
    return html`<${EmptyState}
      icon="target"
      title=${readOnly ? "Nenhuma meta" : "Crie sua primeira meta"}
      text=${readOnly ? "Esta conta ainda não tem metas." : "Metas agrupam tarefas e medem o progresso pelas tarefas concluídas. Ex.: “Passar em Cálculo”."}
      action=${readOnly ? null : html`<${Button} variant="primary" icon="plus" onClick=${() => openModal("newGoal", { accountId: board.account.id })}>Nova meta<//>`}
    />`;
  }
  return html`<div class="stack" style="gap:24px">
    <section class="section">
      <div class="section-head"><h2 class="section-title"><${Icon} name="target" />Em andamento <span class="counter">${active.length}</span></h2></div>
      ${active.length
        ? html`<div class="grid-cards">${active.map((goal) => html`<${GoalCard} key=${goal.id} goal=${goal} onOpen=${() => onOpen(goal)} />`)}</div>`
        : html`<p class="small faint">Nenhuma meta em andamento.</p>`}
    </section>
    ${done.length
      ? html`<section class="section">
          <div class="section-head"><h2 class="section-title tone-good"><${Icon} name="checkCircle" />Concluídas <span class="counter">${done.length}</span></h2></div>
          <div class="grid-cards">${done.map((goal) => html`<${GoalCard} key=${goal.id} goal=${goal} onOpen=${() => onOpen(goal)} />`)}</div>
        </section>`
      : null}
  </div>`;
}

export function GoalsView() {
  const board = useStore((s) => s.boards[s.meId]);
  if (!board) return html`<${Skeleton} count=${3} height=${150} />`;
  return html`<div class="stack" style="gap:20px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Metas</h1>
        <p class="page-subtitle">Objetivos que agrupam tarefas; o progresso é medido pelas tarefas concluídas.</p>
      </div>
      <${Button} variant="primary" icon="plus" onClick=${() => openModal("newGoal", { accountId: board.account.id })}>Nova meta<//>
    </header>
    <${GoalsList} board=${board} onOpen=${(goal) => navigate(`metas/${goal.id}`)} />
  </div>`;
}

/** Detalhe da meta (RF33): tarefas vinculadas em Pendentes e Concluídas. */
export function GoalDetailView({ goalId, accountId: forcedAccount, readOnly: forcedReadOnly }) {
  const meId = useStore((s) => s.meId);
  const accountId = forcedAccount || meId;
  const board = useStore((s) => s.boards[accountId]);
  const [linking, setLinking] = useState(false);
  const ids = { desc: useFieldId("gdesc"), date: useFieldId("gdate"), title: useFieldId("gtitle") };
  if (!board) return html`<${Skeleton} count=${3} />`;
  const goal = board.goals.find((g) => g.id === goalId);
  if (!goal) {
    return html`<${EmptyState} icon="target" title="Meta não encontrada" text="Ela pode ter sido excluída." action=${html`<${Button} onClick=${() => navigate("metas")}>Voltar para Metas<//>`} />`;
  }
  const readOnly = forcedReadOnly ?? accountId !== meId;
  const tasks = board.tasks.filter((t) => t.goal_id === goal.id);
  const overdue = goalOverdue(goal);
  const staleDays = board.account.settings?.stale_days || 5;

  const remove = async () => {
    const ok = await confirmDialog({
      title: "Excluir meta?",
      text: `A meta “${goal.title}” será excluída. As ${plural(tasks.length, "tarefa vinculada", "tarefas vinculadas")} continuam existindo, sem meta.`,
      confirmLabel: "Excluir meta",
      danger: true,
    });
    if (ok) {
      deleteGoal(accountId, goal.id);
      navigate("metas");
    }
  };

  return html`<div class="stack" style="gap:22px">
    <div>
      <${Button} variant="ghost" size="sm" icon="arrowLeft" onClick=${() => history.back()}>Voltar<//>
    </div>
    <section class="panel stack" style="gap:14px">
      <div class="row" style="align-items:flex-start">
        <div class="grow">
          ${readOnly
            ? html`<h1 class="page-title">${goal.title}</h1>`
            : html`<${AutoText}
                id=${ids.title}
                value=${goal.title}
                ariaLabel="Título da meta"
                inputClass="input-inline input-title"
                maxLength=${TITLE_MAX}
                validate=${(v) => (!v.trim() ? "O título é obrigatório." : null)}
                onSave=${(v) => updateGoal(accountId, goal.id, { title: v.trim() })}
              />`}
        </div>
        ${goal.status === "concluida"
          ? html`<${StatusBadge} kind="good" icon="checkCircle">Concluída<//>`
          : overdue
            ? html`<${StatusBadge} kind="critical" icon="alert">Atrasada<//>`
            : html`<${Badge} tone="accent" icon="target">Em andamento<//>`}
        ${!readOnly
          ? html`<${Menu}
              trigger=${(p) => html`<${IconButton} icon="more" label="Mais ações da meta" onClick=${p.toggle} aria-expanded=${p["aria-expanded"]} />`}
              items=${[{ icon: "trash", label: "Excluir meta", danger: true, onClick: remove }]}
            />`
          : null}
      </div>
      <div class="goal-stats">
        <span class="goal-pct">${goal.progress}%</span>
        <span class="small muted"><span class="mono">${goal.done_tasks}/${goal.total_tasks}</span> tarefas concluídas</span>
      </div>
      <${Progress} value=${goal.progress} done=${goal.status === "concluida"} label="Progresso da meta" />
      <div class="form-grid">
        <${Field} label="Data-alvo" id=${ids.date}>
          <${DateInput} id=${ids.date} value=${goal.target_date} disabled=${readOnly} onChange=${(value) => updateGoal(accountId, goal.id, { target_date: value })} />
        <//>
        <${Field} label="Descrição" id=${ids.desc}>
          ${readOnly
            ? html`<p class="small">${goal.description || "—"}</p>`
            : html`<${AutoText}
                id=${ids.desc}
                value=${goal.description}
                placeholder="Por que esta meta importa?"
                draftKey=${`goal-desc:${goal.id}`}
                onSave=${(v) => updateGoal(accountId, goal.id, { description: v })}
              />`}
        <//>
      </div>
    </section>

    <div class="section-head">
      <h2 class="section-title"><${Icon} name="list" />Tarefas vinculadas</h2>
      <div class="grow"></div>
      ${!readOnly
        ? html`<${Button} size="sm" icon="link" onClick=${() => setLinking(true)}>Vincular tarefas<//>
            <${Button} size="sm" variant="primary" icon="plus" onClick=${() => openModal("newTask", { preset: { goal_id: goal.id } })}>Nova tarefa na meta<//>`
        : null}
    </div>
    ${tasks.length
      ? html`<${TaskSections} tasks=${tasks} readOnly=${readOnly} staleDays=${staleDays} goals=${board.goals} />
          ${!readOnly
            ? html`<details class="small muted">
                <summary style="cursor:pointer">Desvincular tarefas</summary>
                <ul class="list" style="margin-top:8px">
                  ${tasks.map(
                    (task) => html`<li key=${task.id} class="list-item">
                      <span class="grow">${task.title}</span>
                      <${Button} size="sm" variant="ghost" icon="x" onClick=${() => updateTask(accountId, task.id, { goal_id: null }, { success: "Tarefa desvinculada." })}>Desvincular<//>
                    </li>`,
                  )}
                </ul>
              </details>`
            : null}`
      : html`<${EmptyState}
          compact
          icon="link"
          title="Nenhuma tarefa vinculada"
          text="Uma meta sem tarefas fica com 0% e em andamento. Vincule tarefas para medir o progresso."
        />`}
    ${linking ? html`<${LinkTasksModalInline} accountId=${accountId} goal=${goal} onClose=${() => setLinking(false)} />` : null}
  </div>`;
}

function LinkTasksModalInline({ accountId, goal, onClose }) {
  const board = useStore((s) => s.boards[accountId]);
  const [selected, setSelected] = useState([]);
  const candidates = sortPending((board?.tasks || []).filter((t) => t.goal_id !== goal.id));
  return html`<${Modal}
    title=${`Vincular tarefas a “${goal.title}”`}
    icon="link"
    onClose=${onClose}
    footer=${html`<${Button} variant="ghost" onClick=${onClose}>Cancelar<//>
      <${Button} variant="primary" disabled=${!selected.length} onClick=${() => (linkTasks(accountId, goal.id, selected), onClose())}>
        Vincular${selected.length ? ` (${selected.length})` : ""}
      <//>`}
  >
    <p class="small muted" style="margin-bottom:10px">Cada tarefa pertence a no máximo uma meta: vincular aqui a remove de outra meta.</p>
    ${candidates.length
      ? html`<ul class="list">
          ${candidates.map((task) => {
            const other = task.goal_id ? board.goals.find((g) => g.id === task.goal_id) : null;
            return html`<li key=${task.id} class="list-item">
              <${Checkbox}
                size="sm"
                checked=${selected.includes(task.id)}
                label=${`Vincular ${task.title}`}
                onChange=${(on) => setSelected(on ? [...selected, task.id] : selected.filter((id) => id !== task.id))}
              />
              <span class="grow">${task.title}</span>
              ${task.status === "concluida" ? html`<span class="badge status-good">Concluída</span>` : null}
              ${other ? html`<span class="xsmall faint">em “${other.title}”</span>` : null}
            </li>`;
          })}
        </ul>`
      : html`<${EmptyState} compact icon="list" title="Nenhuma tarefa disponível" />`}
  <//>`;
}
