// Aba Listas: listas com nome (ex.: lista de compras), cada uma em um modelo — Tarefas (como a Daily: marcar e
// anotar) ou Ranking (itens em posição reordenável, com quantidade e unidade). As listas são privadas: só a
// própria conta as vê, por isso não aparecem no perfil da Equipe.
import { html, cx } from "../lib/html.js";
import { useEffect, useRef, useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Badge, Button, Checkbox, EmptyState, IconButton, Skeleton } from "../ui/core.js";
import { AutoText, Field, useFieldId } from "../ui/forms.js";
import { Menu, Modal } from "../ui/overlay.js";
import { prefs } from "../lib/cache.js";
import { fmtDateTime } from "../lib/format.js";
import { TITLE_MAX } from "../lib/rules.js";
import { useReorder } from "../lib/reorder.js";
import { LIST_KINDS, LIST_NAME_MAX, UNITS, UNIT_MAX, byPosition, fmtQuantity, listGroups, parseQuantity, stepQuantity } from "../lib/lists.js";
import {
  closeModal,
  createList,
  createListItem,
  deleteList,
  deleteListItem,
  navigate,
  openModal,
  reorderListItems,
  updateList,
  updateListItem,
} from "../actions.js";

const UNITS_ID = "list-units";
const quantityText = (quantity) => (quantity === null || quantity === undefined ? "" : String(quantity).replace(".", ","));
const quantityError = (text) => (Number.isNaN(parseQuantity(text)) ? "Informe um número maior que zero." : null);

