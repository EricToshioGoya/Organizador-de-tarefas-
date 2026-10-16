// Aba Calendário: a semana em grade de horários, como no Outlook. Eventos com horário e de dia inteiro,
// repetição, entregas de tarefas e metas (filtráveis). Clicar ou arrastar num horário vazio cria um evento,
// arrastar um evento muda o dia/horário e a borda inferior muda o término; numa série, arrastar altera só
// aquela ocorrência. No calendário de outra conta, tudo fica em modo somente leitura.
import { html, cx } from "../lib/html.js";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Button, Chip, IconButton, Skeleton } from "../ui/core.js";
import { prefs } from "../lib/cache.js";
import { addDays, diffDays, parseDay, todayISO, weekdayShort } from "../lib/format.js";
import { isDone, isOverdue } from "../lib/rules.js";
import {
  DAY_MINUTES,
  HOUR_PX,
  SNAP,
  allDayLanes,
  dayLabel,
  daySegments,
  durationMinutes,
  fromMinutes,
  fromMoment,
  inAllDayRow,
  isISODate,
  moment,
  occurrencesBetween,
  weekDays,
  weekLabel,
  weekStart,
  whenLabel,
} from "../lib/calendar.js";
import { EntryModal } from "./CalendarEntry.js";
import { openTask } from "./TaskCard.js";
import { detachOccurrence, navigate, updateEntry } from "../actions.js";

const ALLDAY_LANES = 3; // linhas visíveis na faixa "Dia inteiro" antes do "+N"
const FIRST_HOUR = 7; // a grade abre rolada até as 7h
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

export function CalendarView() {
  const meId = useStore((s) => s.meId);
  const week = useStore((s) => s.route.params?.semana);
  return html`<div class="stack" style="gap:18px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Calendário</h1>
        <p class="page-subtitle">Clique ou arraste num horário para anotar um evento. Arraste um evento para mudar o dia ou o horário.</p>
      </div>
    </header>
    <${CalendarWeek} accountId=${meId} week=${week} basePath="calendario" />
  </div>`;
}

/** Item da faixa "Dia inteiro": evento, entrega de tarefa ou data-alvo de meta. */
function AllDayItem({ item, readOnly, ghost, dimmed, onOpen, onPointerDown }) {
  const style = `grid-column:${item.from + 2} / ${item.to + 3};grid-row:${item.lane + 1}`;
  if (item.kind === "task") {
    const { task } = item;
    const done = isDone(task);
    const late = !done && isOverdue(task);
    return html`<button
      type="button"
      class=${cx("cal-chip", "is-task", done && "is-done", late && "is-late")}
      style=${style}
      title=${`Entrega: ${task.title}${done ? " (concluída)" : late ? " (atrasada)" : ""}`}
      aria-label=${`Entrega da tarefa ${task.title}${done ? ", concluída" : late ? ", atrasada" : ""}`}
      onClick=${onOpen}
    >
      <${Icon} name=${done ? "checkCircle" : late ? "alert" : "circle"} size=${14} />
      <span class="truncate">${task.title}</span>
    </button>`;
  }
  if (item.kind === "goal") {
    return html`<button type="button" class="cal-chip is-goal" style=${style} title=${`Meta: ${item.goal.title}`} aria-label=${`Data-alvo da meta ${item.goal.title}`} onClick=${onOpen}>
      <${Icon} name="target" size=${14} />
      <span class="truncate">${item.goal.title}</span>
    </button>`;
  }
  const { occ } = item;
  const entry = occ.entry;
  const label = `${entry.title}, ${whenLabel(occ, { withDay: true })}${occ.recurring ? ", repete" : ""}${entry.private ? ", particular" : ""}`;
  return html`<button
    type="button"
    class=${cx("cal-chip", `ev-${entry.color}`, item.clippedStart && "clip-start", item.clippedEnd && "clip-end", ghost && "is-ghost", dimmed && "is-dimmed", readOnly && "is-readonly")}
    style=${style}
    title=${label}
    aria-label=${label}
    onClick=${onOpen}
    onPointerDown=${onPointerDown}
  >
    ${!occ.all_day ? html`<span class="cal-chip-time">${occ.start_time}</span>` : null}
    <span class="truncate">${entry.title}</span>
    ${occ.recurring ? html`<${Icon} name="repeat" size=${12} />` : null}
    ${entry.private ? html`<${Icon} name="lock" size=${12} />` : null}
  </button>`;
}

