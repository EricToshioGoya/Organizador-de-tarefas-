// Estado global simples com assinatura por seletor (sem dependências extras).
import { useEffect, useReducer, useRef } from "preact/hooks";

let state = {
  ready: false,
  meta: null,
  online: navigator.onLine,
  sync: { status: "saved", pending: 0, error: null },
  accounts: null,
  meId: null,
  boards: {},
  loadingBoards: {},
  route: { name: "hoje", params: {} },
  drawer: null,
  panel: null,
  modal: null,
  toasts: [],
  dashboards: {},
  team: {},
};

const listeners = new Set();

export function getState() {
  return state;
}

export function setState(update) {
  const patch = typeof update === "function" ? update(state) : update;
  if (!patch) return;
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener(state));
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Re-renderiza o componente só quando o valor selecionado muda (comparação por identidade). */
export function useStore(selector) {
  const [, force] = useReducer((n) => n + 1, 0);
  const selectorRef = useRef(selector);
  selectorRef.current = selector;
  const value = selector(state);
  const valueRef = useRef(value);
  valueRef.current = value;
  useEffect(() => {
    const listener = (next) => {
      const selected = selectorRef.current(next);
      if (!Object.is(selected, valueRef.current)) {
        valueRef.current = selected;
        force();
      }
    };
    listeners.add(listener);
    listener(state); // pega mudanças ocorridas entre a renderização e a assinatura
    return () => listeners.delete(listener);
  }, []);
  return value;
}

export const selectMe = (s) => (s.accounts || []).find((a) => a.id === s.meId) || null;
export const selectBoard = (id) => (s) => s.boards[id] || null;
