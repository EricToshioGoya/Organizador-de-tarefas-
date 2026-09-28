// Campos de formulário: salvamento automático com debounce de 1 s (RN35), rascunhos (RF70) e autocompletar (RF05).
import { html, cx } from "../lib/html.js";
import { useEffect, useRef, useState, useMemo } from "preact/hooks";
import { Icon } from "./icons.js";
import { registerFlusher } from "../lib/queue.js";
import { loadDraft, saveDraft, clearDraft } from "../lib/drafts.js";
import { normalizeText } from "../lib/rules.js";

let fieldCounter = 0;
export const useFieldId = (prefix = "f") => useMemo(() => `${prefix}-${++fieldCounter}`, []);

export function Field({ label, hint, error, required, children, id, class: className }) {
  return html`<div class=${cx("field", className)}>
    ${label
      ? html`<label class="field-label" for=${id}>${label}${required ? html`<span class="req" aria-hidden="true">*</span>` : null}</label>`
      : null}
    ${children}
    ${error
      ? html`<div class="field-error" id=${id ? `${id}-err` : undefined} role="alert"><${Icon} name="alert" size=${13} />${error}</div>`
      : hint
        ? html`<div class="field-hint" id=${id ? `${id}-hint` : undefined}>${hint}</div>`
        : null}
  </div>`;
}

/**
 * Texto com salvamento automático: sem botão "Salvar" (RF06).
 * Grava 1 s após a última digitação (RN35) e ao sair do campo; guarda rascunho local (RF70).
 */
export function AutoText({
  value = "",
  onSave,
  multiline = false,
  placeholder,
  disabled,
  draftKey,
  validate,
  label,
  id,
  class: className,
  maxLength,
  rows,
  inputClass,
  ariaLabel,
}) {
  const [local, setLocal] = useState(value);
  const [error, setError] = useState(null);
  const [restored, setRestored] = useState(false);
  const focused = useRef(false);
  const dirty = useRef(false);
  const timer = useRef(null);
  const latest = useRef({ local: value, value, onSave });
  latest.current = { local, value, onSave };

  const commit = () => {
    clearTimeout(timer.current);
    if (!dirty.current) return;
    const { local: text, value: remote, onSave: save } = latest.current;
    const problem = validate ? validate(text) : null;
    setError(problem);
    if (problem) return;
    dirty.current = false;
    if (draftKey) clearDraft(draftKey);
    setRestored(false);
    if (text !== remote) save(text);
  };

  useEffect(() => {
    if (!draftKey || disabled) return;
    const draft = loadDraft(draftKey);
    if (draft !== null && draft !== value) {
      setLocal(draft);
      dirty.current = true;
      setRestored(true);
      timer.current = setTimeout(commit, 1000);
    }
  }, [draftKey]);

  useEffect(() => {
    if (!focused.current && !dirty.current) setLocal(value);
  }, [value]);

  useEffect(() => registerFlusher(commit), []);
  useEffect(() => () => commit(), []);

  const onInput = (event) => {
    const text = event.currentTarget.value;
    setLocal(text);
    dirty.current = true;
    if (draftKey) saveDraft(draftKey, text);
    if (error && validate && !validate(text)) setError(null);
    clearTimeout(timer.current);
    timer.current = setTimeout(commit, 1000);
  };

  const common = {
    id,
    value: local,
    placeholder,
    disabled,
    maxLength,
    "aria-label": ariaLabel || (label ? undefined : placeholder),
    "aria-invalid": error ? "true" : undefined,
    "aria-describedby": error && id ? `${id}-err` : undefined,
    onInput,
    onFocus: () => (focused.current = true),
    onBlur: () => {
      focused.current = false;
      commit();
    },
  };

  const control = multiline
    ? html`<textarea ...${common} rows=${rows || 3} class=${cx("textarea", inputClass)}></textarea>`
    : html`<input
        ...${common}
        type="text"
        class=${cx("input", inputClass)}
        onKeyDown=${(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
            event.currentTarget.blur();
          }
          if (event.key === "Escape") {
            dirty.current = false;
            clearTimeout(timer.current);
            if (draftKey) clearDraft(draftKey);
            setLocal(value);
            setError(null);
          }
        }}
      />`;

  if (!label && !error && !restored) return control;
  return html`<${Field} label=${label} id=${id} error=${error} class=${className} hint=${restored ? "Rascunho recuperado — salvando automaticamente." : null}>
    ${control}
  <//>`;
}

/** Campo com sugestões (RF05): lista navegável por teclado. */
export function Autocomplete({ value, onChange, onCommit, options = [], placeholder, id, disabled, ariaLabel }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = `${id || "ac"}-list`;
  const matches = useMemo(() => {
    const query = normalizeText(value || "");
    const list = options.filter((o) => o && (!query || normalizeText(o).includes(query)) && o !== value);
    return list.slice(0, 8);
  }, [value, options]);

  const choose = (option) => {
    onChange(option);
    onCommit?.(option);
    setOpen(false);
    setActive(-1);
  };

  return html`<div class="autocomplete">
    <input
      id=${id}
      class="input"
      type="text"
      value=${value}
      placeholder=${placeholder}
      disabled=${disabled}
      autocomplete="off"
      role="combobox"
      aria-label=${ariaLabel}
      aria-expanded=${open && matches.length ? "true" : "false"}
      aria-controls=${listId}
      aria-autocomplete="list"
      aria-activedescendant=${active >= 0 ? `${listId}-${active}` : undefined}
      onInput=${(event) => {
        onChange(event.currentTarget.value);
        setOpen(true);
        setActive(-1);
      }}
      onFocus=${() => setOpen(true)}
      onBlur=${() =>
        setTimeout(() => {
          setOpen(false);
          onCommit?.(value);
        }, 120)}
      onKeyDown=${(event) => {
        if (!open || !matches.length) {
          if (event.key === "Enter") onCommit?.(value);
          return;
        }
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setActive((i) => (i + 1) % matches.length);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setActive((i) => (i - 1 + matches.length) % matches.length);
        } else if (event.key === "Enter" && active >= 0) {
          event.preventDefault();
          choose(matches[active]);
        } else if (event.key === "Escape") {
          setOpen(false);
        }
      }}
    />
    ${open && matches.length
      ? html`<ul class="autocomplete-list" role="listbox" id=${listId}>
          ${matches.map(
            (option, index) => html`<li
              key=${option}
              id=${`${listId}-${index}`}
              role="option"
              aria-selected=${index === active ? "true" : "false"}
              onMouseDown=${(event) => {
                event.preventDefault();
                choose(option);
              }}
            >
              ${option}
            </li>`,
          )}
        </ul>`
      : null}
  </div>`;
}

export function DateInput({ value, onChange, id, disabled, ariaLabel, min }) {
  return html`<input
    id=${id}
    type="date"
    class="input"
    value=${value || ""}
    min=${min}
    disabled=${disabled}
    aria-label=${ariaLabel}
    onChange=${(event) => onChange(event.currentTarget.value || null)}
  />`;
}

export function Select({ value, onChange, options, id, disabled, ariaLabel, placeholder }) {
  return html`<select
    id=${id}
    class="select"
    value=${value ?? ""}
    disabled=${disabled}
    aria-label=${ariaLabel}
    onChange=${(event) => onChange(event.currentTarget.value || null)}
  >
    ${placeholder !== undefined ? html`<option value="">${placeholder}</option>` : null}
    ${options.map((o) => html`<option key=${o.value} value=${o.value}>${o.label}</option>`)}
  </select>`;
}