/** Evento com horário (um trecho por dia, se atravessar a meia-noite). */
function EventBlock({ segment, readOnly, ghost, dimmed, onOpen, onPointerDown, onResize }) {
  const { occ } = segment;
  const entry = occ.entry;
  const minutes = segment.end - segment.start;
  const short = minutes < 50;
  const top = (segment.start / 60) * HOUR_PX;
  const height = Math.max((minutes / 60) * HOUR_PX, 22) - 2;
  const style = `top:${top}px;height:${height}px;left:calc(${segment.col} * 100% / ${segment.cols} + 2px);width:calc(${segment.span || 1} * 100% / ${segment.cols} - 4px)`;
  const label = `${entry.title}, ${whenLabel(occ, { withDay: true })}${entry.location ? `, ${entry.location}` : ""}${occ.recurring ? ", repete" : ""}${entry.private ? ", particular" : ""}`;
  return html`<button
    type="button"
    class=${cx(
      "cal-event",
      `ev-${entry.color}`,
      short && "is-short",
      (occ.recurring || entry.private) && "has-icons",
      ghost && "is-ghost",
      dimmed && "is-dimmed",
      readOnly && "is-readonly",
      !segment.first && "cont-top",
      !segment.last && "cont-bottom",
    )}
    style=${style}
    title=${label}
    aria-label=${label}
    tabindex=${ghost ? -1 : undefined}
    onClick=${onOpen}
    onPointerDown=${onPointerDown}
  >
    <span class="cal-event-title">
      ${short && segment.first ? html`<span class="cal-event-time">${occ.start_time}</span> ` : null}${entry.title}
    </span>
    ${short ? null : html`<span class="cal-event-time">${whenLabel(occ)}</span>`}
    ${!short && entry.location ? html`<span class="cal-event-meta truncate">${entry.location}</span>` : null}
    ${occ.recurring || entry.private
      ? html`<span class="cal-event-icons" aria-hidden="true">
          ${occ.recurring ? html`<${Icon} name="repeat" size=${12} />` : null}${entry.private ? html`<${Icon} name="lock" size=${12} />` : null}
        </span>`
      : null}
    ${onResize && segment.last ? html`<span class="cal-resize" aria-hidden="true" onPointerDown=${onResize}></span>` : null}
  </button>`;
}

