// Aba Tarefas (RF12–RF16): seções Pendentes e Concluídas com contadores, criação rápida (RF41),
// filtro por fase (RF59), tarefas paradas (RF49) e busca.
import { html, cx } from "../lib/html.js";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { useStore, getState } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Button, Chip, EmptyState, SectionTitle, Skeleton } from "../ui/core.js";
import { TaskCard } from "./TaskCard.js";
import { api } from "../lib/api.js";
import { prefs } from "../lib/cache.js";
import { dueLabel, plural } from "../lib/format.js";
import { DIFFICULTY_LABEL, PHASES, PHASE_COLOR, TITLE_MAX, isDone, isPending, isStale, normalizeText, sortDone, sortPending } from "../lib/rules.js";
import { createTask, openModal, toast } from "../actions.js";

const PAGE = 30;

/** Criação rápida por texto com pré-visualização (RF41, RN19). */
export function QuickAdd({ accountId }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);
  const [offline, setOffline] = useState(false);
  const timer = useRef(null);
  const requesters = useStore((s) => s.boards[accountId]?.requesters || []);
  const seq = useRef(0);

  useEffect(() => {
    clearTimeout(timer.current);
    if (!text.trim()) {
      setPreview(null);
      return undefined;
    }
    const current = ++seq.current;
    timer.current = setTimeout(async () => {
      try {
        const result = await api.post("/api/quick-add/parse", { text }, { account: getState().meId });
        if (current === seq.current) {
          setPreview(result);
          setOffline(false);
        }
      } catch {
        if (current === seq.current) setOffline(true);
      }
    }, 200);
    return () => clearTimeout(timer.current);
  }, [text]);

  const mention = /(^|\s)@([^\s@]*)$/.exec(text);
  const mentionMatches = mention
    ? requesters.filter((r) => normalizeText(r).replace(/\s+/g, "_").startsWith(normalizeText(mention[2]))).slice(0, 5)
    : [];

  const insertMention = (name) => {
    setText(text.replace(/@([^\s@]*)$/, `@${name.replace(/\s+/g, "_")} `));
  };

  const submit = () => {
    if (!text.trim()) return;
    if (offline || !preview) {
      const title = text.trim().slice(0, TITLE_MAX);
      createTask(accountId, { title, source: "quickadd" });
      setText("");
      setPreview(null);
      return;
    }
    if (preview.errors.length) {
      toast(preview.errors[0], "error");
      return;
    }
    createTask(accountId, {
      title: preview.title,
      due_date: preview.due_date,
      difficulty: preview.difficulty || "medio",
      requester: preview.requester || "",
      source: "quickadd",
    });
    setText("");
    setPreview(null);
  };

  return html`<div class="quick-add">
    <div class="quick-add-row">
      <${Icon} name="zap" />
      <label class="sr-only" for="quick-add">Criação rápida</label>
      <input
        id="quick-add"
        class="input"
        placeholder="Criação rápida — ex.: Apresentação sexta difícil @Carlos"
        value=${text}
        autocomplete="off"
        aria-describedby="quick-add-preview"
        onInput=${(e) => setText(e.currentTarget.value)}
        onKeyDown=${(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          }
          if (e.key === "Tab" && mentionMatches.length) {
            e.preventDefault();
            insertMention(mentionMatches[0]);
          }
        }}
      />
      <${Button} variant="primary" icon="plus" disabled=${!text.trim()} onClick=${submit} aria-label="Adicionar tarefa"><span class="hide-mobile">Adicionar</span><//>
    </div>
    ${mentionMatches.length
      ? html`<div class="qa-preview" aria-label="Solicitantes sugeridos">
          <span class="faint">Solicitante:</span>
          ${mentionMatches.map((name) => html`<button key=${name} type="button" class="chip" onClick=${() => insertMention(name)}>@${name}</button>`)}
          <span class="faint">(Tab completa)</span>
        </div>`
      : null}
    ${text.trim()
      ? html`<div class="qa-preview" id="quick-add-preview" aria-live="polite">
          ${offline
            ? html`<span class="faint">Pré-visualização indisponível offline — Enter cria a tarefa com o texto como título.</span>`
            : preview
              ? html`
                  <span class="faint">Pré-visualização:</span>
                  ${preview.tokens.map((token, i) => html`<span key=${i} class=${cx("qa-token", token.kind !== "title" && token.kind)}>${token.text}</span>`)}
                  <span class="faint">→</span>
                  <strong>${preview.title || "(sem título)"}</strong>
                  ${preview.due_date ? html`<span class="badge accent"><${Icon} name="calendar" />${dueLabel(preview.due_date)}</span>` : null}
                  ${preview.difficulty ? html`<span class=${`badge diff-${preview.difficulty}`}><span class="dot"></span>${DIFFICULTY_LABEL[preview.difficulty]}</span>` : null}
                  ${preview.requester ? html`<span class="badge violet"><${Icon} name="user" />${preview.requester}</span>` : null}
                  ${preview.errors.length ? html`<span class="badge status-critical"><${Icon} name="alert" />${preview.errors[0]}</span>` : null}
                `
              : html`<span class="faint">Interpretando…</span>`}
        </div>`
      : html`<div class="qa-preview faint" id="quick-add-preview">
          Use <span class="qa-token date">hoje</span> <span class="qa-token date">amanhã</span> <span class="qa-token date">sexta</span>
          <span class="qa-token date">25/10</span> · <span class="qa-token difficulty">fácil</span> <span class="qa-token difficulty">médio</span>
          <span class="qa-token difficulty">difícil</span> · <span class="qa-token requester">@nome</span>
        </div>`}
  </div>`;
}

