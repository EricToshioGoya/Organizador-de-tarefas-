// Preact + htm sem etapa de build: `html` cria elementos a partir de template strings.
import { h, render, Fragment, createContext } from "preact";
import htm from "htm";

export const html = htm.bind(h);
export { h, render, Fragment, createContext };

/** Junta classes CSS: aceita strings, arrays e objetos { classe: condição }. */
export function cx(...args) {
  const out = [];
  for (const arg of args.flat()) {
    if (!arg) continue;
    if (typeof arg === "string") out.push(arg);
    else if (typeof arg === "object") {
      for (const [name, on] of Object.entries(arg)) if (on) out.push(name);
    }
  }
  return out.join(" ");
}
