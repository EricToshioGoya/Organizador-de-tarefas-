// Estrutura do app: cabeçalho com abas, indicador de salvamento (RF69), menu da conta (RF26),
// criação de tarefa em 1 clique de qualquer tela (RNF10), gaveta de detalhes e painel de drill-down.
import { html, cx } from "../lib/html.js";
import { useEffect } from "preact/hooks";
import { useStore, setState } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Avatar, Badge, Button, EmptyState } from "../ui/core.js";
import { Drawer, Menu, Toasts } from "../ui/overlay.js";
import { AccountPicker } from "./AccountPicker.js";
import { TodayView } from "./TodayView.js";
import { TasksView } from "./TasksView.js";
import { GoalsView, GoalDetailView } from "./GoalsView.js";
import { PerformanceView } from "./PerformanceView.js";
import { TeamView, MemberProfileView } from "./TeamView.js";
import { SettingsView } from "./SettingsView.js";
import { TaskDrawer } from "./TaskDetail.js";
import { TaskCard } from "./TaskCard.js";
import { ModalHost } from "./Modals.js";
import { retryNow } from "../lib/queue.js";
import { isPending, isOverdue } from "../lib/rules.js";
import { navigate, openModal, switchAccount } from "../actions.js";

const MEMBER_TABS = [
  { key: "hoje", label: "Hoje", icon: "sun" },
  { key: "tarefas", label: "Tarefas", icon: "list" },
  { key: "metas", label: "Metas", icon: "target" },
  { key: "desempenho", label: "Desempenho", icon: "chart" },
  { key: "equipe", label: "Equipe", icon: "users" },
];
const MANAGER_TABS = [
  { key: "equipe", label: "Painel", icon: "dashboard" },
  { key: "hoje", label: "Hoje", icon: "sun" },
  { key: "tarefas", label: "Tarefas", icon: "list" },
  { key: "metas", label: "Metas", icon: "target" },
  { key: "desempenho", label: "Desempenho", icon: "chart" },
];

function activeTab(route) {
  if (route.name === "meta") return "metas";
  if (route.name === "membro") return "equipe";
  return route.name;
}

function SaveIndicator() {
  const sync = useStore((s) => s.sync);
  const online = useStore((s) => s.online);
  const status = !online ? "offline" : sync.status;
  const pending = sync.pending;
  const view = {
    saved: { icon: "cloudCheck", text: "Salvo", title: "Todas as alterações estão gravadas no servidor." },
    saving: { icon: "loader", text: "Salvando…", title: `${pending} alteração(ões) sendo gravada(s).` },
    offline: {
      icon: "cloudOff",
      text: pending ? `Offline · ${pending}` : "Offline",
      title: pending ? `${pending} alteração(ões) guardada(s) no dispositivo; serão enviadas ao reconectar.` : "Sem conexão. Alterações ficam guardadas no dispositivo.",
    },
    error: { icon: "alert", text: "Tentando salvar…", title: "O servidor não respondeu; nova tentativa automática em instantes." },
  }[status];
  return html`<button
    type="button"
    class=${cx("save-indicator", status)}
    role="status"
    aria-live="polite"
    title=${view.title}
    onClick=${retryNow}
    aria-label=${`${view.text}. ${view.title}`}
  >
    <${Icon} name=${view.icon} class=${status === "saving" ? "spin" : ""} />
    <span class="hide-mobile">${view.text}</span>
  </button>`;
}

function UserMenu({ me }) {
  return html`<${Menu}
    header=${html`<div class="menu-header">
      <${Avatar} account=${me} />
      <div class="grow" style="min-width:0">
        <div class="truncate" style="font-weight:600">${me.name}</div>
        <div class="xsmall faint">${me.role === "gestor" ? "Gestor" : "Membro"}</div>
      </div>
    </div>`}
    trigger=${(props) => html`<button
      type="button"
      class="icon-btn"
      style="width:auto;padding:0 4px;gap:6px;display:inline-flex"
      aria-label=${`Conta: ${me.name}. Abrir menu`}
      aria-haspopup="menu"
      aria-expanded=${props["aria-expanded"]}
      onClick=${props.toggle}
    >
      <${Avatar} account=${me} size="sm" />
      <${Icon} name="chevronDown" size=${14} />
    </button>`}
    items=${[
      { icon: "switch", label: "Trocar de conta", onClick: switchAccount },
      { icon: "settings", label: "Configurações da conta", onClick: () => navigate("conta") },
      "-",
      { icon: "external", label: "Documentação da API", onClick: () => window.open("/api/docs", "_blank", "noopener") },
    ]}
  />`;
}

function DrillPanel({ panel }) {
  const board = useStore((s) => s.boards[panel.accountId]);
  const meId = useStore((s) => s.meId);
  const tasks = (board?.tasks || []).filter((t) => panel.taskIds.includes(t.id));
  const close = () => setState({ panel: null });
  return html`<${Drawer}
    onClose=${close}
    label=${panel.title}
    header=${html`<div class="grow"><div class="xsmall faint">Detalhamento</div><strong>${panel.title}</strong></div>`}
  >
    ${tasks.length
      ? html`<div class="task-list">
          ${tasks.map((task) => html`<${TaskCard} key=${task.id} task=${task} readOnly=${panel.accountId !== meId} goals=${board.goals} />`)}
        </div>`
      : html`<${EmptyState} compact icon="list" title="Nenhuma tarefa" text="Nenhuma tarefa corresponde a este elemento no período." />`}
  <//>`;
}

