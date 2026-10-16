// Evento do calendário: formulário de criação e edição (com repetição), detalhes em modo somente leitura e
// escolha do que excluir num evento que se repete. Como no Outlook, abrir uma ocorrência edita só ela
// (que vira um evento avulso); "Editar a série" altera todas.
import { html, cx } from "../lib/html.js";
import { useState } from "preact/hooks";
import { Modal } from "../ui/overlay.js";
import { Badge, Banner, Button, Checkbox, Segmented } from "../ui/core.js";
import { DateInput, Field, Select, useFieldId } from "../ui/forms.js";
import { Icon } from "../ui/icons.js";
import {
  COLORS,
  FREQS,
  LOCATION_MAX,
  MAX_INTERVAL,
  SCHEDULE_FIELDS,
  WEEKDAY_INITIALS,
  WEEKDAY_NAMES,
  entryError,
  fromMoment,
  moment,
  normalizeEntry,
  recurrenceLabel,
  validTime,
  weekdayIndex,
  whenLabel,
} from "../lib/calendar.js";
import { TITLE_MAX } from "../lib/rules.js";
import { addDays, diffDays, fmtDateShort, weekdayShort } from "../lib/format.js";
import { confirmDialog, createEntry, deleteEntry, detachOccurrence, excludeOccurrence, updateEntry } from "../actions.js";

const TEXT_FIELDS = ["title", "notes", "location", "color", "private"];

/** Campos do evento como formulário; numa ocorrência, com as datas dela e sem repetição própria. */
function toForm(entry, occurrence) {
  const start = occurrence || entry.start_date;
  const rule = entry.recurrence;
  return {
    title: entry.title,
    notes: entry.notes || "",
    location: entry.location || "",
    color: entry.color || "azul",
    private: !!entry.private,
    all_day: !!entry.all_day,
    start_date: start,
    end_date: addDays(start, diffDays(entry.start_date, entry.end_date)),
    start_time: entry.start_time || "09:00",
    end_time: entry.end_time || "10:00",
    freq: rule?.freq || "",
    interval: rule?.interval || 1,
    weekdays: rule?.weekdays?.length ? rule.weekdays : [weekdayIndex(start)],
    ends: rule?.until ? "date" : "never",
    until: rule?.until || null,
  };
}

/** Formulário → campos da API (mesmo formato do servidor). */
function toData(form) {
  return {
    title: form.title.trim(),
    notes: form.notes,
    location: form.location.trim(),
    color: form.color,
    private: form.private,
    all_day: form.all_day,
    start_date: form.start_date,
    end_date: form.end_date || form.start_date,
    start_time: form.all_day ? null : form.start_time,
    end_time: form.all_day ? null : form.end_time,
    recurrence: form.freq
      ? {
          freq: form.freq,
          interval: Number(form.interval),
          weekdays: form.freq === "semanal" ? [...form.weekdays].sort((a, b) => a - b) : [],
          until: form.ends === "date" ? form.until : null,
        }
      : null,
  };
}

/** Só o que mudou: evita que um campo não alterado sobrescreva a mudança feita em outro aparelho (RN30). */
function changesFrom(before, data, { withRecurrence = true } = {}) {
  const changes = {};
  for (const field of TEXT_FIELDS) if (data[field] !== before[field]) changes[field] = data[field];
  if (SCHEDULE_FIELDS.some((field) => (data[field] ?? null) !== (before[field] ?? null))) {
    for (const field of SCHEDULE_FIELDS) changes[field] = data[field];
  }
  if (withRecurrence && JSON.stringify(normalizeEntry(data).recurrence) !== JSON.stringify(before.recurrence ?? null)) {
    changes.recurrence = data.recurrence;
  }
  return changes;
}

