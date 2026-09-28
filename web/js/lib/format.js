// Formatação em pt-BR: datas dd/mm/aaaa no fuso local (RNF16), números e tamanhos.

export const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Sao_Paulo";

const WEEKDAYS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
const WEEKDAYS_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
export const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const pad = (n) => String(n).padStart(2, "0");

/** Data local de hoje no formato AAAA-MM-DD. */
export function todayISO(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Converte AAAA-MM-DD em Date local (meio-dia, imune a mudanças de horário de verão). */
export function parseDay(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d, 12);
}

export function addDays(iso, days) {
  const date = parseDay(iso);
  date.setDate(date.getDate() + days);
  return todayISO(date);
}

export function diffDays(fromIso, toIso) {
  return Math.round((parseDay(toIso) - parseDay(fromIso)) / 86_400_000);
}

/** Data local (AAAA-MM-DD) de um instante ISO. */
export function localDay(isoInstant) {
  return isoInstant ? todayISO(new Date(isoInstant)) : null;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function fmtDateShort(iso) {
  if (!iso) return "—";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

export function fmtDateTime(isoInstant) {
  if (!isoInstant) return "—";
  const date = new Date(isoInstant);
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fmtTime(isoInstant) {
  const date = new Date(isoInstant);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fmtLongDate(iso) {
  const date = parseDay(iso);
  const text = `${WEEKDAYS[date.getDay()]}, ${date.getDate()} de ${MONTHS[date.getMonth()]}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function weekdayShort(iso) {
  return WEEKDAYS_SHORT[parseDay(iso).getDay()];
}

/** Rótulo relativo da entrega: "Hoje", "Amanhã", "Atrasada há 2 dias", "Em 5 dias", "Sex, 25/09". */
export function dueLabel(due, today = todayISO()) {
  if (!due) return "Sem data";
  const days = diffDays(today, due);
  if (days === 0) return "Hoje";
  if (days === 1) return "Amanhã";
  if (days === -1) return "Ontem";
  if (days < 0) return `${fmtDateShort(due)} · há ${-days} dias`;
  if (days <= 6) return `${weekdayShort(due)}, ${fmtDateShort(due)}`;
  return fmtDate(due);
}

export function relativeTime(isoInstant, now = Date.now()) {
  if (!isoInstant) return "";
  const seconds = Math.round((now - new Date(isoInstant).getTime()) / 1000);
  if (seconds < 45) return "agora";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 30) return `há ${days} dia${days > 1 ? "s" : ""}`;
  return fmtDate(todayISO(new Date(isoInstant)));
}

const numberFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const intFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

export function fmtNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return digits === 0 ? intFmt.format(value) : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

export function fmtPct(value) {
  return value === null || value === undefined ? "—" : `${numberFmt.format(value)}%`;
}

export function fmtDays(value) {
  if (value === null || value === undefined) return "—";
  return `${numberFmt.format(value)} ${value === 1 ? "dia" : "dias"}`;
}

export function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${numberFmt.format(bytes / 1024)} KB`;
  return `${numberFmt.format(bytes / 1024 / 1024)} MB`;
}

export function plural(n, one, many) {
  return `${intFmt.format(n)} ${n === 1 ? one : many}`;
}

export function greeting(now = new Date()) {
  const hour = now.getHours();
  if (hour < 12) return "Bom dia";
  if (hour < 18) return "Boa tarde";
  return "Boa noite";
}

export function hostOf(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "mailto:" ? url.slice(7) : parsed.host + (parsed.pathname !== "/" ? parsed.pathname : "");
  } catch {
    return url;
  }
}