function ViewingBanner({ accountId }) {
  const account = useStore((s) => (s.accounts || []).find((a) => a.id === accountId));
  if (!account) return null;
  return html`<div class="viewing-banner" role="status">
    <${Icon} name="eye" size=${18} />
    <${Avatar} account=${account} size="xs" />
    <span class="grow">Visualizando: <strong>${account.name}</strong> <span class="muted">· somente leitura</span></span>
    <${Button} size="sm" variant="ghost" icon="arrowLeft" onClick=${() => navigate("equipe")}>Voltar<//>
  </div>`;
}

function Page({ route }) {
  switch (route.name) {
    case "hoje":
      return html`<${TodayView} />`;
    case "tarefas":
      return html`<${TasksView} />`;
    case "metas":
      return html`<${GoalsView} />`;
    case "meta":
      return html`<${GoalDetailView} goalId=${route.params.goalId} />`;
    case "desempenho":
      return html`<${PerformanceView} />`;
    case "equipe":
      return html`<${TeamView} />`;
    case "membro":
      return html`<${MemberProfileView} accountId=${route.params.accountId} tab=${route.params.tab} goalId=${route.params.meta} />`;
    case "conta":
      return html`<${SettingsView} />`;
    default:
      return html`<${TodayView} />`;
  }
}

export function App() {
  const ready = useStore((s) => s.ready);
  const meId = useStore((s) => s.meId);
  const me = useStore((s) => (s.accounts || []).find((a) => a.id === s.meId));
  const route = useStore((s) => s.route);
  const drawer = useStore((s) => s.drawer);
  const panel = useStore((s) => s.panel);
  const board = useStore((s) => s.boards[s.meId]);

  useEffect(() => {
    const onKey = (event) => {
      const target = event.target;
      const typing = target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "n" && meId && !document.querySelector(".scrim")) {
        event.preventDefault();
        openModal("newTask", {});
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [meId]);

  if (!ready) {
    return html`<div class="picker"><div class="stack" style="align-items:center"><span class="brand-mark"><${Icon} name="logo" size=${18} strokeWidth=${2.4} /></span><div class="skeleton" style="width:220px;height:14px"></div></div></div>`;
  }
  if (!meId || !me) {
    return html`<${AccountPicker} /><${Toasts} /><${ModalHost} />`;
  }

  const tabs = me.role === "gestor" ? MANAGER_TABS : MEMBER_TABS;
  const current = activeTab(route);
  const overdueCount = (board?.tasks || []).filter((t) => isPending(t) && isOverdue(t)).length;
  const attention = (board?.tasks || []).filter((t) => (t.assigned_by && !t.assigned_seen_at) || (t.comments?.unread || 0) > 0).length;
  const badgeFor = (key) => (key === "hoje" ? overdueCount + attention : 0);
  const viewing = route.name === "membro" ? route.params.accountId : null;

  return html`<div class="app-shell">
    <a class="skip-link" href="#main">Pular para o conteúdo</a>
    <header class="app-header">
      <button type="button" class="brand" onClick=${() => navigate(me.role === "gestor" ? "equipe" : "hoje")} aria-label="Organizador de Tarefas — início">
        <span class="brand-mark"><${Icon} name="logo" size=${18} strokeWidth=${2.4} /></span>
        <span class="brand-name">Organizador</span>
      </button>
      <nav class="top-nav" aria-label="Principal">
        ${tabs.map(
          (tab) => html`<a key=${tab.key} class="nav-tab" href=${`#/${tab.key}`} aria-current=${current === tab.key ? "page" : undefined}>
            <${Icon} name=${tab.icon} size=${18} />${tab.label}
            ${badgeFor(tab.key) ? html`<span class="nav-badge" aria-label=${`${badgeFor(tab.key)} itens pedem atenção`}>${badgeFor(tab.key)}</span>` : null}
          </a>`,
        )}
      </nav>
      <div class="header-spacer"></div>
      <div class="header-actions">
        <${SaveIndicator} />
        <${Button} variant="primary" icon="plus" class="hide-mobile" onClick=${() => openModal("newTask", {})} title="Nova tarefa (atalho: N)">Nova tarefa<//>
        ${me.role === "gestor" ? html`<${Badge} tone="violet" icon="crown" class="hide-mobile">Gestor<//>` : null}
        <${UserMenu} me=${me} />
      </div>
    </header>
    ${viewing ? html`<${ViewingBanner} accountId=${viewing} />` : null}

    <main class="main" id="main" tabindex="-1">
      <${Page} route=${route} />
    </main>

    <nav class="bottom-nav" aria-label="Principal">
      ${tabs.map(
        (tab) => html`<a key=${tab.key} class="bottom-tab" href=${`#/${tab.key}`} aria-current=${current === tab.key ? "page" : undefined}>
          <${Icon} name=${tab.icon} size=${20} />${tab.label}
          ${badgeFor(tab.key) ? html`<span class="nav-badge">${badgeFor(tab.key)}</span>` : null}
        </a>`,
      )}
    </nav>
    <button type="button" class="fab" aria-label="Nova tarefa" onClick=${() => openModal("newTask", {})}><${Icon} name="plus" size=${26} strokeWidth=${2.2} /></button>

    ${drawer ? html`<${TaskDrawer} key=${drawer.taskId} taskId=${drawer.taskId} accountId=${drawer.accountId} />` : null}
    ${panel ? html`<${DrillPanel} panel=${panel} />` : null}
    <${ModalHost} />
    <${Toasts} />
  </div>`;
}