function ColorPicker({ value, onChange, id }) {
  const move = (step) => {
    const index = COLORS.findIndex((c) => c.key === value);
    onChange(COLORS[(index + step + COLORS.length) % COLORS.length].key);
  };
  return html`<div class="color-picker" role="radiogroup" aria-labelledby=${id}>
    ${COLORS.map(
      (color) => html`<button
        key=${color.key}
        type="button"
        role="radio"
        class=${cx("swatch", `ev-${color.key}`)}
        aria-checked=${value === color.key ? "true" : "false"}
        aria-label=${color.label}
        title=${color.label}
        tabindex=${value === color.key ? 0 : -1}
        onClick=${() => onChange(color.key)}
        onKeyDown=${(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            event.preventDefault();
            move(1);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
            event.preventDefault();
            move(-1);
          }
        }}
      >
        ${value === color.key ? html`<${Icon} name="check" size=${16} strokeWidth=${2.6} />` : null}
      </button>`,
    )}
  </div>`;
}

function RecurrenceFields({ form, update, ids }) {
  const freq = FREQS.find((f) => f.key === form.freq);
  const toggleDay = (day) => {
    const on = form.weekdays.includes(day);
    if (on && form.weekdays.length === 1) return; // ao menos um dia
    update({ weekdays: on ? form.weekdays.filter((d) => d !== day) : [...form.weekdays, day] });
  };
  return html`<div class="recurrence">
    <div class="row-wrap">
      <label class="small muted" for=${ids.interval}>A cada</label>
      <input
        id=${ids.interval}
        class="input interval-input"
        type="number"
        inputmode="numeric"
        min="1"
        max=${MAX_INTERVAL}
        value=${form.interval}
        onInput=${(e) => update({ interval: e.currentTarget.value })}
      />
      <span class="small muted">${Number(form.interval) === 1 ? freq.one : freq.many}</span>
    </div>
    ${form.freq === "semanal"
      ? html`<div class="weekday-picker" role="group" aria-label="Dias da semana">
          ${WEEKDAY_INITIALS.map(
            (letter, day) => html`<button
              key=${day}
              type="button"
              class="weekday"
              aria-pressed=${form.weekdays.includes(day) ? "true" : "false"}
              aria-label=${WEEKDAY_NAMES[day]}
              title=${WEEKDAY_NAMES[day]}
              onClick=${() => toggleDay(day)}
            >
              ${letter}
            </button>`,
          )}
        </div>`
      : null}
    <div class="row-wrap">
      <span class="small muted" id=${ids.ends}>Termina</span>
      <${Segmented}
        size="sm"
        label="Quando a repetição termina"
        value=${form.ends}
        onChange=${(ends) => update({ ends, until: form.until || addDays(form.start_date, 90) })}
        options=${[
          { value: "never", label: "Nunca" },
          { value: "date", label: "Em uma data" },
        ]}
      />
      ${form.ends === "date"
        ? html`<div style="width:170px"><${DateInput} value=${form.until} min=${form.start_date} ariaLabel="Data final da repetição" onChange=${(until) => update({ until })} /></div>`
        : null}
    </div>
    <p class="xsmall faint"><${Icon} name="repeat" size=${13} style="display:inline;vertical-align:-2px" /> ${recurrenceLabel(toData(form).recurrence, normalizeEntry(toData(form)).start_date)}</p>
  </div>`;
}

/** Excluir num evento que se repete: só esta ocorrência, esta e as seguintes, ou todas. */
function DeleteScopeModal({ occurrence, onChoose, onClose }) {
  const [scope, setScope] = useState("one");
  const options = [
    { value: "one", label: `Só esta ocorrência (${weekdayShort(occurrence)}, ${fmtDateShort(occurrence)})` },
    { value: "following", label: "Esta e as seguintes" },
    { value: "all", label: "Todas as ocorrências" },
  ];
  return html`<${Modal}
    title="Excluir evento que se repete"
    icon="repeat"
    size="sm"
    onClose=${onClose}
    footer=${html`<${Button} variant="ghost" onClick=${onClose}>Cancelar<//><${Button} variant="danger" icon="trash" onClick=${() => onChoose(scope)}>Excluir<//>`}
  >
    <div class="stack" style="gap:8px" role="radiogroup" aria-label="O que excluir">
      ${options.map(
        (option) => html`<label key=${option.value} class="list-item boxed scope-option">
          <input type="radio" name="delete-scope" value=${option.value} checked=${scope === option.value} onChange=${() => setScope(option.value)} data-autofocus=${scope === option.value ? true : undefined} />
          <span class="grow">${option.label}</span>
        </label>`,
      )}
    </div>
  <//>`;
}

