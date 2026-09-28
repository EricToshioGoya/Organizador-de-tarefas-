// Formulário de nova tarefa (RF01). Toda tarefa serve de modelo (RF42): ao digitar o título, o formulário
// sugere reaproveitar as etapas de tarefas parecidas, e "Duplicar tarefa" chega aqui já preenchido.
// Etapas coladas ou geradas por IA (RF44, RF52), sugestão de dificuldade e prazo (RF53), atribuição pelo
// Gestor (RF64) e rascunho automático (RF70).
import { html } from "../lib/html.js";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { Modal } from "../ui/overlay.js";
import { Avatar, Button, IconButton, Segmented } from "../ui/core.js";
import { Autocomplete, DateInput, Field, Select, useFieldId } from "../ui/forms.js";
import { Icon } from "../ui/icons.js";
import { StepsEditor } from "./StepsEditor.js";
import { api } from "../lib/api.js";
import { uid } from "../lib/ids.js";
import { useStore, getState } from "../lib/store.js";
import { loadDraft, saveDraft, clearDraft } from "../lib/drafts.js";
import { DIFFICULTIES, DIFFICULTY_LABEL, PHASES, TITLE_MAX, normalizeText, orderedSteps } from "../lib/rules.js";
import { fmtDate, fmtNumber, plural } from "../lib/format.js";
import { closeModal, createTask, ensureBoard } from "../actions.js";

const EMPTY = {
  title: "",
  description: "",
  difficulty: "medio",
  due_date: null,
  requester: "",
  goal_id: null,
  phase: "planejamento",
  steps: [],
  template_name: null,
};

const STOPWORDS = new Set(["para", "com", "dos", "das", "uma", "por", "que", "sem", "nos", "nas", "pelo", "pela", "entre", "sobre"]);

/** Campos que uma tarefa passa para outra (RN20): título, descrição, dificuldade e etapas, sem datas nem marcações. */
export function copyableFrom(source) {
  const steps = source.steps?.length && typeof source.steps[0] === "object" ? orderedSteps(source.steps).map((s) => s.text) : source.steps || [];
  return {
    title: source.title,
    description: source.description || "",
    difficulty: source.difficulty || "medio",
    steps: steps.map((text) => ({ id: uid(), text, done: false })),
  };
}

/** Tarefas com etapas (e modelos salvos antes da junção com tarefas) cujo título lembra o digitado. */
function findReusable(sources, title, limit = 3) {
  const query = normalizeText(title);
  if (query.length < 3) return [];
  const words = query.split(/\s+/).filter((w) => w.length >= 3 && !STOPWORDS.has(w));
  const seen = new Set();
  const found = [];
  for (const source of sources) {
    const key = normalizeText(source.title);
    if (!source.steps?.length || seen.has(key)) continue;
    seen.add(key);
    let score = key.includes(query) ? 2 : 0;
    if (!score && words.length) {
      const hits = words.filter((w) => key.includes(w)).length;
      if (hits && hits / words.length >= 0.5) score = hits / words.length;
    }
    if (score) found.push({ source, score });
  }
  return found
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((f) => f.source);
}

