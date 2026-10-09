// Reordenação de listas por arrastar (ponteiro) ou setas do teclado, compartilhada pelo editor de etapas e pelo cartão.
import { useRef, useState } from "preact/hooks";

/** ids: ordem atual · onReorder(novaOrdem) → { listRef, listProps, handleProps(id), stepClass(id), drag } */
export function useReorder(ids, onReorder, readOnly = false) {
  const [drag, setDrag] = useState(null); // { id, over, position }
  const listRef = useRef(null);

  const move = (id, delta) => {
    const next = [...ids];
    const index = next.indexOf(id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= next.length) return;
    next.splice(index, 1);
    next.splice(target, 0, id);
    onReorder(next);
    requestAnimationFrame(() => listRef.current?.querySelector(`[data-step="${id}"] .drag-handle`)?.focus());
  };

  const onPointerMove = (event) => {
    if (!drag || !listRef.current) return;
    for (const row of listRef.current.querySelectorAll("[data-step]")) {
      const rect = row.getBoundingClientRect();
      if (event.clientY >= rect.top && event.clientY <= rect.bottom) {
        const position = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
        if (row.dataset.step !== drag.over || position !== drag.position) setDrag({ ...drag, over: row.dataset.step, position });
        break;
      }
    }
  };

  const onPointerUp = () => {
    if (!drag) return;
    const next = ids.filter((id) => id !== drag.id);
    if (drag.over !== drag.id) {
      let index = next.indexOf(drag.over);
      if (drag.position === "after") index += 1;
      next.splice(index, 0, drag.id);
      onReorder(next);
    }
    setDrag(null);
  };

  const listProps = { ref: listRef, onPointerMove, onPointerUp, onPointerCancel: () => setDrag(null) };

  const handleProps = (id) => ({
    onPointerDown: (event) => {
      if (readOnly || event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setDrag({ id, over: id, position: "before" });
    },
    onKeyDown: (event) => {
      if (event.key === "ArrowUp") {
        event.preventDefault();
        move(id, -1);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        move(id, 1);
      }
    },
  });

  const rowState = (id) => ({
    dragging: drag?.id === id,
    "drop-before": !!drag && drag.over === id && drag.id !== id && drag.position === "before",
    "drop-after": !!drag && drag.over === id && drag.id !== id && drag.position === "after",
  });

  return { listProps, handleProps, rowState };
}
