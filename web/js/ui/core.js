// Componentes básicos do design system (RNF06, RNF12).
import { html, cx } from "../lib/html.js";
import { Icon } from "./icons.js";
import { DIFFICULTY_LABEL, PHASE_LABEL, PHASES } from "../lib/rules.js";

export function Button({ variant, size, block, icon, iconRight, loading, children, class: className, type = "button", ...rest }) {
  const iconSize = size === "sm" ? 16 : 18;
  return html`<button
    ...${rest}
    type=${type}
    class=${cx("btn", variant && `btn-${variant}`, size && `btn-${size}`, block && "btn-block", className)}
    disabled=${rest.disabled || loading}
    aria-busy=${loading ? "true" : undefined}
  >
    ${loading ? html`<${Icon} name="loader" size=${iconSize} class="spin" />` : icon ? html`<${Icon} name=${icon} size=${iconSize} />` : null}
    ${children}
    ${iconRight ? html`<${Icon} name=${iconRight} size=${iconSize} />` : null}
  </button>`;
}

export function IconButton({ icon, label, size, danger, class: className, iconSize, ...rest }) {
  return html`<button
    ...${rest}
    type="button"
    class=${cx("icon-btn", size, danger && "danger", className)}
    aria-label=${label}
    title=${label}
  >
    <${Icon} name=${icon} size=${iconSize || (size === "sm" ? 17 : 20)} />
  </button>`;
}

export function DifficultyBadge({ value }) {
  return html`<span class=${cx("badge", `diff-${value}`)} title=${`Dificuldade: ${DIFFICULTY_LABEL[value]}`}>
    <span class="dot" aria-hidden="true"></span>${DIFFICULTY_LABEL[value]}
  </span>`;
}

export function PhaseBadge({ value, short = false }) {
  const phase = PHASES.find((p) => p.key === value);
  return html`<span class=${cx("badge", `phase-${value}`)} title=${`Fase: ${PHASE_LABEL[value]}`}>
    <span class="dot" aria-hidden="true"></span>${short ? phase?.short : phase?.label}
  </span>`;
}

export function StatusBadge({ kind, icon, children, title }) {
  return html`<span class=${cx("badge", `status-${kind}`)} title=${title}>
    ${icon ? html`<${Icon} name=${icon} />` : null}${children}
  </span>`;
}

export function Badge({ tone, icon, children, title, class: className }) {
  return html`<span class=${cx("badge", tone, className)} title=${title}>
    ${icon ? html`<${Icon} name=${icon} />` : null}${children}
  </span>`;
}

export function Avatar({ account, size, class: className }) {
  if (!account) return null;
  return html`<span
    class=${cx("avatar", size, className)}
    style=${`--avatar-color:${account.color}`}
    aria-hidden="true"
    >${account.initials}</span
  >`;
}

export function Progress({ value, done, label }) {
  return html`<div
    class=${cx("progress", done && "done")}
    role="progressbar"
    aria-valuemin="0"
    aria-valuemax="100"
    aria-valuenow=${value}
    aria-label=${label || "Progresso"}
  >
    <span style=${`width:${Math.max(0, Math.min(100, value))}%`}></span>
  </div>`;
}

/** Checkbox acessível com animação na marcação (RF09, RNF07). */
export function Checkbox({ checked, onChange, label, disabled, round, size, class: className }) {
  return html`<button
    type="button"
    role="checkbox"
    class=${cx("check", round && "round", size, className)}
    aria-checked=${checked ? "true" : "false"}
    aria-label=${label}
    title=${label}
    disabled=${disabled}
    onClick=${(event) => {
      event.stopPropagation();
      if (!disabled) onChange(!checked);
    }}
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  </button>`;
}

export function EmptyState({ icon = "sparkles", title, text, action, compact }) {
  return html`<div class=${cx("empty", compact && "compact")}>
    <div class="empty-icon"><${Icon} name=${icon} size=${22} /></div>
    <div class="empty-title">${title}</div>
    ${text ? html`<div class="empty-text">${text}</div>` : null}
    ${action || null}
  </div>`;
}

export function Skeleton({ count = 3, height }) {
  return html`<div class="task-list" aria-busy="true" aria-label="Carregando">
    ${Array.from({ length: count }, (_, i) => html`<div key=${i} class="skeleton skeleton-card" style=${height ? `height:${height}px` : ""}></div>`)}
  </div>`;
}

/** Controle segmentado (grupo de botões de opção). */
export function Segmented({ options, value, onChange, label, disabled, size }) {
  return html`<div class="segmented" role="radiogroup" aria-label=${label}>
    ${options.map(
      (option) => html`<button
        key=${option.value}
        type="button"
        role="radio"
        aria-checked=${option.value === value ? "true" : "false"}
        disabled=${disabled}
        class=${size}
        onClick=${() => !disabled && option.value !== value && onChange(option.value)}
        onKeyDown=${(event) => {
          if (disabled) return;
          const index = options.findIndex((o) => o.value === value);
          if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            event.preventDefault();
            onChange(options[(index + 1) % options.length].value);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
            event.preventDefault();
            onChange(options[(index - 1 + options.length) % options.length].value);
          }
        }}
      >
        ${option.dot ? html`<span class="dot" aria-hidden="true" style=${`background:${option.dot}`}></span>` : null}
        ${option.label}
      </button>`,
    )}
  </div>`;
}

export function Chip({ pressed, onClick, children, dot }) {
  return html`<button type="button" class="chip" aria-pressed=${pressed ? "true" : "false"} onClick=${onClick}>
    ${dot ? html`<span class="dot" aria-hidden="true" style=${`background:${dot}`}></span>` : null}${children}
  </button>`;
}

/** tone: "critical" | "warning" | "good" | "star" pinta o ícone com a cor do significado. */
export function SectionTitle({ icon, children, count, extra, tone }) {
  return html`<div class="section-head">
    <h2 class=${cx("section-title", tone && `tone-${tone}`)}>
      ${icon ? html`<${Icon} name=${icon} />` : null}${children}
      ${count !== undefined ? html`<span class="counter" aria-label=${`${count} itens`}>${count}</span>` : null}
    </h2>
    <div class="grow"></div>
    ${extra || null}
  </div>`;
}

export function Banner({ tone, icon = "info", children, action }) {
  return html`<div class=${cx("banner", tone)} role=${tone === "critical" || tone === "warning" ? "alert" : "status"}>
    <${Icon} name=${icon} />
    <div class="banner-text">${children}</div>
    ${action || null}
  </div>`;
}