/** Detalhes em modo somente leitura (calendário de outra conta). */
function EntryDetails({ entry, occurrence, owner, onClose }) {
  const occ = { ...entry, start_date: occurrence || entry.start_date, end_date: addDays(occurrence || entry.start_date, diffDays(entry.start_date, entry.end_date)) };
  return html`<${Modal}
    title=${entry.title}
    icon="calendar"
    size="sm"
    onClose=${onClose}
    footer=${html`<${Button} variant="primary" data-autofocus onClick=${onClose}>Fechar<//>`}
  >
    <div class="stack entry-details" style="gap:12px">
      <div class="row"><span class=${cx("ev-dot", `ev-${entry.color}`)} aria-hidden="true"></span><strong>${whenLabel(occ, { withDay: true })}</strong></div>
      ${entry.recurrence ? html`<div class="row small muted"><${Icon} name="repeat" size=${16} />${recurrenceLabel(entry.recurrence, entry.start_date)}</div>` : null}
      ${entry.location ? html`<div class="row small muted"><${Icon} name="mapPin" size=${16} />${entry.location}</div>` : null}
      ${entry.notes ? html`<p class="entry-notes">${entry.notes}</p>` : null}
      ${entry.redacted
        ? html`<p class="small faint"><${Icon} name="lock" size=${14} style="display:inline;vertical-align:-2px" /> Evento particular: só o horário fica visível para as outras contas.</p>`
        : entry.private
          ? html`<${Badge} icon="lock" class="neutral">Particular<//>`
          : null}
      ${owner ? html`<p class="xsmall faint">Calendário de ${owner.name} · somente leitura</p>` : null}
    </div>
  <//>`;
}

/**
 * Formulário do evento. `entry` ausente = novo evento (com `preset` de datas/horários). Com `occurrence`
 * (data de uma ocorrência de um evento que se repete), abre editando só ela.
 */
export function EntryModal({ entry, readOnly, ...props }) {
  if (entry && (readOnly || entry.redacted)) return html`<${EntryDetails} entry=${entry} ...${props} />`;
  return html`<${EntryForm} entry=${entry} ...${props} />`;
}