export function TaskSections({ tasks, readOnly, staleDays, goals, emptyText }) {
  const [showDone, setShowDone] = useState(PAGE);
  const pending = sortPending(tasks.filter(isPending));
  const done = sortDone(tasks.filter(isDone));
  const cardProps = { readOnly, staleDays, goals };
  return html`<div class="stack" style="gap:28px">
    <section class="section" aria-label="Pendentes">
      <${SectionTitle} icon="circle" count=${pending.length}>Pendentes<//>
      ${pending.length
        ? html`<div class="task-list">${pending.map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} />`)}</div>`
        : html`<${EmptyState} compact icon="checkCircle" title="Nenhuma pendente" text=${emptyText || "Tudo concluído por aqui."} />`}
    </section>
    <section class="section" aria-label="Concluídas">
      <${SectionTitle} icon="checkCircle" tone="good" count=${done.length}>Concluídas<//>
      ${done.length
        ? html`<div class="task-list">
            ${done.slice(0, showDone).map((task) => html`<${TaskCard} key=${task.id} task=${task} ...${cardProps} />`)}
          </div>
          ${done.length > showDone
            ? html`<${Button} variant="ghost" icon="chevronDown" onClick=${() => setShowDone(showDone + PAGE)}>
                Mostrar mais (${plural(done.length - showDone, "restante", "restantes")})
              <//>`
            : null}`
        : html`<p class="small faint">As tarefas concluídas aparecem aqui, da mais recente para a mais antiga.</p>`}
    </section>
  </div>`;
}

/** Filtros compartilhados pelas abas Tarefas e Equipe (RF59). */
export function useTaskFilters(key) {
  const [phase, setPhase] = useState(() => prefs.get(`filter.phase.${key}`, null));
  const [query, setQuery] = useState("");
  const [onlyStale, setOnlyStale] = useState(false);
  const choosePhase = (value) => {
    setPhase(value);
    prefs.set(`filter.phase.${key}`, value);
  };
  const apply = (tasks, staleDays) => {
    const q = normalizeText(query);
    return tasks.filter(
      (t) => (!phase || t.phase === phase) && (!q || normalizeText(t.title).includes(q) || normalizeText(t.requester).includes(q)) && (!onlyStale || isStale(t, staleDays)),
    );
  };
  return { phase, choosePhase, query, setQuery, onlyStale, setOnlyStale, apply };
}

export function TaskFilters({ filters, tasks, staleDays }) {
  const counts = useMemo(() => Object.fromEntries(PHASES.map((p) => [p.key, tasks.filter((t) => t.phase === p.key).length])), [tasks]);
  const staleCount = tasks.filter((t) => isStale(t, staleDays)).length;
  return html`<div class="stack" style="gap:10px">
    <div class="row-wrap">
      <div class="row grow" style="min-width:220px;max-width:360px">
        <label class="sr-only" for="task-search">Buscar tarefas</label>
        <input
          id="task-search"
          class="input"
          type="search"
          placeholder="Buscar por título ou solicitante"
          value=${filters.query}
          onInput=${(e) => filters.setQuery(e.currentTarget.value)}
        />
      </div>
    </div>
    <div class="chips" role="group" aria-label="Filtrar por fase">
      <${Chip} pressed=${!filters.phase} onClick=${() => filters.choosePhase(null)}>Todas as fases<//>
      ${PHASES.map(
        (p) => html`<${Chip} key=${p.key} pressed=${filters.phase === p.key} dot=${PHASE_COLOR[p.key]} onClick=${() => filters.choosePhase(filters.phase === p.key ? null : p.key)}>
          ${p.short} <span class="mono faint">${counts[p.key]}</span>
        <//>`,
      )}
      ${staleCount
        ? html`<${Chip} pressed=${filters.onlyStale} onClick=${() => filters.setOnlyStale(!filters.onlyStale)}>
            <${Icon} name="pause" size=${14} />Paradas <span class="mono faint">${staleCount}</span>
          <//>`
        : null}
    </div>
  </div>`;
}

export function TasksView() {
  const board = useStore((s) => s.boards[s.meId]);
  const route = useStore((s) => s.route);
  const filters = useTaskFilters("tarefas");

  useEffect(() => {
    if (route.params?.filtro === "paradas") filters.setOnlyStale(true);
  }, [route.params?.filtro]);

  if (!board) return html`<${Skeleton} count=${5} />`;
  const staleDays = board.account.settings?.stale_days || 5;
  const visible = filters.apply(board.tasks, staleDays);
  const pendingCount = board.tasks.filter(isPending).length;

  return html`<div class="stack" style="gap:20px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Tarefas</h1>
        <p class="page-subtitle">${plural(pendingCount, "pendente", "pendentes")} · ${plural(board.tasks.length - pendingCount, "concluída", "concluídas")}</p>
      </div>
    </header>
    <section class="toolbar" aria-label="Criar e filtrar tarefas">
      <${QuickAdd} accountId=${board.account.id} />
      <${TaskFilters} filters=${filters} tasks=${board.tasks} staleDays=${staleDays} />
    </section>
    ${board.tasks.length
      ? html`<${TaskSections}
          tasks=${visible}
          staleDays=${staleDays}
          goals=${board.goals}
          emptyText=${filters.phase || filters.query || filters.onlyStale ? "Nenhuma tarefa pendente com esses filtros." : undefined}
        />`
      : html`<${EmptyState}
          icon="list"
          title="Nenhuma tarefa ainda"
          text="Crie a primeira tarefa pelo botão “Nova tarefa” ou digite uma frase na criação rápida acima."
          action=${html`<${Button} variant="primary" icon="plus" onClick=${() => openModal("newTask", {})}>Nova tarefa<//>`}
        />`}
  </div>`;
}
