// Rascunhos automáticos de textos em edição (RF70): recuperados ao reabrir a tela.
const PREFIX = "odt.draft.";
const MAX_AGE = 30 * 86_400_000;

export function saveDraft(key, value) {
  try {
    if (value === null || value === undefined || (typeof value === "string" && !value.trim())) {
      localStorage.removeItem(PREFIX + key);
      return;
    }
    localStorage.setItem(PREFIX + key, JSON.stringify({ value, at: Date.now() }));
  } catch {
    /* armazenamento indisponível */
  }
}

export function loadDraft(key) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const { value, at } = JSON.parse(raw);
    if (Date.now() - at > MAX_AGE) {
      localStorage.removeItem(PREFIX + key);
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

export function clearDraft(key) {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    /* ignorado */
  }
}
