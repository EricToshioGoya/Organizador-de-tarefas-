// Aba Daily: tarefas simples do dia, como no Microsoft To Do. O que ficou pendente em dias anteriores aparece
// no topo de Hoje até ser concluído ou excluído; dá para navegar entre os dias e planejar os próximos.
// No perfil de outra conta, a Daily aparece em modo somente leitura.
import { html, cx } from "../lib/html.js";
import { useEffect, useRef, useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Button, Checkbox, EmptyState, IconButton, Skeleton } from "../ui/core.js";
import { AutoText, DateInput, useFieldId } from "../ui/forms.js";
import { prefs } from "../lib/cache.js";
import { addDays, fmtDate, fmtDateShort, fmtDateTime, fmtLongDate, todayISO } from "../lib/format.js";
import { TITLE_MAX } from "../lib/rules.js";
import { isISODate } from "../lib/calendar.js";
import { dailyLists, originLabel, relativeDay } from "../lib/daily.js";
import { createDailyItem, deleteDailyItem, navigate, updateDailyItem } from "../actions.js";

export function DailyView() {
  const meId = useStore((s) => s.meId);
  const day = useStore((s) => s.route.params?.dia);
  return html`<div class="stack" style="gap:18px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Daily</h1>
        <p class="page-subtitle">Tarefas simples do dia. O que ficar pendente aparece no topo de Hoje até ser concluído.</p>
      </div>
    </header>
    <${DailyDay} accountId=${meId} day=${day} basePath="daily" />
  </div>`;
}

const datesText = (item) =>
  `Planejada para ${fmtDate(item.day)}${item.done && item.done_at ? ` · concluída em ${fmtDateTime(item.done_at)}` : ""}`;