export function TaskFormModal({ accountId, preset = {}, assign = false, duplicate = false }) {
  const meId = useStore((s) => s.meId);
  const targetId = accountId || meId;
  const board = useStore((s) => s.boards[targetId]);
  const target = useStore((s) => (s.accounts || []).find((a) => a.id === targetId));
  const ownBoard = useStore((s) => s.boards[s.meId]);
  const draftKey = `newtask:${targetId}`;
  const initialDraft = useMemo(() => (Object.keys(preset).length ? null : loadDraft(draftKey)), []);
  const [form, setForm] = useState(() => ({ ...EMPTY, ...(initialDraft || {}), ...preset }));
  const [restored, setRestored] = useState(!!initialDraft);
  const [copied, setCopied] = useState(null); // { from, previous } — para desfazer o reaproveitamento
  const [error, setError] = useState(null);
  const [suggestion, setSuggestion] = useState(null);
  const suggestTimer = useRef(null);
  const ids = { title: useFieldId("nt"), desc: useFieldId("nd"), due: useFieldId("ndue"), req: useFieldId("nreq"), goal: useFieldId("ngoal"), phase: useFieldId("nphase") };

  useEffect(() => {
    if (!board) ensureBoard(targetId);
  }, [targetId]);

  const update = (patch) => {
    setForm((current) => {
      const next = { ...current, ...patch };
      saveDraft(draftKey, next);
      return next;
    });
    if (patch.title !== undefined && error) setError(null);
  };

  // RF53: sugestão por similaridade enquanto o título é digitado
  useEffect(() => {
    clearTimeout(suggestTimer.current);
    const title = form.title.trim();
    if (title.length < 4) {
      setSuggestion(null);
      return undefined;
    }
    suggestTimer.current = setTimeout(async () => {
      try {
        const result = await api.post(`/api/accounts/${targetId}/suggestions`, { title, description: form.description }, { account: getState().meId });
        setSuggestion(result.active && result.found ? result : null);
      } catch {
        setSuggestion(null);
      }
    }, 700);
    return () => clearTimeout(suggestTimer.current);
  }, [form.title]);

  // Fontes para reaproveitar etapas: tarefas mais recentes primeiro e, por último, modelos antigos da conta.
  const sources = useMemo(() => {
    const byActivity = (list) => [...list].sort((a, b) => ((a.last_activity_at || "") < (b.last_activity_at || "") ? 1 : -1));
    const tasks = byActivity([...(board?.tasks || []), ...(ownBoard && ownBoard !== board ? ownBoard.tasks : [])]);
    return [...tasks, ...(ownBoard?.templates || [])];
  }, [board?.tasks, ownBoard?.tasks, ownBoard?.templates]);
  const reusable = useMemo(() => (form.template_name ? [] : findReusable(sources, form.title)), [sources, form.title, form.template_name]);

  const reuse = (source) => {
    const data = copyableFrom(source);
    const typed = form.title.trim();
    const searching = !typed || normalizeText(data.title).includes(normalizeText(typed));
    setCopied({ from: data.title, previous: form });
    update({
      title: searching ? data.title : form.title,
      description: form.description.trim() ? form.description : data.description,
      difficulty: data.difficulty,
      steps: data.steps,
      template_name: data.title,
    });
  };

  const undoReuse = () => {
    update(copied.previous);
    setCopied(null);
  };

  const submit = () => {
    const title = form.title.trim();
    if (!title) {
      setError("O título é obrigatório.");
      document.getElementById(ids.title)?.focus();
      return;
    }
    if (title.length > TITLE_MAX) {
      setError(`O título aceita até ${TITLE_MAX} caracteres.`);
      return;
    }
    createTask(
      targetId,
      {
        ...form,
        title,
        requester: form.requester.trim(),
        steps: form.steps.map((s) => s.text),
        source: form.template_name ? "template" : form.source || "form",
      },
      { assign },
    );
    clearDraft(draftKey);
    closeModal();
  };

  const discardDraft = () => {
    clearDraft(draftKey);
    setForm({ ...EMPTY, ...preset });
    setRestored(false);
    setCopied(null);
  };

  const steps = form.steps;
  const setSteps = (list) => update({ steps: list });
  const heading = assign
    ? html`<span class="row">Atribuir tarefa a <${Avatar} account=${target} size="xs" /> ${target?.name}</span>`
    : duplicate
      ? "Duplicar tarefa"
      : "Nova tarefa";

  return html`<${Modal}
    title=${heading}
    icon=${assign ? "inbox" : duplicate ? "copy" : "plus"}
    size="lg"
    soft
    onClose=${closeModal}
    footer=${html`
      ${restored ? html`<button type="button" class="btn btn-ghost btn-sm" onClick=${discardDraft} style="margin-right:auto">Descartar rascunho</button>` : null}
      <${Button} variant="ghost" onClick=${closeModal}>Cancelar<//>
      <${Button} variant="primary" icon="check" onClick=${submit}>${assign ? "Atribuir tarefa" : "Criar tarefa"}<//>`}
  >
    <form
      class="stack"
      style="gap:14px"
      onSubmit=${(e) => {
        e.preventDefault();
        submit();
      }}
      onKeyDown=${(e) => e.key === "Enter" && (e.ctrlKey || e.metaKey) && (e.preventDefault(), submit())}
    >
      ${restored ? html`<div class="banner"><${Icon} name="history" /><div class="banner-text">Rascunho recuperado.</div></div>` : null}
      ${assign
        ? html`<div class="banner violet">
            <${Icon} name="info" />
            <div class="banner-text">A tarefa será criada na conta de ${target?.name}, com você como solicitante. ${target?.name} receberá um aviso na aba Hoje.</div>
          </div>`
        : null}
      ${duplicate && preset.template_name
        ? html`<div class="banner violet">
            <${Icon} name="copy" />
            <div class="banner-text">Cópia de <strong>${preset.template_name}</strong>: etapas desmarcadas, sem data de entrega. Ajuste o que precisar.</div>
          </div>`
        : null}

      <div class="block">
        <${Field} label="O que precisa ser feito?" required id=${ids.title} error=${error} hint=${`${form.title.length}/${TITLE_MAX}`}>
          <input
            id=${ids.title}
            class="input input-title"
            data-autofocus
            value=${form.title}
            maxLength=${TITLE_MAX}
            placeholder="Ex.: Relatório mensal de vendas"
            aria-invalid=${error ? "true" : undefined}
            aria-required="true"
            onInput=${(e) => update({ title: e.currentTarget.value })}
          />
        <//>
        ${reusable.length
          ? html`<div class="reuse" role="group" aria-label="Reaproveitar etapas de uma tarefa parecida">
              <span class="reuse-label"><${Icon} name="copy" size=${15} />Reaproveitar etapas de</span>
              ${reusable.map(
                (source) => html`<button
                  key=${source.id}
                  type="button"
                  class="chip"
                  aria-label=${`${source.title}, ${plural(source.steps.length, "etapa", "etapas")}`}
                  title=${`Copiar título, descrição, dificuldade e as ${source.steps.length} etapas de “${source.title}”`}
                  onClick=${() => reuse(source)}
                >
                  <span class="truncate">${source.title}</span>
                  <span class="faint mono">${plural(source.steps.length, "etapa", "etapas")}</span>
                </button>`,
              )}
            </div>`
          : null}
        ${copied
          ? html`<div class="banner violet" role="status">
              <${Icon} name="copy" />
              <div class="banner-text">Etapas copiadas de <strong>${copied.from}</strong>.</div>
              <${Button} size="sm" variant="ghost" icon="history" onClick=${undoReuse}>Desfazer<//>
            </div>`
          : null}
      </div>

      ${suggestion
        ? html`<div class="banner violet">
            <${Icon} name="sparkles" />
            <div class="banner-text">
              Sugestão: <strong>${DIFFICULTY_LABEL[suggestion.difficulty]}</strong> · entrega <strong class="mono">${fmtDate(suggestion.due_date)}</strong>
              <div class="xsmall muted">Baseada em ${suggestion.based_on.length} tarefas concluídas semelhantes (mediana de ${fmtNumber(suggestion.median_days)} dias).</div>
            </div>
            <${Button} size="sm" variant="primary" onClick=${() => {
              update({ difficulty: suggestion.difficulty, due_date: suggestion.due_date });
              setSuggestion(null);
            }}>Aplicar<//>
            <${IconButton} icon="x" size="sm" label="Dispensar sugestão" onClick=${() => setSuggestion(null)} />
          </div>`
        : null}

      <div class="block">
        <${Field} label=${steps.length ? `Etapas (${steps.length})` : "Etapas"}>
          <${StepsEditor}
            steps=${steps}
            showCheck=${false}
            getContext=${() => ({ title: form.title, description: form.description })}
            onAdd=${(texts, source) => {
              setSteps([...steps, ...texts.map((text) => ({ id: uid(), text, done: false }))]);
              if (source === "ai") update({ source: "ai" });
            }}
            onToggle=${() => {}}
            onRename=${(id, text) => setSteps(steps.map((s) => (s.id === id ? { ...s, text } : s)))}
            onDelete=${(id) => setSteps(steps.filter((s) => s.id !== id))}
            onReorder=${(order) => setSteps(order.map((id) => steps.find((s) => s.id === id)))}
          />
        <//>
      </div>

      <div class="block">
        <div class="form-grid">
          <${Field} label="Dificuldade" class="span-2">
            <${Segmented}
              label="Dificuldade"
              value=${form.difficulty}
              options=${DIFFICULTIES.map((d) => ({ value: d.key, label: d.label, dot: `var(--diff-${d.key})` }))}
              onChange=${(value) => update({ difficulty: value })}
            />
          <//>
          <${Field} label="Data de entrega" id=${ids.due}>
            <${DateInput} id=${ids.due} value=${form.due_date} onChange=${(value) => update({ due_date: value })} />
          <//>
          <${Field} label="Fase" id=${ids.phase}>
            <${Select} id=${ids.phase} value=${form.phase} options=${PHASES.map((p) => ({ value: p.key, label: p.label }))} onChange=${(value) => value && update({ phase: value })} />
          <//>
          ${!assign
            ? html`<${Field} label="Solicitante" id=${ids.req}>
                  <${Autocomplete}
                    id=${ids.req}
                    value=${form.requester}
                    options=${board?.requesters || []}
                    placeholder="Quem pediu?"
                    ariaLabel="Solicitante"
                    onChange=${(value) => update({ requester: value })}
                  />
                <//>
                <${Field} label="Meta" id=${ids.goal}>
                  <${Select}
                    id=${ids.goal}
                    value=${form.goal_id || ""}
                    placeholder="Sem meta"
                    options=${(board?.goals || []).filter((g) => g.status === "andamento").map((g) => ({ value: g.id, label: g.title }))}
                    onChange=${(value) => update({ goal_id: value || null })}
                  />
                <//>`
            : null}
        </div>
      </div>

      <div class="block">
        <${Field} label="Descrição" id=${ids.desc} hint="Opcional: contexto e critérios de aceite.">
          <textarea
            id=${ids.desc}
            class="textarea"
            rows="3"
            value=${form.description}
            placeholder="Contexto, critérios de aceite…"
            onInput=${(e) => update({ description: e.currentTarget.value })}
          ></textarea>
        <//>
      </div>
      <button type="submit" hidden>Criar</button>
    </form>
  <//>`;
}
