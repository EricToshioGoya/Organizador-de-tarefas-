// Listas: modelos, ordem dos itens e formatação de quantidades.
import { fmtNumber } from "./format.js";

export const LIST_KINDS = {
  tarefas: { label: "Tarefas", icon: "checkSquare", text: "Como a Daily: marque o que for concluindo. O item mais recente fica no topo." },
  ranking: { label: "Ranking", icon: "listOrdered", text: "Itens em ordem de prioridade (1º, 2º, 3º…), reordenáveis, com quantidade e unidade." },
};

/** Sugestões de unidade no modelo ranking (o campo aceita qualquer texto). */
export const UNITS = ["un", "kg", "g", "L", "ml", "cx", "pct", "dz"];
export const LIST_NAME_MAX = 60;
export const UNIT_MAX = 20;
export const QUANTITY_MAX = 1_000_000;

const byCreated = (a, b) => (a.created_at || "").localeCompare(b.created_at || "") || a.id.localeCompare(b.id);
export const byPosition = (a, b) => a.position - b.position || byCreated(a, b);

/** Itens de uma lista: pendentes (ranking pela posição; tarefas com a mais recente no topo) e concluídos. */
export function listGroups(items, list) {
  const own = items.filter((item) => item.list_id === list.id);
  const pending = own.filter((item) => !item.done);
  return {
    pending: list.kind === "ranking" ? pending.sort(byPosition) : pending.sort((a, b) => byCreated(b, a)),
    done: own.filter((item) => item.done).sort((a, b) => (b.done_at || "").localeCompare(a.done_at || "")),
  };
}

/** "2 kg", "1,5 L", "3" ou "" sem quantidade. */
export function fmtQuantity(quantity, unit) {
  if (quantity === null || quantity === undefined) return "";
  return `${fmtNumber(quantity, 3)}${unit ? ` ${unit}` : ""}`;
}

/** Texto digitado ("1,5", "2") → número válido ou null (vazio); NaN se inválido. */
export function parseQuantity(text) {
  const clean = String(text ?? "").trim().replace(",", ".");
  if (!clean) return null;
  const value = Number(clean);
  return Number.isFinite(value) && value > 0 && value <= QUANTITY_MAX ? Math.round(value * 1000) / 1000 : NaN;
}

/** Próxima quantidade nos botões − / +: passos inteiros, nunca abaixo de 1. */
export function stepQuantity(quantity, delta) {
  const base = quantity ?? 0;
  const next = delta > 0 ? Math.floor(base) + 1 : Math.ceil(base) - 1;
  return Math.min(QUANTITY_MAX, Math.max(1, next));
}
