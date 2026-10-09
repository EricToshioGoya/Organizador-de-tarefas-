// Editor de etapas (RF07–RF11): marcar com um clique, editar, remover, reordenar (arrastar ou teclado),
// colar várias de uma vez (RF44) e gerar por IA com revisão antes de gravar (RF52, RN26).
import { html, cx } from "../lib/html.js";
import { useState } from "preact/hooks";
import { Icon } from "../ui/icons.js";
import { Checkbox, IconButton, Button } from "../ui/core.js";
import { Modal } from "../ui/overlay.js";
import { api } from "../lib/api.js";
import { splitPastedSteps } from "../lib/rules.js";
import { useReorder } from "../lib/reorder.js";
import { getState } from "../lib/store.js";
import { toast } from "../actions.js";

function StepText({ step, readOnly, onRename }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(step.text);
  if (editing && !readOnly) {
    const commit = () => {
      setEditing(false);
      const clean = text.trim();
      if (clean && clean !== step.text) onRename(step.id, clean);
      else setText(step.text);
    };
    return html`<div class="step-text">
      <input
        class="input"
        value=${text}
        maxLength="500"
        aria-label="Descrição da etapa"
        data-autofocus
        ref=${(el) => el && requestAnimationFrame(() => el.focus())}
        onInput=${(e) => setText(e.currentTarget.value)}
        onBlur=${commit}
        onKeyDown=${(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setText(step.text);
            setEditing(false);
          }
        }}
      />
    </div>`;
  }
  return html`<span
    class="step-text"
    onDblClick=${() => !readOnly && (setText(step.text), setEditing(true))}
    title=${readOnly ? undefined : "Clique duas vezes para editar"}
    >${step.text}</span
  >`;
}

export function AIReviewModal({ steps: initial, onConfirm, onClose }) {
  const [items, setItems] = useState(initial.map((text, i) => ({ id: i, text, keep: true })));
  const chosen = items.filter((i) => i.keep && i.text.trim());
  return html`<${Modal}
    title="Revise as etapas sugeridas"
    icon="sparkles"
    onClose=${onClose}
    footer=${html`
      <${Button} variant="ghost" onClick=${onClose}>Descartar<//>
      <${Button} variant="primary" icon="check" disabled=${!chosen.length} onClick=${() => onConfirm(chosen.map((i) => i.text.trim()))}>
        Adicionar ${chosen.length} etapa${chosen.length === 1 ? "" : "s"}
      <//>`}
  >
    <p class="muted small" style="margin-bottom:12px">
      Nada é gravado sem sua confirmação. Edite, desmarque ou remova sugestões antes de adicionar.
    </p>
    <ul class="steps">
      ${items.map(
        (item) => html`<li key=${item.id} class="step">
          <${Checkbox}
            size="sm"
            checked=${item.keep}
            label=${item.keep ? "Não incluir esta etapa" : "Incluir esta etapa"}
            onChange=${(keep) => setItems(items.map((i) => (i.id === item.id ? { ...i, keep } : i)))}
          />
          <div class="step-text">
            <input
              class="input"
              value=${item.text}
              maxLength="500"
              aria-label="Etapa sugerida"
              onInput=${(e) => setItems(items.map((i) => (i.id === item.id ? { ...i, text: e.currentTarget.value } : i)))}
            />
          </div>
        </li>`,
      )}
    </ul>
  <//>`;
}

export function PastePreviewModal({ steps, onConfirm, onClose }) {
  return html`<${Modal}
    title=${`Adicionar ${steps.length} etapas?`}
    icon="clipboard"
    size="sm"
    onClose=${onClose}
    footer=${html`
      <${Button} variant="ghost" onClick=${onClose}>Cancelar<//>
      <${Button} variant="primary" icon="plus" onClick=${() => onConfirm(steps)}>Adicionar<//>`}
  >
    <p class="muted small" style="margin-bottom:10px">Uma etapa por linha; linhas vazias e marcadores de lista foram removidos.</p>
    <ol class="list">
      ${steps.map((text, i) => html`<li key=${i} class="list-item"><span class="step-num">${i + 1}.</span>${text}</li>`)}
    </ol>
  <//>`;
}

