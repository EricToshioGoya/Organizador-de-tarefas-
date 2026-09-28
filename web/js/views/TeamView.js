// Aba Equipe (RF34) e Painel da equipe do Gestor (RF62, RN34); perfil do membro em modo somente leitura
// (RF35–RF37, RF63) com atribuição de tarefas pelo Gestor (RF64).
import { html, cx } from "../lib/html.js";
import { useEffect } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Avatar, Badge, Button, EmptyState, Skeleton, StatusBadge } from "../ui/core.js";
import { TaskFilters, TaskSections, useTaskFilters } from "./TasksView.js";
import { GoalsList, GoalDetailView } from "./GoalsView.js";
import { Dashboard, PeriodFilter, usePeriod } from "./PerformanceView.js";
import { PHASE_COLOR, PHASE_LABEL } from "../lib/rules.js";
import { plural } from "../lib/format.js";
import { ensureBoard, loadTeam, navigate, openModal } from "../actions.js";

function PhaseBar({ phases }) {
  const total = phases.reduce((sum, p) => sum + p.value, 0);
  if (!total) return html`<div class="phase-bar" aria-label="Sem tarefas no período"></div>`;
  return html`<div>
    <div class="phase-bar" role="img" aria-label=${phases.map((p) => `${PHASE_LABEL[p.key]}: ${p.value}`).join(", ")}>
      ${phases.filter((p) => p.value).map((p) => html`<span key=${p.key} style=${`flex-grow:${p.value};background:${PHASE_COLOR[p.key]}`} title=${`${PHASE_LABEL[p.key]}: ${p.value}`}></span>`)}
    </div>
    <div class="legend" style="margin-top:8px">
      ${phases.map(
        (p) => html`<span key=${p.key} class="legend-item"><span class="legend-swatch" style=${`background:${PHASE_COLOR[p.key]}`}></span>${p.label.replace(" (funcionando)", "")} <span class="mono">${p.value}</span></span>`,
      )}
    </div>
  </div>`;
}

