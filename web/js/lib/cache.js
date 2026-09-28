// Cache local em IndexedDB para consulta offline (RNF20). Falhas de armazenamento nunca quebram o app.
const DB_NAME = "organizador-cache";
const STORE = "kv";
let dbPromise = null;

function open() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      if (!("indexedDB" in globalThis)) {
        reject(new Error("IndexedDB indisponível"));
        return;
      }
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }).catch((error) => {
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}

function run(mode, fn) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const request = fn(tx.objectStore(STORE));
        tx.oncomplete = () => resolve(request?.result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      }),
  );
}

export async function cacheGet(key) {
  try {
    return await run("readonly", (store) => store.get(key));
  } catch {
    return undefined;
  }
}

export async function cacheSet(key, value) {
  try {
    await run("readwrite", (store) => store.put(value, key));
  } catch {
    /* sem cache: o app segue funcionando online */
  }
}

export async function cacheDelete(key) {
  try {
    await run("readwrite", (store) => store.delete(key));
  } catch {
    /* ignorado */
  }
}

/** Preferências simples do dispositivo (conta usada por último, filtros). */
export const prefs = {
  get(key, fallback = null) {
    try {
      const raw = localStorage.getItem(`odt.${key}`);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      if (value === null || value === undefined) localStorage.removeItem(`odt.${key}`);
      else localStorage.setItem(`odt.${key}`, JSON.stringify(value));
    } catch {
      /* armazenamento indisponível (janela privada, cota) */
    }
  },
};