/** Semana em grade (aba Calendário e perfil de outra conta, em modo somente leitura). */
export function CalendarWeek({ accountId, week, basePath, readOnly = false }) {
  const board = useStore((s) => s.boards[accountId]);
  const owner = useStore((s) => (s.accounts || []).find((a) => a.id === accountId));
  const meId = useStore((s) => s.meId);
  const [now, setNow] = useState(() => new Date());
  const [filters, setFilters] = useState(() => ({ tasks: prefs.get("cal.tasks", true), goals: prefs.get("cal.goals", true) }));
  const [editing, setEditing] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [drag, setDragState] = useState(null);
  const dragRef = useRef(null);
  const scroller = useRef(null);
  const columns = useRef([]);
  const suppressUntil = useRef(0);
  const scrolled = useRef(false);

  const setDrag = (value) => {
    dragRef.current = value;
    setDragState(value);
  };

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const today = todayISO(now);
  const start = weekStart(isISODate(week) ? week : today);
  const days = weekDays(start);
  const end = days[6];

  // Abre nas 7h e, no celular (rolagem lateral), com o dia de hoje à vista.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (!scrolled.current) {
      el.scrollTop = FIRST_HOUR * HOUR_PX - 8;
      scrolled.current = true;
    }
    const index = days.indexOf(today);
    const column = columns.current[index];
    const gutter = columns.current[0] ? columns.current[0].getBoundingClientRect().left - el.getBoundingClientRect().left + el.scrollLeft : 0;
    el.scrollLeft = index > 0 && column ? column.getBoundingClientRect().left - el.getBoundingClientRect().left + el.scrollLeft - gutter : 0;
  }, [start, !!board]);

  const entries = board?.calendar || [];
  const occurrences = useMemo(() => entries.flatMap((entry) => occurrencesBetween(entry, start, end)), [entries, start]);
  const timed = occurrences.filter((occ) => !inAllDayRow(occ));
  const column = (iso) => clamp(diffDays(start, iso), 0, 6);

  const goalPath = (goal) => (readOnly ? `equipe/${accountId}/metas?meta=${goal.id}` : `metas/${goal.id}`);
  const allDay = useMemo(() => {
    const items = occurrences.filter(inAllDayRow).map((occ, order) => ({
      kind: "entry",
      key: occ.key,
      occ,
      from: column(occ.start_date),
      to: column(occ.end_date),
      clippedStart: occ.start_date < start,
      clippedEnd: occ.end_date > end,
      order,
    }));
    if (filters.tasks) {
      for (const task of board?.tasks || []) {
        if (task.due_date && task.due_date >= start && task.due_date <= end) {
          const at = column(task.due_date);
          items.push({ kind: "task", key: `task:${task.id}`, task, from: at, to: at, order: 1000 + (isDone(task) ? 500 : 0) });
        }
      }
    }
    if (filters.goals) {
      for (const goal of board?.goals || []) {
        if (goal.target_date && goal.target_date >= start && goal.target_date <= end) {
          const at = column(goal.target_date);
          items.push({ kind: "goal", key: `goal:${goal.id}`, goal, from: at, to: at, order: 900 });
        }
      }
    }
    return allDayLanes(items);
  }, [occurrences, board?.tasks, board?.goals, filters, start]);

  const collapsible = allDay.count > ALLDAY_LANES;
  const shownLanes = collapsible && !expanded ? ALLDAY_LANES - 1 : allDay.count;
  const hiddenPerDay = days.map((_, d) => allDay.items.filter((item) => item.lane >= shownLanes && item.from <= d && item.to >= d).length);
  const laneRows = Math.max(1, shownLanes + (hiddenPerDay.some(Boolean) ? 1 : 0));

  const go = (iso) => navigate(iso && iso !== weekStart(today) ? `${basePath}?semana=${iso}` : basePath);
  const toggleFilter = (key) =>
    setFilters((current) => {
      const next = { ...current, [key]: !current[key] };
      prefs.set(`cal.${key}`, next[key]);
      return next;
    });

  // ------------------------------------------------------------------------------------------
  // Criar, abrir, mover e redimensionar
  // ------------------------------------------------------------------------------------------

  const openNew = (preset) => !readOnly && setEditing({ entry: null, occurrence: null, preset });

  const openSlot = (day, from, to) =>
    openNew({
      all_day: false,
      start_date: day,
      start_time: fromMinutes(from),
      end_date: to >= DAY_MINUTES ? addDays(day, 1) : day,
      end_time: fromMinutes(to % DAY_MINUTES),
    });

  const newEvent = () => {
    const inWeek = days.includes(today);
    const minutes = now.getHours() * 60 + now.getMinutes();
    const from = inWeek ? Math.min(Math.ceil((minutes + 1) / 30) * 30, DAY_MINUTES - 60) : 9 * 60;
    openSlot(inWeek ? today : start, from, from + 60);
  };

  const openOccurrence = (occ) => {
    if (performance.now() < suppressUntil.current) return;
    setEditing({ entry: occ.entry, occurrence: occ.recurring ? occ.date : null });
  };

  const rects = () => columns.current.map((el) => el.getBoundingClientRect());
  const minuteAt = (y, rect) => clamp(((y - rect.top) / HOUR_PX) * 60, 0, DAY_MINUTES);
  const dayAt = (x, all) => all.reduce((found, rect, index) => (x >= rect.left ? index : found), 0);

  /** Arrasto com o mouse ou caneta; no toque, o gesto continua rolando a grade (toque abre o evento). */
  const track = (event, onMove, onDrop) => {
    if (readOnly || event.button !== 0 || event.pointerType === "touch") return false;
    const x0 = event.clientX;
    const y0 = event.clientY;
    let active = false;
    const move = (e) => {
      if (!active && Math.hypot(e.clientX - x0, e.clientY - y0) < 4) return;
      active = true;
      e.preventDefault();
      onMove(e);
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
    };
    const up = () => {
      stop();
      if (!active) return;
      suppressUntil.current = performance.now() + 400; // o clique que encerra o arrasto não abre nada
      onDrop(dragRef.current);
      setDrag(null);
    };
    const cancel = () => {
      stop();
      setDrag(null);
    };
    const key = (e) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      cancel();
      if (active) suppressUntil.current = performance.now() + 400;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
    return true;
  };

  const applySchedule = (occ, changes) => {
    if (occ.recurring) detachOccurrence(accountId, occ.entry.id, occ.date, changes);
    else updateEntry(accountId, occ.entry.id, changes);
  };

  const dropMove = (state) => {
    if (!state || (state.start === state.origin && state.end === state.originEnd)) return;
    const from = fromMoment(state.start);
    const to = fromMoment(state.end);
    applySchedule(state.occ, { all_day: false, start_date: from.date, start_time: from.time, end_date: to.date, end_time: to.time });
  };

  const onSlotPointerDown = (event, index) => {
    if (event.target.closest(".cal-event")) return;
    const all = rects();
    const anchor = Math.floor(minuteAt(event.clientY, all[index]) / SNAP) * SNAP;
    track(
      event,
      (e) => {
        const at = Math.floor(minuteAt(e.clientY, all[index]) / SNAP) * SNAP;
        setDrag({ type: "create", day: index, from: Math.min(anchor, at), to: Math.min(Math.max(anchor, at) + SNAP, DAY_MINUTES) });
      },
      (state) => state && openSlot(days[state.day], state.from, state.to),
    );
  };

  const onSlotClick = (event, index) => {
    if (readOnly || performance.now() < suppressUntil.current || event.target.closest(".cal-event")) return;
    const from = Math.min(Math.floor(minuteAt(event.clientY, columns.current[index].getBoundingClientRect()) / 30) * 30, DAY_MINUTES - 30);
    openSlot(days[index], from, Math.min(from + 60, DAY_MINUTES));
  };

  const onEventPointerDown = (event, segment, index) => {
    if (segment.occ.entry.redacted) return;
    event.stopPropagation();
    const all = rects();
    const occ = segment.occ;
    const origin = moment(occ.start_date, occ.start_time);
    const duration = durationMinutes(occ);
    const grab = minuteAt(event.clientY, all[index]) - segment.start;
    const segmentStart = moment(days[index], null) + segment.start;
    track(
      event,
      (e) => {
        const target = dayAt(e.clientX, all);
        const at = clamp(Math.round((minuteAt(e.clientY, all[target]) - grab) / SNAP) * SNAP, 0, DAY_MINUTES - SNAP);
        const delta = moment(days[target], null) + at - segmentStart;
        setDrag({ type: "move", key: occ.key, occ, origin, originEnd: origin + duration, start: origin + delta, end: origin + delta + duration });
      },
      dropMove,
    );
  };

  const onResizePointerDown = (event, segment, index) => {
    event.stopPropagation();
    const all = rects();
    const occ = segment.occ;
    const origin = moment(occ.start_date, occ.start_time);
    const originEnd = origin + durationMinutes(occ);
    const dayStart = moment(days[index], null);
    const started = track(
      event,
      (e) => {
        const at = clamp(Math.round(minuteAt(e.clientY, all[index]) / SNAP) * SNAP, segment.start + SNAP, DAY_MINUTES);
        setDrag({ type: "move", key: occ.key, occ, origin, originEnd, start: origin, end: dayStart + at });
      },
      dropMove,
    );
    if (started) event.preventDefault();
  };

  const onChipPointerDown = (event, item) => {
    if (item.kind !== "entry" || item.occ.entry.redacted) return;
    const all = rects();
    const from = dayAt(event.clientX, all);
    track(
      event,
      (e) => setDrag({ type: "shift", key: item.key, item, delta: dayAt(e.clientX, all) - from }),
      (state) => {
        if (!state?.delta) return;
        const occ = state.item.occ;
        const shift = (iso) => addDays(iso, state.delta);
        applySchedule(occ, {
          all_day: occ.all_day,
          start_date: shift(occ.start_date),
          end_date: shift(occ.end_date),
          start_time: occ.all_day ? null : occ.start_time,
          end_time: occ.all_day ? null : occ.end_time,
        });
      },
    );
  };

  // Prévia do arrasto: o evento na nova posição, com o original esmaecido
  const moving = drag?.type === "move" ? drag : null;
  const ghost = useMemo(() => {
    if (!moving) return null;
    const from = fromMoment(moving.start);
    const to = fromMoment(moving.end);
    return { ...moving.occ, key: `${moving.key}:ghost`, start_date: from.date, start_time: from.time, end_date: to.date, end_time: to.time };
  }, [moving]);

  if (!board) return html`<${Skeleton} count=${1} height=${520} />`;

  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  const visibleItems = allDay.items.filter((item) => item.lane < shownLanes);
  const shifting = drag?.type === "shift" ? drag : null;

  return html`<section class="cal" aria-label=${`Calendário${readOnly && owner ? ` de ${owner.name}` : ""}: semana de ${weekLabel(start)}`}>
    <div class="toolbar toolbar-row cal-toolbar" role="toolbar" aria-label="Navegação do calendário">
      <${Button} size="sm" onClick=${() => go(null)} disabled=${days.includes(today)}>Hoje<//>
      <div class="row" style="gap:0">
        <${IconButton} icon="chevronLeft" label="Semana anterior" onClick=${() => go(addDays(start, -7))} />
        <${IconButton} icon="chevronRight" label="Próxima semana" onClick=${() => go(addDays(start, 7))} />
      </div>
      <h2 class="cal-range" aria-live="polite">${weekLabel(start)}</h2>
      <input
        type="date"
        class="input cal-jump"
        value=${start}
        aria-label="Ir para a semana de uma data"
        title="Ir para a semana de uma data"
        onChange=${(e) => isISODate(e.currentTarget.value) && go(weekStart(e.currentTarget.value))}
      />
      <div class="grow"></div>
      <div class="chips" role="group" aria-label="Mostrar no calendário">
        <${Chip} pressed=${filters.tasks} onClick=${() => toggleFilter("tasks")}><${Icon} name="checkCircle" size=${15} />Entregas<//>
        <${Chip} pressed=${filters.goals} onClick=${() => toggleFilter("goals")}><${Icon} name="target" size=${15} />Metas<//>
      </div>
      ${readOnly ? null : html`<${Button} size="sm" variant="primary" icon="plus" onClick=${newEvent}>Novo evento<//>`}
    </div>

    <div class="cal-scroll" ref=${scroller}>
      <div class="cal-grid">
        <div class="cal-head">
          <div class="cal-corner"></div>
          ${days.map((day, index) => {
            const date = parseDay(day);
            return html`<div key=${day} class=${cx("cal-dayhead", day === today && "is-today", index >= 5 && "is-weekend")}>
              <span class="cal-dow">${weekdayShort(day)}</span>
              <span class="cal-date" aria-label=${dayLabel(day)}>${date.getDate()}</span>
            </div>`;
          })}
        </div>

        <div class="cal-allday" style=${`grid-template-rows:repeat(${laneRows}, var(--cal-lane-h))`} role="group" aria-label="Dia inteiro">
          <div class="cal-allday-label" style="grid-row:1 / -1">
            <span>Dia inteiro</span>
            ${collapsible
              ? html`<${IconButton}
                  icon=${expanded ? "chevronUp" : "chevronDown"}
                  size="sm"
                  iconSize=${15}
                  label=${expanded ? "Mostrar menos" : "Mostrar todos os itens de dia inteiro"}
                  onClick=${() => setExpanded(!expanded)}
                />`
              : null}
          </div>
          ${days.map(
            (day, index) => html`<div
              key=${day}
              class=${cx("cal-allday-cell", day === today && "is-today", readOnly && "is-readonly")}
              style=${`grid-column:${index + 2};grid-row:1 / -1`}
              onClick=${() => !readOnly && performance.now() >= suppressUntil.current && openNew({ all_day: true, start_date: day, end_date: day })}
            ></div>`,
          )}
          ${visibleItems.map(
            (item) => html`<${AllDayItem}
              key=${item.key}
              item=${item}
              readOnly=${readOnly || item.occ?.entry.redacted}
              dimmed=${shifting?.key === item.key}
              onOpen=${() => {
                if (performance.now() < suppressUntil.current) return;
                if (item.kind === "task") openTask(item.task);
                else if (item.kind === "goal") navigate(goalPath(item.goal));
                else openOccurrence(item.occ);
              }}
              onPointerDown=${(event) => onChipPointerDown(event, item)}
            />`,
          )}
          ${shifting
            ? html`<${AllDayItem}
                key="ghost"
                item=${{ ...shifting.item, from: clamp(shifting.item.from + shifting.delta, 0, 6), to: clamp(shifting.item.to + shifting.delta, 0, 6) }}
                ghost
              />`
            : null}
          ${hiddenPerDay.map((count, index) =>
            count
              ? html`<button
                  key=${`more-${index}`}
                  type="button"
                  class="cal-more"
                  style=${`grid-column:${index + 2};grid-row:${laneRows}`}
                  onClick=${() => setExpanded(true)}
                  aria-label=${`Mais ${count} ${count > 1 ? "itens" : "item"} de dia inteiro em ${dayLabel(days[index])}`}
                >
                  +${count}
                </button>`
              : null,
          )}
        </div>

        <div class="cal-body">
          <div class="cal-hours" aria-hidden="true">
            ${Array.from({ length: 23 }, (_, i) => html`<span key=${i} style=${`top:${(i + 1) * HOUR_PX}px`}>${String(i + 1).padStart(2, "0")}:00</span>`)}
          </div>
          ${days.map((day, index) => {
            const segments = daySegments(timed, day);
            const ghostSegments = ghost ? daySegments([ghost], day) : [];
            const creating = drag?.type === "create" && drag.day === index ? drag : null;
            return html`<div
              key=${day}
              ref=${(el) => (columns.current[index] = el)}
              class=${cx("cal-day", day === today && "is-today", index >= 5 && "is-weekend", readOnly && "is-readonly")}
              role="group"
              aria-label=${dayLabel(day)}
              onPointerDown=${(event) => onSlotPointerDown(event, index)}
              onClick=${(event) => onSlotClick(event, index)}
            >
              ${segments.map(
                (segment) => html`<${EventBlock}
                  key=${`${segment.occ.key}:${segment.start}`}
                  segment=${segment}
                  readOnly=${readOnly || segment.occ.entry.redacted}
                  dimmed=${moving?.key === segment.occ.key}
                  onOpen=${() => openOccurrence(segment.occ)}
                  onPointerDown=${(event) => onEventPointerDown(event, segment, index)}
                  onResize=${readOnly || segment.occ.entry.redacted ? null : (event) => onResizePointerDown(event, segment, index)}
                />`,
              )}
              ${ghostSegments.map((segment) => html`<${EventBlock} key=${`ghost:${segment.start}`} segment=${{ ...segment, col: 0, cols: 1, span: 1 }} ghost />`)}
              ${creating
                ? html`<div class="cal-selection" style=${`top:${(creating.from / 60) * HOUR_PX}px;height:${((creating.to - creating.from) / 60) * HOUR_PX}px`}>
                    ${fromMinutes(creating.from)} – ${creating.to >= DAY_MINUTES ? "24:00" : fromMinutes(creating.to)}
                  </div>`
                : null}
              ${day === today ? html`<div class="cal-now" style=${`top:${(nowMinutes / 60) * HOUR_PX}px`} aria-hidden="true"></div>` : null}
            </div>`;
          })}
        </div>
      </div>
    </div>

    ${editing
      ? html`<${EntryModal}
          accountId=${accountId}
          readOnly=${readOnly || accountId !== meId}
          owner=${owner}
          ...${editing}
          onClose=${() => setEditing(null)}
        />`
      : null}
  </section>`;
}