export function ListsView() {
  const meId = useStore((s) => s.meId);
  const board = useStore((s) => s.boards[s.meId]);
  const wanted = useStore((s) => s.route.params?.lista);
  const lists = board?.lists || [];
  const current = lists.find((l) => l.id === wanted) || lists.find((l) => l.id === prefs.get("lists.last")) || lists[0] || null;

  useEffect(() => {
    if (current) prefs.set("lists.last", current.id);
  }, [current?.id]);

  const newList = () => openModal("listForm", { accountId: meId });

  return html`<div class="stack" style="gap:18px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Listas</h1>
        <p class="page-subtitle">Listas com nome para o que você quiser: compras, ideias, prioridades. Só você vê as suas listas.</p>
      </div>
      ${lists.length ? html`<${Button} variant="primary" icon="plus" onClick=${newList}>Nova lista<//>` : null}
    </header>
    ${!board
      ? html`<${Skeleton} count=${3} height=${64} />`
      : !current
        ? html`<${EmptyState}
            icon="clipboardList"
            title="Nenhuma lista ainda"
            text="Crie uma lista no modelo Tarefas (marcar e anotar, como na Daily) ou Ranking (ordem de prioridade, com quantidades)."
            action=${html`<${Button} variant="primary" icon="plus" onClick=${newList}>Criar lista<//>`}
          />`
        : html`<div class="lists-layout">
            <${ListsNav} lists=${lists} items=${board.list_items || []} currentId=${current.id} onNew=${newList} />
            <${ListPanel} key=${current.id} list=${current} items=${board.list_items || []} />
          </div>`}
  </div>`;
}

function ListsNav({ lists, items, currentId, onNew }) {
  return html`<nav class="lists-nav" aria-label="Suas listas">
    <ul class="lists-nav-items">
      ${lists.map((list) => {
        const pending = items.filter((i) => i.list_id === list.id && !i.done).length;
        return html`<li key=${list.id}>
          <a
            class="lists-nav-item"
            href=${`#/listas?lista=${encodeURIComponent(list.id)}`}
            aria-current=${list.id === currentId ? "page" : undefined}
            title=${`${list.name} · ${LIST_KINDS[list.kind]?.label}`}
          >
            <${Icon} name=${LIST_KINDS[list.kind]?.icon || "list"} size=${18} />
            <span class="grow truncate">${list.name}</span>
            ${pending ? html`<span class="counter" aria-label=${`${pending} pendentes`}>${pending}</span>` : null}
          </a>
        </li>`;
      })}
    </ul>
    <button type="button" class="lists-nav-item lists-nav-new" onClick=${onNew}><${Icon} name="plus" size=${18} />Nova lista</button>
  </nav>`;
}

function ListPanel({ list, items }) {
  const accountId = list.account_id;
  const ranking = list.kind === "ranking";
  const [openId, setOpenId] = useState(null);
  const [showDone, setShowDone] = useState(() => prefs.get("lists.done", true));
  const { pending, done } = listGroups(items, list);
  const reorder = (order) => {
    const rest = items.filter((i) => i.list_id === list.id && !order.includes(i.id)).sort(byPosition);
    reorderListItems(accountId, list.id, [...order, ...rest.map((i) => i.id)]);
  };
  const { listProps, handleProps, rowState } = useReorder(
    pending.map((i) => i.id),
    reorder,
    !ranking,
  );
  const toggleDone = () => {
    prefs.set("lists.done", !showDone);
    setShowDone(!showDone);
  };
  const row = (item, index = null) => html`<${ListRow}
    key=${item.id}
    item=${item}
    ranking=${ranking}
    rank=${index === null ? null : index + 1}
    draggable=${ranking && index !== null && pending.length > 1}
    handleProps=${handleProps}
    rowState=${rowState}
    open=${openId === item.id}
    onToggle=${() => setOpenId(openId === item.id ? null : item.id)}
  />`;
  const total = pending.length + done.length;

  return html`<section class="stack lists-panel" style="gap:12px" aria-label=${`Lista ${list.name}`}>
    <div class="toolbar toolbar-row lists-toolbar" role="toolbar" aria-label="Lista">
      <h2 class="daily-date truncate" title=${list.name}>${list.name}</h2>
      <${Badge} icon=${LIST_KINDS[list.kind].icon} title=${LIST_KINDS[list.kind].text}>${LIST_KINDS[list.kind].label}<//>
      <div class="grow"></div>
      ${total ? html`<span class="small muted">${done.length} de ${total} concluídos</span>` : null}
      <${Menu}
        trigger=${(props) => html`<${IconButton}
          icon="more"
          label="Opções da lista"
          aria-haspopup="menu"
          aria-expanded=${props["aria-expanded"]}
          onClick=${props.toggle}
        />`}
        items=${[
          { icon: "edit", label: "Renomear ou trocar modelo", onClick: () => openModal("listForm", { accountId, list }) },
          "-",
          ...Object.entries(LIST_KINDS).map(([kind, meta]) => ({
            icon: meta.icon,
            label: `Modelo ${meta.label}`,
            checked: list.kind === kind,
            onClick: () => list.kind !== kind && updateList(accountId, list.id, { kind }),
          })),
          "-",
          {
            icon: "trash",
            label: "Excluir lista",
            danger: true,
            onClick: async () => {
              if (await deleteList(accountId, list.id)) navigate("listas");
            },
          },
        ]}
      />
    </div>

    <div class=${cx("block daily lists-block", ranking && "is-ranking")}>
      <${AddItem} list=${list} />
      ${pending.length
        ? html`<div class="daily-group">
            <ul class="daily-items" ...${ranking ? listProps : {}}>${pending.map((item, index) => row(item, ranking ? index : null))}</ul>
          </div>`
        : html`<div class="daily-group">
            <${EmptyState}
              compact
              icon=${LIST_KINDS[list.kind].icon}
              title=${done.length ? "Tudo concluído" : "Lista vazia"}
              text=${ranking ? "Adicione itens com quantidade e unidade; arraste para definir a ordem de prioridade." : "Adicione o primeiro item no campo acima."}
            />
          </div>`}
      ${done.length
        ? html`<div class="daily-group">
            <button type="button" class="daily-group-title daily-done-toggle" aria-expanded=${showDone ? "true" : "false"} onClick=${toggleDone}>
              <${Icon} name=${showDone ? "chevronDown" : "chevronRight"} />Concluídos <span class="counter">${done.length}</span>
            </button>
            ${showDone ? html`<ul class="daily-items">${done.map((item) => row(item))}</ul>` : null}
          </div>`
        : null}
    </div>
    ${ranking ? html`<datalist id=${UNITS_ID}>${UNITS.map((u) => html`<option key=${u} value=${u} />`)}</datalist>` : null}
  </section>`;
}

/** Campo do topo: título (e, no ranking, quantidade e unidade). Enter adiciona. */
function AddItem({ list }) {
  const ranking = list.kind === "ranking";
  const [title, setTitle] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("");
  const input = useRef(null);
  const parsed = parseQuantity(quantity);
  const invalid = ranking && Number.isNaN(parsed);
  const add = () => {
    const text = title.trim();
    if (!text || invalid) return;
    createListItem(list.account_id, list.id, ranking && parsed !== null ? { title: text, quantity: parsed, unit: unit.trim() } : { title: text });
    setTitle("");
    setQuantity("");
    setUnit("");
    input.current?.focus();
  };
  const clear = (e) => e.key === "Escape" && (setTitle(""), setQuantity(""), setUnit(""));
  return html`<form class="daily-add lists-add" onSubmit=${(e) => (e.preventDefault(), add())}>
    <${Icon} name="plus" />
    <input
      ref=${input}
      class="input daily-add-input"
      maxLength=${TITLE_MAX}
      value=${title}
      autocomplete="off"
      placeholder="Adicionar um item"
      aria-label=${`Novo item em ${list.name}`}
      onInput=${(e) => setTitle(e.currentTarget.value)}
      onKeyDown=${clear}
    />
    ${ranking
      ? html`<div class="lists-add-qty">
          <input
            class="input"
            inputmode="decimal"
            value=${quantity}
            autocomplete="off"
            placeholder="Qtd."
            aria-label="Quantidade (opcional)"
            aria-invalid=${invalid ? "true" : undefined}
            title=${invalid ? "Informe um número maior que zero." : "Quantidade (opcional)"}
            onInput=${(e) => setQuantity(e.currentTarget.value)}
            onKeyDown=${clear}
          />
          <input
            class="input"
            list=${UNITS_ID}
            maxLength=${UNIT_MAX}
            value=${unit}
            autocomplete="off"
            placeholder="Unid."
            aria-label="Unidade (opcional)"
            title="Unidade (opcional): un, kg, g, L…"
            onInput=${(e) => setUnit(e.currentTarget.value)}
            onKeyDown=${clear}
          />
        </div>`
      : null}
    <${Button} type="submit" size="sm" variant="primary" disabled=${!title.trim() || invalid}>Adicionar<//>
  </form>`;
}

/** Quantidade no ranking: − 2 kg + (passos inteiros, mínimo 1). */
function QuantityStepper({ item }) {
  const set = (quantity) => updateListItem(item.account_id, item.id, { quantity });
  const label = fmtQuantity(item.quantity, item.unit);
  return html`<div class="qty-stepper" role="group" aria-label=${`Quantidade de ${item.title}`}>
    <${IconButton}
      icon="minus"
      size="sm"
      label=${`Diminuir quantidade: ${item.title}`}
      disabled=${item.quantity === null || item.quantity <= 1}
      onClick=${() => set(stepQuantity(item.quantity, -1))}
    />
    <span class=${cx("qty-value", !label && "is-empty")} aria-live="polite">${label || "—"}</span>
    <${IconButton} icon="plus" size="sm" label=${`Aumentar quantidade: ${item.title}`} onClick=${() => set(stepQuantity(item.quantity, 1))} />
  </div>`;
}

const datesText = (item) => `Adicionado em ${fmtDateTime(item.created_at)}${item.done && item.done_at ? ` · concluído em ${fmtDateTime(item.done_at)}` : ""}`;

function ListRow({ item, ranking, rank, draggable, handleProps, rowState, open, onToggle }) {
  const ids = { title: useFieldId("list-title"), note: useFieldId("list-note"), qty: useFieldId("list-qty"), unit: useFieldId("list-unit") };
  const update = (changes) => updateListItem(item.account_id, item.id, changes);
  const preview = item.note.split("\n").find((line) => line.trim()) || "";
  const quantity = fmtQuantity(item.quantity, item.unit);
  const showQuantity = ranking && quantity && (item.done || rank === null);
  return html`<li data-step=${rank === null ? undefined : item.id} class=${cx("daily-item list-item-row", item.done && "is-done", open && "is-open", rank !== null && rowState(item.id))}>
    <div class="daily-row">
      ${draggable
        ? html`<button
            type="button"
            class="drag-handle"
            aria-label=${`Reordenar: ${item.title}. Use as setas para cima e para baixo.`}
            title="Arraste para reordenar (ou use as setas)"
            ...${handleProps(item.id)}
          >
            <${Icon} name="grip" size=${16} />
          </button>`
        : null}
      ${rank !== null ? html`<span class="list-rank" aria-label=${`${rank}º lugar`}>${rank}º</span>` : null}
      <${Checkbox}
        round
        checked=${item.done}
        label=${item.done ? `Reabrir: ${item.title}` : `Concluir: ${item.title}`}
        onChange=${(value) => update({ done: value })}
      />
      <button type="button" class="daily-main" aria-expanded=${open ? "true" : "false"} onClick=${onToggle}>
        <span class="daily-title">${item.title}</span>
        ${preview || showQuantity
          ? html`<span class="daily-meta">
              ${showQuantity ? html`<span class="badge"><${Icon} name="layers" />${quantity}</span>` : null}
              ${preview ? html`<span class="daily-note-preview"><${Icon} name="note" size=${13} /><span class="truncate">${preview}</span></span>` : null}
            </span>`
          : null}
      </button>
      ${ranking && !item.done && rank !== null ? html`<${QuantityStepper} item=${item} />` : null}
      <${IconButton} icon="trash" size="sm" danger class="daily-delete" label=${`Excluir: ${item.title}`} onClick=${() => deleteListItem(item.account_id, item.id)} />
    </div>
    ${open
      ? html`<div class="daily-details">
          <${AutoText}
            id=${ids.title}
            label="Título"
            value=${item.title}
            maxLength=${TITLE_MAX}
            validate=${(text) => (text.trim() ? null : "O título é obrigatório.")}
            onSave=${(title) => update({ title: title.trim() })}
          />
          ${ranking
            ? html`<div class="lists-qty-fields">
                <${AutoText}
                  id=${ids.qty}
                  label="Quantidade"
                  value=${quantityText(item.quantity)}
                  placeholder="Ex.: 2 ou 1,5"
                  validate=${quantityError}
                  onSave=${(text) => update({ quantity: parseQuantity(text) })}
                />
                <${AutoText}
                  id=${ids.unit}
                  label="Unidade"
                  value=${item.unit}
                  list=${UNITS_ID}
                  maxLength=${UNIT_MAX}
                  placeholder="un, kg, L…"
                  onSave=${(unit) => update({ unit: unit.trim() })}
                />
              </div>`
            : null}
          <${AutoText}
            id=${ids.note}
            label="Anotação"
            multiline
            rows=${3}
            placeholder="Detalhes, links, lembretes…"
            value=${item.note}
            draftKey=${`list-note:${item.id}`}
            onSave=${(note) => update({ note })}
          />
          <p class="xsmall faint">${datesText(item)}</p>
        </div>`
      : null}
  </li>`;
}

/** Nova lista ou edição (nome e modelo). */
export function ListFormModal({ accountId, list = null }) {
  const [name, setName] = useState(list?.name || "");
  const [kind, setKind] = useState(list?.kind || "tarefas");
  const [error, setError] = useState(null);
  const nameId = useFieldId("list-name");

  const submit = () => {
    const clean = name.trim().replace(/\s+/g, " ");
    if (!clean) {
      setError("Informe o nome da lista.");
      return;
    }
    closeModal();
    if (list) {
      const changes = {};
      if (clean !== list.name) changes.name = clean;
      if (kind !== list.kind) changes.kind = kind;
      if (Object.keys(changes).length) updateList(accountId, list.id, changes);
      return;
    }
    navigate(`listas?lista=${encodeURIComponent(createList(accountId, { name: clean, kind }))}`);
  };

  return html`<${Modal}
    title=${list ? "Editar lista" : "Nova lista"}
    icon="clipboardList"
    onClose=${closeModal}
    footer=${html`<${Button} variant="ghost" onClick=${closeModal}>Cancelar<//><${Button} variant="primary" icon="check" onClick=${submit}>${list ? "Salvar" : "Criar lista"}<//>`}
  >
    <form class="stack" style="gap:14px" onSubmit=${(e) => (e.preventDefault(), submit())}>
      <${Field} label="Nome" required id=${nameId} error=${error} hint="Ex.: Lista de compras">
        <input id=${nameId} class="input" data-autofocus maxLength=${LIST_NAME_MAX} value=${name} onInput=${(e) => (setName(e.currentTarget.value), setError(null))} />
      <//>
      <fieldset class="list-kinds">
        <legend class="field-label">Modelo</legend>
        ${Object.entries(LIST_KINDS).map(
          ([key, meta]) => html`<label key=${key} class=${cx("list-kind", kind === key && "is-selected")}>
            <input type="radio" name="list-kind" value=${key} checked=${kind === key} onChange=${() => setKind(key)} />
            <span class="list-kind-icon"><${Icon} name=${meta.icon} size=${20} /></span>
            <span class="stack" style="gap:2px">
              <strong>${meta.label}</strong>
              <span class="small muted">${meta.text}</span>
            </span>
          </label>`,
        )}
      </fieldset>
      ${list && kind !== list.kind ? html`<p class="small muted">Os itens continuam na lista; ${kind === "ranking" ? "eles entram no ranking na ordem em que foram adicionados; arraste para ajustar." : "posição e quantidade ficam guardadas, mas não aparecem."}</p>` : null}
      <button type="submit" hidden>Salvar</button>
    </form>
  <//>`;
}
