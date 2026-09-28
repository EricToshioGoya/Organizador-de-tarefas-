// Sobreposições acessíveis: modal, gaveta lateral, menu e toasts (RNF10, RNF12).
import { html, cx, render } from "../lib/html.js";
import { useEffect, useRef, useState, useLayoutEffect, useMemo } from "preact/hooks";
import { Icon } from "./icons.js";
import { IconButton } from "./core.js";
import { useStore } from "../lib/store.js";
import { dismissToast } from "../actions.js";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Renderiza os filhos direto no <body>. Necessário porque superfícies com backdrop-filter viram o
 * bloco de contenção de elementos `position: fixed`, o que prenderia modais e menus dentro delas.
 */
export function Portal({ children }) {
  const host = useMemo(() => {
    const node = document.createElement("div");
    node.className = "portal";
    document.body.appendChild(node);
    return node;
  }, []);
  useLayoutEffect(() => {
    render(children, host);
  });
  useEffect(
    () => () => {
      render(null, host);
      host.remove();
    },
    [],
  );
  return null;
}

/** Prende o foco dentro do contêiner, fecha com Esc e devolve o foco ao sair. */
export function useFocusTrap(ref, { onEscape, autoFocus = true } = {}) {
  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const previous = document.activeElement;
    if (autoFocus) {
      const target = node.querySelector("[data-autofocus]") || node.querySelector(FOCUSABLE) || node;
      requestAnimationFrame(() => target.focus({ preventScroll: true }));
    }
    const onKey = (event) => {
      if (event.key === "Escape" && onEscape) {
        event.stopPropagation();
        onEscape();
        return;
      }
      if (event.key !== "Tab") return;
      event.stopPropagation(); // a armadilha mais interna decide
      const items = [...node.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    node.addEventListener("keydown", onKey);
    return () => {
      node.removeEventListener("keydown", onKey);
      if (previous && previous.focus && document.contains(previous)) previous.focus({ preventScroll: true });
    };
  }, []);
}

function useBodyScrollLock() {
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);
}

let modalCounter = 0;

export function Modal(props) {
  return html`<${Portal}><${ModalInner} ...${props} /><//>`;
}

/** soft: corpo em fundo cinza para conteúdo organizado em blocos brancos (.block). */
function ModalInner({ title, onClose, children, footer, size, labelledBy, icon, soft }) {
  const ref = useRef(null);
  useFocusTrap(ref, { onEscape: onClose });
  useBodyScrollLock();
  const fallbackId = useMemo(() => `modal-title-${++modalCounter}`, []);
  const titleId = labelledBy || fallbackId;
  return html`<div class="scrim" onMouseDown=${(event) => event.target === event.currentTarget && onClose?.()}>
    <div ref=${ref} class=${cx("modal", size, soft && "soft")} role="dialog" aria-modal="true" aria-labelledby=${titleId} tabindex="-1">
      <div class="modal-head">
        ${icon ? html`<span class="modal-icon" aria-hidden="true"><${Icon} name=${icon} size=${19} /></span>` : null}
        <h2 id=${titleId} class="modal-title">${title}</h2>
        ${onClose ? html`<${IconButton} icon="x" label="Fechar" onClick=${onClose} />` : null}
      </div>
      <div class="modal-body">${children}</div>
      ${footer ? html`<div class="modal-foot">${footer}</div>` : null}
    </div>
  </div>`;
}

export function Drawer(props) {
  return html`<${Portal}><${DrawerInner} ...${props} /><//>`;
}

function DrawerInner({ onClose, children, header, wide, label }) {
  const ref = useRef(null);
  useFocusTrap(ref, { onEscape: onClose });
  useBodyScrollLock();
  return html`<div class="scrim drawer-scrim" onMouseDown=${(event) => event.target === event.currentTarget && onClose()}>
    <aside ref=${ref} class=${cx("drawer", wide && "wide")} role="dialog" aria-modal="true" aria-label=${label} tabindex="-1">
      <div class="drawer-head">
        ${header}
        <${IconButton} icon="x" label="Fechar" onClick=${onClose} />
      </div>
      <div class="drawer-body">${children}</div>
    </aside>
  </div>`;
}

/** Menu suspenso ancorado a um botão; navegação por setas, Esc fecha. */
export function Menu({ trigger, items, align = "right", header }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const menuRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useLayoutEffect(() => {
    if (!open || !wrapRef.current || !menuRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    const menu = menuRef.current.getBoundingClientRect();
    let left = align === "right" ? rect.right - menu.width : rect.left;
    left = Math.max(8, Math.min(left, window.innerWidth - menu.width - 8));
    let top = rect.bottom + 6;
    if (top + menu.height > window.innerHeight - 8) top = Math.max(8, rect.top - menu.height - 6);
    setPos({ top, left });
    menuRef.current.querySelector(".menu-item")?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (!wrapRef.current?.contains(event.target) && !menuRef.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        wrapRef.current?.querySelector("button")?.focus();
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const nodes = [...(menuRef.current?.querySelectorAll(".menu-item") || [])];
        const index = nodes.indexOf(document.activeElement);
        const next = event.key === "ArrowDown" ? (index + 1) % nodes.length : (index - 1 + nodes.length) % nodes.length;
        nodes[next]?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", () => setOpen(false), { once: true });
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return html`<div ref=${wrapRef} style="display:inline-flex">
    ${trigger({ open, toggle: () => setOpen((v) => !v), "aria-haspopup": "menu", "aria-expanded": open ? "true" : "false" })}
    ${open
      ? html`<${Portal}><div ref=${menuRef} class="menu" role="menu" style=${`position:fixed;top:${pos.top}px;left:${pos.left}px`}>
          ${header || null}
          ${items
            .filter(Boolean)
            .map((item, index) =>
              item === "-"
                ? html`<div key=${index} class="menu-sep" role="separator"></div>`
                : html`<button
                    key=${index}
                    type="button"
                    role=${item.checked === undefined ? "menuitem" : "menuitemradio"}
                    aria-checked=${item.checked === undefined ? undefined : String(item.checked)}
                    class=${cx("menu-item", item.danger && "danger")}
                    disabled=${item.disabled}
                    onClick=${() => {
                      setOpen(false);
                      item.onClick();
                    }}
                  >
                    ${item.icon ? html`<${Icon} name=${item.icon} />` : null}
                    ${item.dot ? html`<span class="dot" style=${`background:${item.dot}`} aria-hidden="true"></span>` : null}
                    <span class="grow">${item.label}</span>
                    ${item.hint ? html`<span class="xsmall faint">${item.hint}</span>` : null}
                    ${item.checked ? html`<${Icon} name="check" />` : null}
                  </button>`,
            )}
        </div><//>`
      : null}
  </div>`;
}

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const icons = { success: "checkCircle", error: "alert", info: "info" };
  return html`<div class="toasts" role="region" aria-label="Notificações" aria-live="polite">
    ${toasts.map(
      (toast) => html`<div key=${toast.id} class=${cx("toast", toast.kind)} role=${toast.kind === "error" ? "alert" : "status"}>
        <${Icon} name=${icons[toast.kind] || "info"} />
        <div class="toast-text">${toast.text}</div>
        ${toast.action
          ? html`<button class="btn btn-sm btn-ghost" onClick=${() => {
              toast.action.onClick();
              dismissToast(toast.id);
            }}>${toast.action.label}</button>`
          : null}
        <${IconButton} icon="x" size="sm" label="Dispensar" onClick=${() => dismissToast(toast.id)} />
      </div>`,
    )}
  </div>`;
}
