// Calendário: datas da semana, repetição, validação e disposição dos eventos na grade.
// Espelha app/domain/calendar.py (mesmas regras de validação e o mesmo cálculo de ocorrências); o servidor
// continua sendo a fonte da verdade. Horários são locais e "flutuantes" (sem fuso), como numa agenda.
import { MONTHS, MONTHS_SHORT, addDays, diffDays, fmtDate, fmtDateShort, parseDay, weekdayShort } from "./format.js";

export const COLORS = [
  { key: "azul", label: "Azul" },
  { key: "verde", label: "Verde" },
  { key: "amarelo", label: "Amarelo" },
  { key: "laranja", label: "Laranja" },
  { key: "vermelho", label: "Vermelho" },
  { key: "roxo", label: "Roxo" },
  { key: "cinza", label: "Cinza" },
];

export const FREQS = [
  { key: "diaria", label: "Diariamente", one: "dia", many: "dias" },
  { key: "semanal", label: "Semanalmente", one: "semana", many: "semanas" },
  { key: "mensal", label: "Mensalmente", one: "mês", many: "meses" },
  { key: "anual", label: "Anualmente", one: "ano", many: "anos" },
];

// 0 = segunda … 6 = domingo (semana de segunda a domingo — RN23)
export const WEEKDAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
export const WEEKDAY_INITIALS = ["S", "T", "Q", "Q", "S", "S", "D"];

export const SCHEDULE_FIELDS = ["all_day", "start_date", "start_time", "end_date", "end_time"];
export const LOCATION_MAX = 200;
export const MAX_SPAN_DAYS = 366;
export const MAX_INTERVAL = 99;
export const HOUR_PX = 48; // altura de uma hora na grade
export const SNAP = 15; // minutos
export const DAY_MINUTES = 1440;

const EPOCH = "2000-01-03"; // uma segunda-feira: referência para contar minutos entre datas
const pad = (n) => String(n).padStart(2, "0");

// ---------------------------------------------------------------------------------------------
// Datas e horários
// ---------------------------------------------------------------------------------------------

/** Dia da semana com segunda = 0. */
export const weekdayIndex = (iso) => (parseDay(iso).getDay() + 6) % 7;
export const weekStart = (iso) => addDays(iso, -weekdayIndex(iso));
export const weekDays = (start) => Array.from({ length: 7 }, (_, i) => addDays(start, i));
export const isISODate = (value) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parseDay(value).getTime());
export const validTime = (value) => /^([01]\d|2[0-3]):([0-5]\d)$/.test(value || "");

export function toMinutes(hhmm) {
  const [hours, minutes] = hhmm.split(":").map(Number);
  return hours * 60 + minutes;
}