function DailyRow({ item, today, readOnly, origin, open, onToggle }) {
  const ids = { title: useFieldId("daily-title"), note: useFieldId("daily-note"), day: useFieldId("daily-day") };
  const update = (changes) => updateDailyItem(item.account_id, item.id, changes);
  const preview = item.note.split("\n").find((line) => line.trim()) || "";
  const tomorrow = addDays(today, 1);
  return html`<li class=${cx("daily-item", item.done && "is-done", open && "is-open")}>
    <div class="daily-row">
      <${Checkbox}
        round
        checked=${item.done}
        disabled=${readOnly}
        label=${item.done ? `Reabrir: ${item.title}` : `Concluir: ${item.title}`}
        onChange=${(done) => update({ done })}
      />
      <button type="button" class="daily-main" aria-expanded=${open ? "true" : "false"} onClick=${onToggle}>
        <span class="daily-title">${item.title}</span>
        ${origin || preview
          ? html`<span class="daily-meta">
              ${origin ? html`<span class="badge status-warning"><${Icon} name="history" />${origin}</span>` : null}
              ${preview ? html`<span class="daily-note-preview"><${Icon} name="note" size=${13} /><span class="truncate">${preview}</span></span>` : null}
            </span>`
          : null}
      </button>
      ${readOnly
        ? null
        : html`<${IconButton} icon="trash" size="sm" danger class="daily-delete" label=${`Excluir: ${item.title}`} onClick=${() => deleteDailyItem(item.account_id, item.id)} />`}
    </div>
    ${open
      ? html`<div class="daily-details">
          ${readOnly
            ? item.note
              ? html`<p class="entry-notes">${item.note}</p>`
              : html`<p class="small faint">Sem anotação.</p>`
            : html`
                <${AutoText}
                  id=${ids.title}
                  label="Título"
                  value=${item.title}
                  maxLength=${TITLE_MAX}
                  validate=${(text) => (text.trim() ? null : "O título é obrigatório.")}
                  onSave=${(title) => update({ title: title.trim() })}
                />
                <${AutoText}
                  id=${ids.note}
                  label="Anotação"
                  multiline
                  rows=${3}
                  placeholder="Detalhes, links, lembretes…"
                  value=${item.note}
                  draftKey=${`daily-note:${item.id}`}
                  onSave=${(note) => update({ note })}
                />
                <div class="row-wrap daily-move">
                  ${item.day !== today ? html`<${Button} size="sm" icon="sun" onClick=${() => update({ day: today })}>Para hoje<//>` : null}
                  ${item.day !== tomorrow ? html`<${Button} size="sm" icon="arrowRight" onClick=${() => update({ day: tomorrow })}>Para amanhã<//>` : null}
                  <label class="small muted" for=${ids.day}>Mover para</label>
                  <div class="daily-move-date">
                    <${DateInput} id=${ids.day} value=${item.day} onChange=${(day) => day && day !== item.day && update({ day })} />
                  </div>
                </div>
              `}
          <p class="xsmall faint">${datesText(item)}</p>
        </div>`
      : null}
  </li>`;
}

function emptyText(current, today, readOnly) {
  if (current < today) return { title: "Nada neste dia", text: "Nenhuma tarefa foi planejada para este dia." };
  if (readOnly) return { title: "Nada planejado", text: "Nenhuma tarefa na Daily deste dia." };
  if (current === today) {
    return { title: "Nada para hoje ainda", text: "Adicione as tarefas simples que você quer fazer hoje. O que ficar pendente aparece aqui amanhã." };
  }
  return { title: "Planeje o dia", text: "Adicione o que você precisa fazer neste dia." };
}

/** Um dia da Daily (aba Daily e perfil de outra conta, em modo somente leitura). */
export function DailyDay({ accountId, day, basePath, readOnly = false }) {
  const board = useStore((s) => s.boards[accountId]);
  const [now, setNow] = useState(() => new Date());
  const [text, setText] = useState("");
  const [openId, setOpenId] = useState(null);
  const [showDone, setShowDone] = useState(() => prefs.get("daily.done", true));
  const input = useRef(null);

  // Atualiza "hoje" na virada do dia: as pendências de ontem passam a aparecer no topo
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const today = todayISO(now);
  const current = isISODate(day) ? day : today;
  const go = (iso) => navigate(iso && iso !== today ? `${basePath}?dia=${iso}` : basePath);

  if (!board) return html`<${Skeleton} count=${3} height=${64} />`;

  const { carried, pending, done } = dailyLists(board.daily || [], current, today);
  const relative = relativeDay(current, today);
  const empty = !carried.length && !pending.length && !done.length;
  const add = () => {
    const title = text.trim();
    if (!title) return;
    createDailyItem(accountId, { title, day: current });
    setText("");
    input.current?.focus();
  };
  const toggleDone = () => {
    prefs.set("daily.done", !showDone);
    setShowDone(!showDone);
  };
  const row = (item, origin = null) => html`<${DailyRow}
    key=${item.id}
    item=${item}
    today=${today}
    readOnly=${readOnly}
    origin=${origin}
    open=${openId === item.id}
    onToggle=${() => setOpenId(openId === item.id ? null : item.id)}
  />`;
  const message = emptyText(current, today, readOnly);

  return html`<section class="stack" style="gap:12px" aria-label=${`Daily de ${fmtLongDate(current)}`}>
    <div class="toolbar toolbar-row daily-toolbar" role="toolbar" aria-label="Navegação da Daily">
      <${Button} size="sm" onClick=${() => go(null)} disabled=${current === today}>Hoje<//>
      <div class="row" style="gap:0">
        <${IconButton} icon="chevronLeft" label="Dia anterior" onClick=${() => go(addDays(current, -1))} />
        <${IconButton} icon="chevronRight" label="Próximo dia" onClick=${() => go(addDays(current, 1))} />
      </div>
      <h2 class="daily-date" aria-live="polite">${fmtLongDate(current)}${relative ? html`<span class="faint"> · ${relative}</span>` : null}</h2>
      <div class="grow"></div>
      <input
        type="date"
        class="input cal-jump"
        value=${current}
        aria-label="Ir para um dia"
        title="Ir para um dia"
        onChange=${(e) => isISODate(e.currentTarget.value) && go(e.currentTarget.value)}
      />
    </div>

    <div class="block daily">
      ${readOnly
        ? null
        : html`<form class="daily-add" onSubmit=${(e) => (e.preventDefault(), add())}>
            <${Icon} name="plus" />
            <input
              ref=${input}
              class="input daily-add-input"
              maxLength=${TITLE_MAX}
              value=${text}
              autocomplete="off"
              placeholder=${current === today ? "Adicionar uma tarefa" : `Adicionar tarefa para ${fmtDateShort(current)}`}
              aria-label="Nova tarefa da Daily"
              onInput=${(e) => setText(e.currentTarget.value)}
              onKeyDown=${(e) => e.key === "Escape" && setText("")}
            />
            <${Button} type="submit" size="sm" variant="primary" disabled=${!text.trim()}>Adicionar<//>
          </form>`}
      ${carried.length
        ? html`<div class="daily-group">
            <h3 class="daily-group-title tone-warning"><${Icon} name="history" />De dias anteriores <span class="counter">${carried.length}</span></h3>
            <ul class="daily-items">${carried.map((item) => row(item, originLabel(item.day, today)))}</ul>
          </div>`
        : null}
      ${pending.length
        ? html`<div class="daily-group">
            ${current < today
              ? html`<h3 class="daily-group-title">Pendentes <span class="counter">${pending.length}</span><span class="faint" style="font-weight:400">· aparecem em Hoje</span></h3>`
              : null}
            <ul class="daily-items">${pending.map((item) => row(item))}</ul>
          </div>`
        : null}
      ${empty ? html`<div class="daily-group"><${EmptyState} compact icon="checkSquare" title=${message.title} text=${message.text} /></div>` : null}
      ${done.length
        ? html`<div class="daily-group">
            <button type="button" class="daily-group-title daily-done-toggle" aria-expanded=${showDone ? "true" : "false"} onClick=${toggleDone}>
              <${Icon} name=${showDone ? "chevronDown" : "chevronRight"} />Concluídas <span class="counter">${done.length}</span>
            </button>
            ${showDone ? html`<ul class="daily-items">${done.map((item) => row(item, item.day < current ? originLabel(item.day, today) : null))}</ul>` : null}
          </div>`
        : null}
    </div>
  </section>`;
}
