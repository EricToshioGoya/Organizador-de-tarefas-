// Componente de gráfico: inicializa o ECharts só quando entra na tela e acompanha o tamanho do cartão.
import { html } from "../lib/html.js";
import { useEffect, useRef, useState } from "preact/hooks";
import { loadECharts } from "../lib/charts.js";

export function EChart({ option, height = 260, onClick, label, minWidth }) {
  const ref = useRef(null);
  const wrapRef = useRef(null);
  const chart = useRef(null);
  const clickRef = useRef(onClick);
  const [visible, setVisible] = useState(false);
  const [scroll, setScroll] = useState(false);
  clickRef.current = onClick;

  // Rolagem horizontal só quando o gráfico de fato não cabe: o ECharts arredonda a largura para cima, e a
  // sobra de fração de pixel bastaria para exibir uma barra de rolagem vazia.
  useEffect(() => {
    const node = wrapRef.current;
    if (!minWidth || !node) {
      setScroll(false);
      return undefined;
    }
    const check = () => setScroll(node.clientWidth + 1 < minWidth);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(node);
    return () => observer.disconnect();
  }, [minWidth]);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    // Gráficos fora da tela iniciam logo depois, sem competir com os visíveis na primeira pintura.
    const fallback = setTimeout(() => setVisible(true), 1200);
    return () => {
      observer.disconnect();
      clearTimeout(fallback);
    };
  }, []);

  useEffect(() => {
    if (!visible) return undefined;
    let disposed = false;
    let resizeObserver = null;
    loadECharts().then((echarts) => {
      if (disposed || !ref.current) return;
      chart.current = echarts.init(ref.current, "odt", { renderer: "canvas", locale: "EN" });
      chart.current.setOption({ ...option, aria: { enabled: true, label: { description: label } } });
      chart.current.on("click", (params) => clickRef.current?.(params));
      resizeObserver = new ResizeObserver(() => chart.current?.resize());
      resizeObserver.observe(ref.current);
    });
    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, [visible]);

  useEffect(() => {
    if (chart.current && option) chart.current.setOption({ ...option, aria: { enabled: true, label: { description: label } } }, { notMerge: true });
  }, [option]);

  useEffect(() => {
    chart.current?.resize();
  }, [height]);

  return html`<div ref=${wrapRef} style=${scroll ? "overflow-x:auto" : ""}>
    <div
      ref=${ref}
      class="chart-box"
      style=${`height:${height}px;${minWidth ? `min-width:${minWidth}px;` : ""}cursor:${onClick ? "pointer" : "default"}`}
      role="img"
      aria-label=${label}
    ></div>
  </div>`;
}