/**
 * steps: [{id, text, done}] · onAdd(texts, source) · onToggle(id, done) · onRename(id, text)
 * onDelete(id) · onReorder(ids) · getContext() → {title, description} para a IA.
 */
export function StepsEditor({ steps, readOnly, showCheck = true, onAdd, onToggle, onRename, onDelete, onReorder, getContext }) {
  const [draft, setDraft] = useState("");
  const [paste, setPaste] = useState(null);
  const [aiSteps, setAiSteps] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const { listProps, handleProps, rowState } = useReorder(
    steps.map((s) => s.id),
    onReorder,
    readOnly,
  );
  const aiEnabled = getState().meta?.ai_enabled;

  const add = () => {
    const text = draft.trim();
    if (!text) return;
    onAdd([text], "form");
    setDraft("");
  };

  const generate = async () => {
    const { title, description } = getContext();
    if (!title?.trim()) {
      toast("Informe o título da tarefa antes de gerar etapas.", "info");
      return;
    }
    setAiLoading(true);
    try {
      const result = await api.post("/api/ai/steps", { title, description: description || "" }, { account: getState().meId });
      setAiSteps(result.steps);
    } catch (error) {
      toast(error.message || "A IA não respondeu. Tente novamente.", "error");
    } finally {
      setAiLoading(false);
    }
  };

  return html`<div class="stack" style="gap:8px">
    ${steps.length
      ? html`<ul class="steps" ...${listProps}>
          ${steps.map(
            (step) => html`<li
              key=${step.id}
              data-step=${step.id}
              class=${cx("step", { done: showCheck && step.done }, rowState(step.id))}
            >
              ${!readOnly && steps.length > 1
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
              ${showCheck
                ? html`<${Checkbox}
                    checked=${step.done}
                    disabled=${readOnly}
                    label=${step.done ? `Desmarcar: ${step.text}` : `Concluir: ${step.text}`}
                    onChange=${(value) => onToggle(step.id, value)}
                  />`
                : html`<span class="step-num">${steps.indexOf(step) + 1}.</span>`}
              <${StepText} step=${step} readOnly=${readOnly} onRename=${onRename} />
              ${!readOnly
                ? html`<div class="step-actions">
                    <${IconButton} icon="trash" size="sm" danger label=${`Remover etapa: ${step.text}`} onClick=${() => onDelete(step.id)} />
                  </div>`
                : null}
            </li>`,
          )}
        </ul>`
      : null}

    ${!readOnly
      ? html`<div class="step-add">
          <input
            class="input"
            placeholder=${steps.length ? "Próxima etapa… (cole várias linhas para incluir em lote)" : "Primeira etapa… (cole várias linhas para incluir em lote)"}
            aria-label="Nova etapa"
            value=${draft}
            maxLength="500"
            onInput=${(e) => setDraft(e.currentTarget.value)}
            onKeyDown=${(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            onPaste=${(e) => {
              const text = e.clipboardData?.getData("text") || "";
              if (!text.includes("\n")) return;
              e.preventDefault();
              const lines = splitPastedSteps(text);
              if (lines.length === 1) setDraft(lines[0]);
              else if (lines.length > 1) setPaste(lines);
            }}
          />
          <${Button} icon="plus" onClick=${add} disabled=${!draft.trim()} aria-label="Adicionar etapa">Adicionar<//>
          ${aiEnabled
            ? html`<${Button} variant="ghost" icon="sparkles" loading=${aiLoading} onClick=${generate} title="Gerar etapas com IA a partir do título e da descrição">
                <span class="hide-mobile">IA</span>
              <//>`
            : null}
        </div>`
      : null}

    ${paste
      ? html`<${PastePreviewModal}
          steps=${paste}
          onClose=${() => setPaste(null)}
          onConfirm=${(lines) => {
            onAdd(lines, "paste");
            setPaste(null);
          }}
        />`
      : null}
    ${aiSteps
      ? html`<${AIReviewModal}
          steps=${aiSteps}
          onClose=${() => setAiSteps(null)}
          onConfirm=${(lines) => {
            onAdd(lines, "ai");
            setAiSteps(null);
          }}
        />`
      : null}
  </div>`;
}