function MemberCard({ account, isMe }) {
  return html`<article class="member-card">
    <div class="member-head">
      <${Avatar} account=${account} size="lg" />
      <div class="grow">
        <div class="member-name">${account.name}${isMe ? html` <span class="faint small">(você)</span>` : null}</div>
        ${account.role === "gestor" ? html`<${Badge} tone="violet" icon="crown">Gestor<//>` : html`<span class="small faint">Membro</span>`}
      </div>
    </div>
    <div class="stat-row" style="grid-template-columns:repeat(2,minmax(0,1fr))">
      <div class="stat"><div class="stat-value">${account.active_goals}</div><div class="stat-label">metas em andamento</div></div>
      <div class=${cx("stat", account.overdue_tasks && "critical")}>
        <div class="stat-value">${account.pending_tasks}</div>
        <div class="stat-label">pendentes${account.overdue_tasks ? ` · ${account.overdue_tasks} atrasada${account.overdue_tasks > 1 ? "s" : ""}` : ""}</div>
      </div>
    </div>
    <${Button} icon="eye" onClick=${() => navigate(isMe ? "tarefas" : `equipe/${account.id}/tarefas`)}>${isMe ? "Minhas tarefas" : "Ver perfil"}<//>
  </article>`;
}

/** RF34: cartões simples da equipe (visão do Membro). */
function MembersGrid() {
  const accounts = useStore((s) => s.accounts);
  const meId = useStore((s) => s.meId);
  if (!accounts) return html`<${Skeleton} count=${3} height=${180} />`;
  const ordered = [...accounts].sort((a, b) => (a.id === meId ? -1 : b.id === meId ? 1 : a.name.localeCompare(b.name, "pt-BR")));
  return html`<div class="grid-cards">${ordered.map((a) => html`<${MemberCard} key=${a.id} account=${a} isMe=${a.id === meId} />`)}</div>`;
}

/** RF62: painel do Gestor com pendentes, atrasadas, concluídas no período e distribuição por fase. */
function ManagerPanel() {
  const [period, setPeriod] = usePeriod("period.team");
  const data = useStore((s) => s.team[period]);
  const meId = useStore((s) => s.meId);
  useEffect(() => {
    loadTeam(period);
  }, [period]);
  const members = data?.members || null;
  return html`<div class="stack" style="gap:18px">
    <div class="toolbar toolbar-row" role="toolbar" aria-label="Filtros">
      <${PeriodFilter} value=${period} onChange=${setPeriod} />
    </div>
    ${!members
      ? html`<${Skeleton} count=${3} height=${220} />`
      : html`<div class="grid-cards" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr))">
          ${members.map(({ account, overview }) => {
            const isMe = account.id === meId;
            return html`<article key=${account.id} class="member-card">
              <div class="member-head">
                <${Avatar} account=${account} size="lg" />
                <div class="grow">
                  <div class="member-name">${account.name}${isMe ? html` <span class="faint small">(você)</span>` : null}</div>
                  <div class="row-wrap">
                    ${account.role === "gestor" ? html`<${Badge} tone="violet" icon="crown">Gestor<//>` : html`<span class="small faint">Membro</span>`}
                    ${overview.overload?.overloaded ? html`<${StatusBadge} kind="warning" icon="alert">Sobrecarga<//>` : null}
                    ${overview.stale ? html`<${StatusBadge} kind="serious" icon="pause">${overview.stale} parada${overview.stale > 1 ? "s" : ""}<//>` : null}
                  </div>
                </div>
              </div>
              <div class="stat-row">
                <div class="stat"><div class="stat-value">${overview.pending}</div><div class="stat-label">pendentes</div></div>
                <div class=${cx("stat", overview.overdue && "critical")}><div class="stat-value">${overview.overdue}</div><div class="stat-label">atrasadas</div></div>
                <div class="stat"><div class="stat-value">${overview.done_in_period}</div><div class="stat-label">concluídas</div></div>
              </div>
              <div>
                <div class="small muted" style="margin-bottom:8px;font-weight:600">Distribuição por fase</div>
                <${PhaseBar} phases=${overview.phases} />
              </div>
              <div class="row-wrap">
                <${Button} icon="eye" onClick=${() => navigate(isMe ? "desempenho" : `equipe/${account.id}/tarefas`)}>${isMe ? "Meu desempenho" : "Acompanhar"}<//>
                ${!isMe ? html`<${Button} variant="primary" icon="inbox" onClick=${() => openModal("newTask", { accountId: account.id, assign: true })}>Atribuir tarefa<//>` : null}
              </div>
            </article>`;
          })}
        </div>`}
  </div>`;
}

export function TeamView() {
  const me = useStore((s) => (s.accounts || []).find((a) => a.id === s.meId));
  const manager = me?.role === "gestor";
  return html`<div class="stack" style="gap:20px">
    <header class="page-head">
      <div>
        <h1 class="page-title">${manager ? "Painel da equipe" : "Equipe"}</h1>
        <p class="page-subtitle">
          ${manager
            ? "Acompanhe as entregas de cada membro, atribua tarefas e comente."
            : "Veja as tarefas e metas dos colegas em modo somente leitura."}
        </p>
      </div>
    </header>
    ${manager ? html`<${ManagerPanel} />` : html`<${MembersGrid} />`}
  </div>`;
}

/** Perfil do membro (RF35–RF37); o Gestor também acompanha o dashboard (RF63). */
export function MemberProfileView({ accountId, tab = "tarefas", goalId }) {
  const account = useStore((s) => (s.accounts || []).find((a) => a.id === accountId));
  const me = useStore((s) => (s.accounts || []).find((a) => a.id === s.meId));
  const board = useStore((s) => s.boards[accountId]);
  const filters = useTaskFilters(`equipe:${accountId}`);
  const [period, setPeriod] = usePeriod("period.member");
  const manager = me?.role === "gestor";

  useEffect(() => {
    ensureBoard(accountId);
  }, [accountId]);

  if (!account) return html`<${EmptyState} icon="users" title="Conta não encontrada" action=${html`<${Button} onClick=${() => navigate("equipe")}>Voltar<//>`} />`;
  if (me && accountId === me.id) {
    navigate(tab === "desempenho" ? "desempenho" : tab === "metas" ? "metas" : "tarefas");
    return null;
  }
  const tabs = [
    { key: "tarefas", label: "Tarefas", icon: "list" },
    { key: "metas", label: "Metas", icon: "target" },
    ...(manager ? [{ key: "desempenho", label: "Desempenho", icon: "chart" }] : []),
  ];
  const staleDays = board?.account?.settings?.stale_days || 5;

  return html`<div class="stack" style="gap:18px">
    <header class="page-head">
      <div class="row" style="gap:14px">
        <${Avatar} account=${account} size="lg" />
        <div>
          <h1 class="page-title">${account.name}</h1>
          <p class="page-subtitle">
            ${plural(account.pending_tasks, "tarefa pendente", "tarefas pendentes")} · ${plural(account.active_goals, "meta em andamento", "metas em andamento")}
          </p>
        </div>
      </div>
      ${manager ? html`<${Button} variant="primary" icon="inbox" onClick=${() => openModal("newTask", { accountId, assign: true })}>Atribuir tarefa<//>` : null}
    </header>

    <div class="tabs" role="tablist" aria-label="Seções do perfil">
      ${tabs.map(
        (t) => html`<button
          key=${t.key}
          role="tab"
          aria-selected=${tab === t.key ? "true" : "false"}
          onClick=${() => navigate(`equipe/${accountId}/${t.key}`)}
        >
          ${t.label}
        </button>`,
      )}
    </div>

    ${!board
      ? html`<${Skeleton} count=${4} />`
      : tab === "metas"
        ? goalId
          ? html`<${GoalDetailView} goalId=${goalId} accountId=${accountId} readOnly />`
          : html`<${GoalsList} board=${board} readOnly onOpen=${(goal) => navigate(`equipe/${accountId}/metas?meta=${goal.id}`)} />`
        : tab === "desempenho" && manager
          ? html`<div class="stack" style="gap:16px">
              <div class="toolbar toolbar-row" role="toolbar" aria-label="Filtros"><${PeriodFilter} value=${period} onChange=${setPeriod} /></div>
              <${Dashboard} accountId=${accountId} period=${period} />
            </div>`
          : html`<div class="stack" style="gap:18px">
              <section class="toolbar" aria-label="Filtrar tarefas"><${TaskFilters} filters=${filters} tasks=${board.tasks} staleDays=${staleDays} /></section>
              <${TaskSections} tasks=${filters.apply(board.tasks, staleDays)} readOnly staleDays=${staleDays} goals=${board.goals} emptyText="Nenhuma tarefa pendente." />
            </div>`}
    <p class="xsmall faint"><${Icon} name="eye" size=${12} style="display:inline;vertical-align:-2px" /> Modo somente leitura: criação, edição, marcação e exclusão ficam bloqueadas no perfil de outra conta.${manager ? " Como Gestor, você pode atribuir tarefas e comentar." : ""}</p>
  </div>`;
}