export const fromMinutes = (total) => `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;

/** Minutos desde a referência: permite somar durações que atravessam a meia-noite. */
export const moment = (date, time) => diffDays(EPOCH, date) * DAY_MINUTES + (time ? toMinutes(time) : 0);

export function fromMoment(total) {
  const days = Math.floor(total / DAY_MINUTES);
  return { date: addDays(EPOCH, days), time: fromMinutes(total - days * DAY_MINUTES) };
}

const startMoment = (e) => moment(e.start_date, e.all_day ? null : e.start_time);
const endMoment = (e) => (e.all_day ? moment(addDays(e.end_date, 1), null) : moment(e.end_date, e.end_time));
export const durationMinutes = (e) => endMoment(e) - startMoment(e);

// ---------------------------------------------------------------------------------------------
// Validação e normalização (espelho de clean_entry)
// ---------------------------------------------------------------------------------------------

/** Repetição normalizada e o início ajustado: na semanal, o 1º dia escolhido a partir do início. */
export function normalizeRecurrence(rule, startDate) {
  if (!rule || !rule.freq) return { recurrence: null, start: startDate };
  const interval = Number(rule.interval ?? 1);
  let weekdays = [];
  let start = startDate;
  if (rule.freq === "semanal") {
    weekdays = [...new Set((rule.weekdays?.length ? rule.weekdays : [weekdayIndex(startDate)]).map(Number))].sort((a, b) => a - b);
    const current = weekdayIndex(startDate);
    start = addDays(startDate, Math.min(...weekdays.map((d) => (d - current + 7) % 7)));
  }
  return { recurrence: { freq: rule.freq, interval, weekdays, until: rule.until || null }, start };
}

/** Aplica a normalização do servidor (útil para a atualização otimista). */
export function normalizeEntry(fields) {
  const { recurrence, start } = normalizeRecurrence(fields.recurrence, fields.start_date);
  const shift = diffDays(fields.start_date, start);
  const allDay = !!fields.all_day;
  return {
    ...fields,
    all_day: allDay,
    start_date: start,
    end_date: addDays(fields.end_date || fields.start_date, shift),
    start_time: allDay ? null : fields.start_time,
    end_time: allDay ? null : fields.end_time,
    recurrence,
  };
}

/** Primeiro problema de data/horário/repetição, com as mesmas mensagens do servidor; null se tudo certo. */
export function entryError(fields) {
  if (!isISODate(fields.start_date)) return "Informe a data de início.";
  const end = fields.end_date || fields.start_date;
  if (!isISODate(end)) return "Informe a data de término.";
  if (fields.all_day) {
    if (end < fields.start_date) return "O término deve ser no mesmo dia do início ou depois.";
  } else {
    if (!validTime(fields.start_time)) return "Horário de início inválido: use HH:MM.";
    if (!validTime(fields.end_time)) return "Horário de término inválido: use HH:MM.";
    if (moment(end, fields.end_time) <= moment(fields.start_date, fields.start_time)) return "O término deve ser depois do início.";
  }
  if (diffDays(fields.start_date, end) > MAX_SPAN_DAYS) return `Um evento pode durar no máximo ${MAX_SPAN_DAYS} dias.`;
  const rule = fields.recurrence;
  if (rule?.freq) {
    const interval = Number(rule.interval);
    if (!Number.isInteger(interval) || interval < 1 || interval > MAX_INTERVAL) return `O intervalo da repetição vai de 1 a ${MAX_INTERVAL}.`;
    if (rule.until) {
      if (!isISODate(rule.until)) return "Data final da repetição inválida.";
      if (rule.until < normalizeRecurrence(rule, fields.start_date).start) return "A repetição deve terminar no dia do início ou depois.";
    }
  }
  return null;
}

// ---------------------------------------------------------------------------------------------
// Ocorrências (espelho de occurs_on)
// ---------------------------------------------------------------------------------------------

/** Se uma ocorrência começa em `day`. Mensal/anual repetem o dia do início; meses sem esse dia ficam sem. */
export function occursOn(entry, day) {
  const start = entry.start_date;
  if (day < start || (entry.exceptions || []).includes(day)) return false;
  const rule = entry.recurrence;
  if (!rule) return day === start;
  if (rule.until && day > rule.until) return false;
  const interval = rule.interval || 1;
  const a = parseDay(start);
  const b = parseDay(day);
  switch (rule.freq) {
    case "diaria":
      return diffDays(start, day) % interval === 0;
    case "semanal": {
      const weeks = diffDays(weekStart(start), weekStart(day)) / 7;
      const days = rule.weekdays?.length ? rule.weekdays : [weekdayIndex(start)];
      return days.includes(weekdayIndex(day)) && weeks % interval === 0;
    }
    case "mensal": {
      const months = (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth();
      return b.getDate() === a.getDate() && months % interval === 0;
    }
    case "anual":
      return b.getMonth() === a.getMonth() && b.getDate() === a.getDate() && (b.getFullYear() - a.getFullYear()) % interval === 0;
    default:
      return false;
  }
}

/** Ocorrências que tocam o intervalo [from, to] (datas inclusivas), com as datas e horários de cada uma. */
export function occurrencesBetween(entry, from, to) {
  const span = diffDays(entry.start_date, entry.end_date);
  const make = (day) => ({
    key: `${entry.id}:${day}`,
    entry,
    date: day,
    all_day: entry.all_day,
    start_date: day,
    end_date: addDays(day, span),
    start_time: entry.start_time,
    end_time: entry.end_time,
    recurring: !!entry.recurrence,
  });
  if (!entry.recurrence) return entry.start_date <= to && entry.end_date >= from ? [make(entry.start_date)] : [];
  const out = [];
  const first = addDays(from, -span) > entry.start_date ? addDays(from, -span) : entry.start_date;
  for (let day = first; day <= to; day = addDays(day, 1)) if (occursOn(entry, day)) out.push(make(day));
  return out;
}

/** Evento de dia inteiro ou com 24 h ou mais vai para a faixa "Dia inteiro" (como no Google Agenda). */
export const inAllDayRow = (occ) => occ.all_day || durationMinutes(occ) >= DAY_MINUTES;

// ---------------------------------------------------------------------------------------------
// Disposição na grade
// ---------------------------------------------------------------------------------------------

const MIN_VISUAL = 30; // minutos: altura mínima de um evento na tela, também usada para detectar sobreposição

/** Trechos de eventos com horário em um dia: lado a lado quando se sobrepõem, cada um em `col` de `cols`
 * colunas e ocupando `span` colunas (as livres à direita). */
export function daySegments(occurrences, day) {
  const segments = [];
  for (const occ of occurrences) {
    if (occ.start_date > day || occ.end_date < day) continue;
    const start = occ.start_date === day ? toMinutes(occ.start_time) : 0;
    const end = occ.end_date === day ? toMinutes(occ.end_time) : DAY_MINUTES;
    if (end <= start) continue; // termina à meia-noite do dia anterior
    segments.push({ occ, start, end, first: occ.start_date === day, last: occ.end_date === day || (occ.end_date === addDays(day, 1) && occ.end_time === "00:00") });
  }
  segments.sort((a, b) => a.start - b.start || b.end - a.end);
  let group = [];
  let columns = [];
  let groupEnd = -1;
  const close = () => {
    for (const segment of group) {
      segment.cols = columns.length;
      // Ocupa as colunas livres à direita enquanto nenhum outro evento do grupo estiver nelas no mesmo horário
      segment.span = 1;
      const visualEnd = Math.max(segment.end, segment.start + MIN_VISUAL);
      while (
        segment.col + segment.span < columns.length &&
        !group.some((other) => other.col === segment.col + segment.span && other.start < visualEnd && Math.max(other.end, other.start + MIN_VISUAL) > segment.start)
      ) {
        segment.span += 1;
      }
    }
    group = [];
    columns = [];
  };
  for (const segment of segments) {
    if (group.length && segment.start >= groupEnd) close();
    const visualEnd = Math.max(segment.end, segment.start + MIN_VISUAL);
    let col = columns.findIndex((busyUntil) => busyUntil <= segment.start);
    if (col === -1) col = columns.push(0) - 1;
    columns[col] = visualEnd;
    segment.col = col;
    group.push(segment);
    groupEnd = Math.max(groupEnd, visualEnd);
  }
  close();
  return segments;
}

/** Faixa "Dia inteiro": itens com coluna inicial/final (0–6) distribuídos em linhas sem sobreposição. */
export function allDayLanes(items) {
  const sorted = [...items].sort((a, b) => a.from - b.from || b.to - b.from - (a.to - a.from) || a.order - b.order);
  const lanes = [];
  for (const item of sorted) {
    let lane = lanes.findIndex((busyUntil) => busyUntil < item.from);
    if (lane === -1) lane = lanes.push(-1) - 1;
    lanes[lane] = item.to;
    item.lane = lane;
  }
  return { items: sorted, count: lanes.length };
}

// ---------------------------------------------------------------------------------------------
// Textos
// ---------------------------------------------------------------------------------------------

/** "12 – 18 de outubro de 2026", "28 de setembro – 4 de outubro de 2026", "28 de dez. de 2026 – 3 de jan. de 2027". */
export function weekLabel(start) {
  const end = addDays(start, 6);
  const a = parseDay(start);
  const b = parseDay(end);
  if (a.getFullYear() !== b.getFullYear()) {
    return `${a.getDate()} de ${MONTHS_SHORT[a.getMonth()]}. de ${a.getFullYear()} – ${b.getDate()} de ${MONTHS_SHORT[b.getMonth()]}. de ${b.getFullYear()}`;
  }
  if (a.getMonth() !== b.getMonth()) return `${a.getDate()} de ${MONTHS[a.getMonth()]} – ${b.getDate()} de ${MONTHS[b.getMonth()]} de ${b.getFullYear()}`;
  return `${a.getDate()} – ${b.getDate()} de ${MONTHS[b.getMonth()]} de ${b.getFullYear()}`;
}

export function dayLabel(iso) {
  const date = parseDay(iso);
  return `${WEEKDAY_NAMES[weekdayIndex(iso)]}, ${date.getDate()} de ${MONTHS[date.getMonth()]}`;
}

const joinNames = (names) => (names.length > 1 ? `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}` : names[0] || "");

/** "Toda semana: segunda e quarta", "A cada 2 meses no dia 12", "Todo ano em 12 de outubro, até 31/12/2027". */
export function recurrenceLabel(rule, startDate) {
  if (!rule?.freq) return "Não repete";
  const n = rule.interval || 1;
  const start = parseDay(startDate);
  let text;
  switch (rule.freq) {
    case "diaria":
      text = n === 1 ? "Todos os dias" : `A cada ${n} dias`;
      break;
    case "semanal": {
      const days = rule.weekdays?.length ? rule.weekdays : [weekdayIndex(startDate)];
      const names = days.join() === "0,1,2,3,4" ? ", de segunda a sexta" : `: ${joinNames(days.map((d) => WEEKDAY_NAMES[d]))}`;
      text = `${n === 1 ? "Toda semana" : `A cada ${n} semanas`}${names}`;
      break;
    }
    case "mensal":
      text = `${n === 1 ? "Todo mês" : `A cada ${n} meses`} no dia ${start.getDate()}`;
      break;
    case "anual":
      text = `${n === 1 ? "Todo ano" : `A cada ${n} anos`} em ${start.getDate()} de ${MONTHS[start.getMonth()]}`;
      break;
    default:
      text = "Repete";
  }
  return rule.until ? `${text}, até ${fmtDate(rule.until)}` : text;
}

/** Quando acontece uma ocorrência: "09:00 – 10:00", "Dia inteiro", "Seg, 12/10 22:00 – Ter, 13/10 02:00". */
export function whenLabel(occ, { withDay = false } = {}) {
  const day = (iso) => `${weekdayShort(iso)}, ${fmtDateShort(iso)}`;
  if (occ.all_day) {
    if (occ.start_date === occ.end_date) return withDay ? `${day(occ.start_date)} · dia inteiro` : "Dia inteiro";
    return `${day(occ.start_date)} – ${day(occ.end_date)}`;
  }
  const endsNextMidnight = occ.end_date === addDays(occ.start_date, 1) && occ.end_time === "00:00";
  if (occ.start_date === occ.end_date || endsNextMidnight) {
    const range = `${occ.start_time} – ${endsNextMidnight ? "24:00" : occ.end_time}`;
    return withDay ? `${day(occ.start_date)} · ${range}` : range;
  }
  return `${day(occ.start_date)} ${occ.start_time} – ${day(occ.end_date)} ${occ.end_time}`;
}