function EntryForm({ accountId, entry, occurrence, preset = {}, onClose }) {
  const recurring = !!entry?.recurrence;
  const [mode, setMode] = useState(recurring && occurrence ? "occurrence" : "series");
  const blank = { title: "", notes: "", location: "", color: "azul", private: false, recurrence: null, start_date: preset.start_date, end_date: preset.start_date, ...preset };
  const [form, setForm] = useState(() => toForm(entry || blank, mode === "occurrence" ? occurrence : null));
  const [error, setError] = useState(null);
  const [askScope, setAskScope] = useState(false);
  const ids = {
    title: useFieldId("ev-title"),
    start: useFieldId("ev-start"),
    end: useFieldId("ev-end"),
    freq: useFieldId("ev-freq"),
    interval: useFieldId("ev-interval"),
    ends: useFieldId("ev-ends"),
    location: useFieldId("ev-location"),
    color: useFieldId("ev-color"),
    notes: useFieldId("ev-notes"),
  };

  const update = (patch) => {
    setForm((current) => ({ ...current, ...patch }));
    if (error) setError(null);
  };

  /** Mover o início leva o término junto, mantendo a duração (como no Outlook). */
  const moveStart = (patch) => {
    setForm((current) => {
      const next = { ...current, ...patch };
      const times = current.all_day || (validTime(current.start_time) && validTime(current.end_time) && validTime(next.start_time));
      if (current.start_date && current.end_date && next.start_date && times) {
        const startOf = (f) => moment(f.start_date, f.all_day ? null : f.start_time);
        const duration = moment(current.end_date, current.all_day ? null : current.end_time) - startOf(current);
        const end = fromMoment(startOf(next) + duration);
        next.end_date = end.date;
        if (!next.all_day) next.end_time = end.time;
      }
      if (next.freq === "semanal" && patch.start_date && current.weekdays.length === 1 && current.weekdays[0] === weekdayIndex(current.start_date)) {
        next.weekdays = [weekdayIndex(next.start_date)]; // repetição seguia o dia do início
      }
      return next;
    });
    if (error) setError(null);
  };

  const switchMode = (next) => {
    setMode(next);
    setForm(toForm(entry, next === "occurrence" ? occurrence : null));
    setError(null);
  };

  const submit = () => {
    const data = toData(form);
    if (mode === "occurrence") data.recurrence = null;
    if (!data.title) {
      setError({ field: "title", message: "O título é obrigatório." });
      return;
    }
    const problem = entryError(data);
    if (problem) {
      setError({ field: problem.includes("repetição") ? "recurrence" : "when", message: problem });
      return;
    }
    if (!entry) {
      createEntry(accountId, data);
    } else if (mode === "occurrence") {
      const changes = changesFrom({ ...toData(toForm(entry, occurrence)), recurrence: null }, data, { withRecurrence: false });
      if (Object.keys(changes).length) detachOccurrence(accountId, entry.id, occurrence, changes);
    } else {
      const changes = changesFrom(entry, data);
      if (Object.keys(changes).length) updateEntry(accountId, entry.id, changes, { success: "Evento atualizado." });
    }
    onClose();
  };

  const remove = async () => {
    if (recurring && mode === "occurrence") {
      setAskScope(true);
      return;
    }
    const ok = await confirmDialog({
      title: recurring ? "Excluir todas as ocorrências?" : "Excluir evento?",
      text: `“${entry.title}” será excluído${recurring ? " com todas as ocorrências" : ""}. Esta ação não pode ser desfeita.`,
      confirmLabel: "Excluir",
      danger: true,
    });
    if (!ok) return;
    deleteEntry(accountId, entry.id);
    onClose();
  };

  const removeScope = (scope) => {
    setAskScope(false);
    if (scope === "one") excludeOccurrence(accountId, entry.id, occurrence);
    else if (scope === "all" || occurrence <= entry.start_date) deleteEntry(accountId, entry.id, { success: "Evento excluído com todas as ocorrências." });
    else updateEntry(accountId, entry.id, { recurrence: { ...entry.recurrence, until: addDays(occurrence, -1) } }, { success: "Ocorrências excluídas a partir desta data." });
    onClose();
  };

  const title = !entry ? "Novo evento" : mode === "occurrence" ? "Editar ocorrência" : recurring ? "Editar série" : "Editar evento";

  return html`<${Modal}
    title=${title}
    icon="calendar"
    onClose=${onClose}
    footer=${html`
      ${entry ? html`<${Button} variant="danger" icon="trash" style="margin-right:auto" onClick=${remove}>Excluir<//>` : null}
      <${Button} variant="ghost" onClick=${onClose}>Cancelar<//>
      <${Button} variant="primary" icon="check" onClick=${submit}>Salvar<//>
    `}
  >
    <form class="stack entry-form" style="gap:16px" onSubmit=${(e) => (e.preventDefault(), submit())}>
      ${recurring
        ? html`<${Banner}
            icon="repeat"
            action=${occurrence
              ? html`<${Button} size="sm" variant="ghost" onClick=${() => switchMode(mode === "occurrence" ? "series" : "occurrence")}>
                  ${mode === "occurrence" ? "Editar a série" : "Só esta ocorrência"}
                <//>`
              : null}
          >
            ${mode === "occurrence"
              ? html`<strong>Só esta ocorrência.</strong> ${recurrenceLabel(entry.recurrence, entry.start_date)}.`
              : html`<strong>Série inteira.</strong> As mudanças valem para todas as ocorrências.`}
          <//>`
        : null}

      <${Field} label="Título" required id=${ids.title} error=${error?.field === "title" ? error.message : null}>
        <input
          id=${ids.title}
          class="input input-title"
          data-autofocus
          maxLength=${TITLE_MAX}
          placeholder="Ex.: Reunião com o cliente"
          value=${form.title}
          aria-invalid=${error?.field === "title" ? "true" : undefined}
          onInput=${(e) => update({ title: e.currentTarget.value })}
        />
      <//>

      <div class="when-grid">
        <${Field} label="Início" id=${ids.start}>
          <div class="when-row">
            <${DateInput} id=${ids.start} value=${form.start_date} ariaLabel="Data de início" onChange=${(start_date) => start_date && moveStart({ start_date })} />
            ${form.all_day
              ? null
              : html`<input class="input time-input" type="time" step="900" aria-label="Horário de início" value=${form.start_time} onInput=${(e) => moveStart({ start_time: e.currentTarget.value })} />`}
          </div>
        <//>
        <${Field} label="Término" id=${ids.end}>
          <div class="when-row">
            <${DateInput} id=${ids.end} value=${form.end_date} min=${form.start_date} ariaLabel="Data de término" onChange=${(end_date) => end_date && update({ end_date })} />
            ${form.all_day
              ? null
              : html`<input class="input time-input" type="time" step="900" aria-label="Horário de término" value=${form.end_time} onInput=${(e) => update({ end_time: e.currentTarget.value })} />`}
          </div>
        <//>
      </div>
      ${error?.field === "when" ? html`<div class="field-error" role="alert" style="margin-top:-6px"><${Icon} name="alert" size=${13} />${error.message}</div>` : null}
      <label class="check-row">
        <${Checkbox} size="sm" checked=${form.all_day} label="Dia inteiro" onChange=${(all_day) => update({ all_day })} />
        <span>Dia inteiro</span>
      </label>

      ${mode === "occurrence"
        ? null
        : html`<${Field} label="Repetir" id=${ids.freq}>
            <${Select}
              id=${ids.freq}
              value=${form.freq}
              placeholder="Não repete"
              options=${FREQS.map((f) => ({ value: f.key, label: f.label }))}
              onChange=${(freq) => update({ freq: freq || "", weekdays: form.weekdays.length ? form.weekdays : [weekdayIndex(form.start_date)] })}
            />
            ${form.freq ? html`<${RecurrenceFields} form=${form} update=${update} ids=${ids} />` : null}
            ${error?.field === "recurrence" ? html`<div class="field-error" role="alert"><${Icon} name="alert" size=${13} />${error.message}</div>` : null}
          <//>`}

      <${Field} label="Local" id=${ids.location}>
        <input id=${ids.location} class="input" maxLength=${LOCATION_MAX} placeholder="Ex.: Sala 3, Teams" value=${form.location} onInput=${(e) => update({ location: e.currentTarget.value })} />
      <//>

      <div class="row-wrap" style="gap:16px 28px;align-items:flex-end">
        <div class="field">
          <span class="field-label" id=${ids.color}>Cor</span>
          <${ColorPicker} id=${ids.color} value=${form.color} onChange=${(color) => update({ color })} />
        </div>
        <label class="check-row" title="Para as outras contas, aparece só como Ocupado.">
          <${Checkbox} size="sm" checked=${form.private} label="Particular" onChange=${(on) => update({ private: on })} />
          <span><${Icon} name="lock" size=${14} style="display:inline;vertical-align:-2px" /> Particular</span>
        </label>
      </div>
      ${form.private ? html`<p class="xsmall faint" style="margin-top:-8px">Para as outras contas, este evento aparece só como “Ocupado”, sem título, local nem anotações.</p>` : null}

      <${Field} label="Anotações" id=${ids.notes}>
        <textarea id=${ids.notes} class="textarea" rows="4" placeholder="Pauta, links, lembretes…" value=${form.notes} onInput=${(e) => update({ notes: e.currentTarget.value })}></textarea>
      <//>

      <button type="submit" hidden>Salvar</button>
    </form>
    ${askScope ? html`<${DeleteScopeModal} occurrence=${occurrence} onChoose=${removeScope} onClose=${() => setAskScope(false)} />` : null}
  <//>`;
}
