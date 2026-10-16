// Daily: o que aparece em cada dia. Itens não concluídos de dias anteriores aparecem no topo de Hoje até serem
// concluídos ou excluídos (continuam com o dia em que foram planejados); os concluídos hoje entram em
// "Concluídas" de hoje.
import { diffDays, fmtDateShort, localDay, weekdayShort } from "./format.js";

const byCreated = (a, b) => (a.created_at || "").localeCompare(b.created_at || "") || a.id.localeCompare(b.id);

/** Listas de um dia: pendências de dias anteriores (só em Hoje), pendentes do dia e concluídas. */
export function dailyLists(items, day, today) {
  const isToday = day === today;
  const carried = isToday ? items.filter((item) => !item.done && item.day < today) : [];
  const pending = items.filter((item) => !item.done && item.day === day);
  const done = items.filter((item) => item.done && (item.day === day || (isToday && item.day < today && localDay(item.done_at) === today)));
  return {
    carried: carried.sort((a, b) => a.day.localeCompare(b.day) || byCreated(a, b)),
    pending: pending.sort((a, b) => byCreated(b, a)), // a mais recente no topo, como no To Do
    done: done.sort((a, b) => (b.done_at || "").localeCompare(a.done_at || "")),
  };
}

/** De quando é uma pendência que aparece hoje: "de ontem", "de seg, 12/10". */
export function originLabel(day, today) {
  return diffDays(day, today) === 1 ? "de ontem" : `de ${weekdayShort(day).toLowerCase()}, ${fmtDateShort(day)}`;
}

/** "Hoje", "Ontem", "Amanhã" ou null. */
export function relativeDay(day, today) {
  return { 0: "Hoje", [-1]: "Ontem", 1: "Amanhã" }[diffDays(today, day)] || null;
}
