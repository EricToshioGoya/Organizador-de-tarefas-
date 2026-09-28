// Fila local de alterações (RF71, RN35, RNF25).
// Toda mutação é gravada no dispositivo ANTES de ir ao servidor; sobrevive a fechamento do navegador
// e a queda de conexão, e é reenviada com a mesma chave de idempotência até a confirmação.
import { request, ApiError, isNetworkError } from "./api.js";
import { uid } from "./ids.js";

const STORAGE_KEY = "odt.queue.v1";
const MAX_DELAY = 30_000;

let queue = load();
let processing = false;
let retryTimer = null;
let attempt = 0;
let lastStatus = queue.length ? "saving" : "saved";
let lastError = null;

const waiters = new Map(); // id da mutação -> [{ resolve, reject }]
const listeners = new Set();
const errorListeners = new Set();
const drainListeners = new Set();
const flushers = new Set();

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const items = raw ? JSON.parse(raw) : [];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue, (key, value) => (key === "inflight" ? undefined : value)));
  } catch {
    /* sem armazenamento local: a fila continua em memória */
  }
}

function snapshot() {
  return { status: lastStatus, pending: queue.length, error: lastError };
}

function emit() {
  const state = snapshot();
  listeners.forEach((fn) => fn(state));
}

function setStatus(status, error = null) {
  lastStatus = status;
  lastError = error;
  emit();
}

function settle(id, kind, value) {
  const list = waiters.get(id);
  if (!list) return;
  waiters.delete(id);
  list.forEach((w) => w[kind](value));
}

function scheduleRetry() {
  clearTimeout(retryTimer);
  attempt += 1;
  const delay = Math.min(MAX_DELAY, 1000 * 2 ** Math.min(attempt, 5)) + Math.random() * 400;
  retryTimer = setTimeout(process, delay);
}

async function process() {
  if (processing) return;
  processing = true;
  clearTimeout(retryTimer);
  try {
    while (queue.length) {
      const mutation = queue[0];
      mutation.inflight = true;
      setStatus("saving");
      let data;
      try {
        data = await request(mutation.method, mutation.path, {
          body: mutation.body,
          account: mutation.account,
          time: mutation.time,
          key: mutation.id,
        });
      } catch (error) {
        mutation.inflight = false;
        const transient = isNetworkError(error) || error.status >= 500 || error.status === 408 || error.status === 429;
        if (transient) {
          setStatus(isNetworkError(error) ? "offline" : "error", error);
          scheduleRetry();
          return;
        }
        // Rejeição definitiva (validação, somente leitura, registro excluído): descarta e avisa.
        queue.shift();
        persist();
        settle(mutation.id, "reject", error);
        errorListeners.forEach((fn) => fn(error, mutation));
        continue;
      }
      queue.shift();
      persist();
      attempt = 0;
      settle(mutation.id, "resolve", data);
    }
    setStatus("saved");
    drainListeners.forEach((fn) => fn());
  } finally {
    processing = false;
  }
}

/**
 * Enfileira uma mutação e devolve uma Promise com a resposta do servidor.
 * PATCHs seguidos no mesmo recurso são combinados enquanto aguardam (ex.: digitação offline).
 */
export function enqueue({ method, path, body, account, meta = {} }) {
  return new Promise((resolve, reject) => {
    const last = queue[queue.length - 1];
    if (method === "PATCH" && last && !last.inflight && last.method === "PATCH" && last.path === path && last.account === account) {
      last.body = { ...last.body, ...body };
      last.time = new Date().toISOString();
      persist();
      waiters.get(last.id)?.push({ resolve, reject }) ?? waiters.set(last.id, [{ resolve, reject }]);
      emit();
      process();
      return;
    }
    const mutation = { id: uid(), method, path, body, account, time: new Date().toISOString(), meta };
    queue.push(mutation);
    persist();
    waiters.set(mutation.id, [{ resolve, reject }]);
    if (lastStatus === "saved") setStatus("saving");
    else emit();
    process();
  });
}

export function pendingFor(predicate) {
  return queue.some((m) => predicate(m.meta || {}, m));
}

export function hasPending() {
  return queue.length > 0;
}

export function onSyncChange(fn) {
  listeners.add(fn);
  fn(snapshot());
  return () => listeners.delete(fn);
}

export function onMutationError(fn) {
  errorListeners.add(fn);
  return () => errorListeners.delete(fn);
}

export function onDrain(fn) {
  drainListeners.add(fn);
  return () => drainListeners.delete(fn);
}

/** Campos com salvamento adiado (debounce) registram aqui como gravar imediatamente. */
export function registerFlusher(fn) {
  flushers.add(fn);
  return () => flushers.delete(fn);
}

export function flushAll() {
  flushers.forEach((fn) => {
    try {
      fn();
    } catch {
      /* segue para os demais */
    }
  });
}

export function retryNow() {
  attempt = 0;
  process();
}

export function startQueue() {
  window.addEventListener("online", retryNow);
  window.addEventListener("offline", () => setStatus(queue.length ? "offline" : lastStatus === "saved" ? "offline" : lastStatus));
  // Ao sair da página, grava na fila local o que ainda estava aguardando o debounce (RNF25).
  window.addEventListener("pagehide", flushAll);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushAll();
    else retryNow();
  });
  if (!navigator.onLine) setStatus("offline");
  process();
}

export { ApiError };
