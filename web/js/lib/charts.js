// Gráficos G1–G12 (seção 2.6) com ECharts: tooltip, legenda clicável e animação de entrada (RF20),
// clique para drill-down (RF21) e tabela equivalente para acessibilidade (RNF12).
// Cores validadas (CVD, visão normal e contraste) contra a superfície branca --chart-surface; ver
// docs/design-system.md. Os gráficos são o lugar das cores vivas; a interface ao redor fica neutra.
import { fmtDate, fmtDateShort, fmtNumber, MONTHS_SHORT } from "./format.js";
import { DIFFICULTY_COLOR, PHASE_COLOR } from "./rules.js";

export const COLORS = {
  surface: "#ffffff",
  series1: "#2a78d6",
  series2: "#eb6834",
  series3: "#1baf7a",
  good: "#16a34a",
  neutral: "#8a8a83",
  critical: "#dc2626",
  warning: "#d97706",
  text1: "#1d1d1b",
  text2: "#55554f",
  text3: "#6b6b64",
  grid: "#eeeae2",
  axis: "#d3cec3",
  seq: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"],
  empty: "#f1ede5",
  track: "#f1ede5",
  ring: "rgba(29, 29, 27, 0.16)",
};
// Números com algarismos tabulares, na mesma fonte da interface
const MONO = '"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const SANS = MONO;

let echartsPromise = null;

/** ECharts é carregado só quando o dashboard abre (RNF09: carga inicial ≤ 2 s). */
export function loadECharts() {
  if (!echartsPromise) {
    echartsPromise = import("/vendor/echarts.esm.min.js").then((echarts) => {
      echarts.registerTheme("odt", THEME);
      return echarts;
    });
  }
  return echartsPromise;
}

const THEME = {
  backgroundColor: "transparent",
  color: [COLORS.series1, COLORS.series2],
  textStyle: { fontFamily: SANS, color: COLORS.text2 },
  categoryAxis: {
    axisLine: { show: true, lineStyle: { color: COLORS.axis } },
    axisTick: { show: false },
    axisLabel: { color: COLORS.text3, fontSize: 11 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: COLORS.text3, fontSize: 11, fontFamily: MONO },
    splitLine: { show: true, lineStyle: { color: COLORS.grid, width: 1, type: "solid" } },
  },
  legend: { textStyle: { color: COLORS.text2, fontSize: 12 }, itemWidth: 12, itemHeight: 8, itemGap: 16, inactiveColor: "#c9c9c3" },
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: "#e7e7e3",
    borderWidth: 1,
    padding: [10, 14],
    textStyle: { color: COLORS.text1, fontSize: 12, fontFamily: SANS },
    extraCssText: "border-radius:12px;box-shadow:0 12px 32px rgba(29,29,27,.12);",
  },
};

export const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Textos vindos de usuários (solicitantes, metas) são escapados antes de entrar no tooltip. */
export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Linha do tooltip: traço curto na cor da série, valor em destaque e rótulo secundário. */
function row(color, value, label) {
  const key = color ? `<span style="display:inline-block;width:12px;height:2px;border-radius:2px;background:${color};margin-right:8px;vertical-align:middle"></span>` : "";
  return `<div style="display:flex;align-items:center;gap:2px;margin-top:3px">${key}<strong style="font-family:${MONO};min-width:34px">${esc(value)}</strong><span style="color:${COLORS.text2};margin-left:6px">${esc(label)}</span></div>`;
}

function head(text) {
  return `<div style="color:${COLORS.text3};font-size:11px;margin-bottom:2px">${esc(text)}</div>`;
}

function vGradient(color, top = 0.3) {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: hexAlpha(color, top) },
      { offset: 1, color: hexAlpha(color, 0) },
    ],
  };
}

function hexAlpha(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// Gradiente vivo (azul → verde-água) para o medidor e as barras de progresso dos gráficos
const VIVID_GRADIENT_H = {
  type: "linear",
  x: 0,
  y: 0,
  x2: 1,
  y2: 0,
  colorStops: [
    { offset: 0, color: COLORS.series1 },
    { offset: 1, color: COLORS.series3 },
  ],
};

function base(extra = {}) {
  const reduced = prefersReducedMotion();
  return {
    animation: !reduced,
    animationDuration: 650,
    animationEasing: "cubicOut",
    textStyle: { fontFamily: SANS },
    ...extra,
  };
}

function nice(max) {
  if (max <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  return Math.ceil(max / (magnitude / 2)) * (magnitude / 2);
}

const labelFor = (iso, granularity) => (granularity === "week" ? `sem ${fmtDateShort(iso)}` : fmtDateShort(iso));

// ---------------------------------------------------------------------------------------------
// G1 — Criadas × Concluídas
// ---------------------------------------------------------------------------------------------

export function g1(data) {
  const labels = data.labels.map((d) => labelFor(d, data.granularity));
  const empty = !data.created.some(Boolean) && !data.done.some(Boolean);
  const option = base({
    grid: { left: 4, right: 16, top: 40, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, data: ["Concluídas", "Criadas"] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: COLORS.axis, width: 1 } },
      formatter: (items) => {
        const index = items[0].dataIndex;
        const title = data.granularity === "week" ? `Semana de ${fmtDate(data.labels[index])}` : fmtDate(data.labels[index]);
        return head(title) + items.map((i) => row(i.color, fmtNumber(i.value, 0), i.seriesName)).join("") + row(null, fmtNumber(data.backlog[index], 0), "no backlog ao fim do intervalo");
      },
    },
    xAxis: { type: "category", boundaryGap: false, data: labels, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", minInterval: 1 },
    series: [
      {
        name: "Concluídas",
        type: "line",
        smooth: 0.35,
        smoothMonotone: "x",
        showSymbol: false,
        symbolSize: 8,
        data: data.done,
        lineStyle: { width: 2, color: COLORS.series1 },
        itemStyle: { color: COLORS.series1, borderColor: COLORS.surface, borderWidth: 2 },
        areaStyle: { color: vGradient(COLORS.series1, 0.3) },
        emphasis: { focus: "series" },
        z: 3,
      },
      {
        name: "Criadas",
        type: "line",
        smooth: 0.35,
        smoothMonotone: "x",
        showSymbol: false,
        symbolSize: 8,
        data: data.created,
        lineStyle: { width: 2, color: COLORS.series2 },
        itemStyle: { color: COLORS.series2, borderColor: COLORS.surface, borderWidth: 2 },
        areaStyle: { color: vGradient(COLORS.series2, 0.2) },
        emphasis: { focus: "series" },
        z: 2,
      },
    ],
  });
  return {
    option,
    empty,
    table: {
      columns: [data.granularity === "week" ? "Semana" : "Dia", "Criadas", "Concluídas", "Backlog"],
      rows: data.labels.map((d, i) => [fmtDate(d), data.created[i], data.done[i], data.backlog[i]]),
    },
  };
}

// ---------------------------------------------------------------------------------------------
// G2 — Distribuição por dificuldade (donut com total no centro)
// ---------------------------------------------------------------------------------------------

export function g2(data) {
  const option = base({
    tooltip: {
      trigger: "item",
      formatter: (p) => head("Dificuldade") + row(p.color, `${fmtNumber(p.value, 0)} (${fmtNumber(p.percent, 0)}%)`, p.name),
    },
    legend: { bottom: 0, left: "center", icon: "roundRect", formatter: (name) => `${name}  ${data.items.find((i) => i.label === name)?.value ?? ""}` },
    title: {
      text: fmtNumber(data.total, 0),
      subtext: data.total === 1 ? "tarefa" : "tarefas",
      left: "center",
      top: "33%",
      itemGap: 2,
      textStyle: { color: COLORS.text1, fontSize: 30, fontWeight: 600, fontFamily: MONO },
      subtextStyle: { color: COLORS.text3, fontSize: 12 },
    },
    series: [
      {
        type: "pie",
        radius: ["56%", "78%"],
        center: ["50%", "44%"],
        padAngle: 2,
        avoidLabelOverlap: true,
        label: { show: false },
        itemStyle: { borderRadius: 6, borderColor: COLORS.surface, borderWidth: 2 },
        emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 14, shadowColor: "rgba(29,29,27,0.18)" } },
        data: data.items.map((i) => ({ name: i.label, value: i.value, key: i.key, itemStyle: { color: DIFFICULTY_COLOR[i.key] } })),
      },
    ],
  });
  return {
    option,
    empty: data.total === 0,
    drill: (p) => p.data?.key,
    table: { columns: ["Dificuldade", "Tarefas"], rows: data.items.map((i) => [i.label, i.value]) },
  };
}

// ---------------------------------------------------------------------------------------------
// G3 — Entregas no prazo (gauge radial)
// ---------------------------------------------------------------------------------------------

export function g3(data) {
  const option = base({
    series: [
      {
        type: "gauge",
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: "96%",
        center: ["50%", "58%"],
        progress: {
          show: true,
          roundCap: true,
          width: 16,
          itemStyle: { color: VIVID_GRADIENT_H },
        },
        axisLine: { roundCap: true, lineStyle: { width: 16, color: [[1, COLORS.track]] } },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: { show: true, offsetCenter: [0, "36%"], color: COLORS.text3, fontSize: 12 },
        detail: {
          valueAnimation: !prefersReducedMotion(),
          offsetCenter: [0, "0%"],
          formatter: (v) => `${fmtNumber(v, 1)}%`,
          color: COLORS.text1,
          fontSize: 32,
          fontWeight: 600,
          fontFamily: MONO,
        },
        data: [{ value: data.value ?? 0, name: `${data.on_time} de ${data.base} no prazo` }],
      },
    ],
    tooltip: { formatter: () => head("Entregas no prazo") + row(COLORS.good, fmtNumber(data.on_time, 0), "no prazo") + row(COLORS.critical, fmtNumber(data.late, 0), "com atraso") },
  });
  return {
    option,
    empty: data.value === null,
    table: { columns: ["Indicador", "Valor"], rows: [["% no prazo", data.value === null ? "—" : `${fmtNumber(data.value)}%`], ["No prazo", data.on_time], ["Com atraso", data.late]] },
  };
}

// ---------------------------------------------------------------------------------------------
// G4 — Desempenho por solicitante (barras horizontais empilhadas; cores de status)
// ---------------------------------------------------------------------------------------------

const G4_SERIES = [
  { key: "done", name: "Concluídas", color: COLORS.good },
  { key: "pending", name: "Pendentes", color: COLORS.neutral },
  { key: "overdue", name: "Atrasadas", color: COLORS.critical },
];

export function g4(data) {
  const items = [...data.items].reverse(); // maior no topo
  const option = base({
    grid: { left: 4, right: 20, top: 34, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, data: G4_SERIES.map((s) => s.name) },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(29,29,27,0.05)" } },
      formatter: (list) => head(items[list[0].dataIndex].requester) + list.map((i) => row(i.color, fmtNumber(i.value, 0), i.seriesName)).join(""),
    },
    xAxis: { type: "value", minInterval: 1 },
    yAxis: { type: "category", data: items.map((i) => i.requester), axisLabel: { width: 120, overflow: "truncate", color: COLORS.text2 } },
    series: G4_SERIES.map((s) => ({
      name: s.name,
      type: "bar",
      stack: "total",
      barMaxWidth: 18,
      data: items.map((i) => i[s.key]),
      itemStyle: { color: s.color, borderRadius: 4, borderColor: COLORS.surface, borderWidth: 2 },
      emphasis: { focus: "series" },
    })),
  });
  return {
    option,
    empty: !items.length,
    height: Math.max(180, 60 + items.length * 34),
    drill: (p) => `${items[p.dataIndex].key}|${G4_SERIES.find((s) => s.name === p.seriesName).key}`,
    table: {
      columns: ["Solicitante", "Concluídas", "Pendentes", "Atrasadas"],
      rows: data.items.map((i) => [i.requester, i.done, i.pending, i.overdue]),
    },
    note: data.hidden ? `+${data.hidden} solicitantes com menos tarefas não exibidos.` : null,
  };
}

// ---------------------------------------------------------------------------------------------
// G5 — Mapa de atividade (heatmap de calendário)
// ---------------------------------------------------------------------------------------------

export function g5(data) {
  const start = new Date(`${data.start}T12:00:00`);
  const end = new Date(`${data.end}T12:00:00`);
  let from = data.start;
  let clipped = false;
  if ((end - start) / 86_400_000 > 371) {
    const d = new Date(end);
    d.setDate(d.getDate() - 364);
    from = d.toISOString().slice(0, 10);
    clipped = true;
  }
  const days = Math.round((end - new Date(`${from}T12:00:00`)) / 86_400_000) + 1;
  const cell = days <= 35 ? 26 : days <= 120 ? 17 : 13;
  const weeks = Math.ceil(days / 7) + 1;
  const option = base({
    tooltip: {
      formatter: (p) => head(fmtDate(p.value[0])) + row(COLORS.series1, fmtNumber(p.value[1], 0), p.value[1] === 1 ? "etapa concluída" : "etapas concluídas"),
    },
    visualMap: {
      show: data.max > 0,
      type: "continuous",
      min: 1,
      max: Math.max(data.max, 2),
      orient: "horizontal",
      right: 4,
      top: 0,
      itemWidth: 10,
      itemHeight: 90,
      text: ["Mais", "Menos"],
      textStyle: { color: COLORS.text3, fontSize: 11 },
      inRange: { color: COLORS.seq },
      calculable: false,
    },
    calendar: {
      range: [from, data.end],
      cellSize: [cell, cell],
      top: 42,
      left: "center",
      orient: "horizontal",
      splitLine: { show: false },
      itemStyle: { color: COLORS.empty, borderColor: COLORS.surface, borderWidth: 3 },
      dayLabel: { firstDay: 1, nameMap: ["D", "S", "T", "Q", "Q", "S", "S"], color: COLORS.text3, fontSize: 10 },
      monthLabel: { nameMap: MONTHS_SHORT, color: COLORS.text3, fontSize: 11 },
      yearLabel: { show: false },
    },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data: data.days, emphasis: { itemStyle: { borderColor: COLORS.text1, borderWidth: 1 } } }],
  });
  return {
    option,
    empty: false,
    height: 42 + cell * 7 + 28,
    minWidth: weeks * cell + 60,
    drill: (p) => p.value?.[0],
    note: clipped ? "Exibindo os últimos 12 meses do histórico." : `${fmtNumber(data.total, 0)} etapas concluídas no período.`,
    table: { columns: ["Dia", "Etapas concluídas"], rows: data.days.map(([d, n]) => [fmtDate(d), n]) },
  };
}

// ---------------------------------------------------------------------------------------------
// G6 — Tempo médio de conclusão por dificuldade
// ---------------------------------------------------------------------------------------------

export function g6(data) {
  const option = base({
    grid: { left: 4, right: 12, top: 24, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const item = data.items[p.dataIndex];
        return head(item.label) + row(p.color, item.avg_days === null ? "—" : `${fmtNumber(item.avg_days)} d`, `média de ${item.count} tarefa${item.count === 1 ? "" : "s"}`);
      },
    },
    xAxis: { type: "category", data: data.items.map((i) => i.label) },
    yAxis: { type: "value", name: "dias", nameTextStyle: { color: COLORS.text3, fontSize: 11 } },
    series: [
      {
        type: "bar",
        barMaxWidth: 24,
        data: data.items.map((i) => ({ value: i.avg_days ?? 0, key: i.key, itemStyle: { color: DIFFICULTY_COLOR[i.key], borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: "top", color: COLORS.text2, fontFamily: MONO, fontSize: 11, formatter: (p) => (data.items[p.dataIndex].avg_days === null ? "—" : `${fmtNumber(p.value)} d`) },
      },
    ],
  });
  return {
    option,
    empty: data.items.every((i) => i.avg_days === null),
    drill: (p) => data.items[p.dataIndex].key,
    table: { columns: ["Dificuldade", "Média (dias)", "Tarefas"], rows: data.items.map((i) => [i.label, i.avg_days === null ? "—" : fmtNumber(i.avg_days), i.count]) },
  };
}

// ---------------------------------------------------------------------------------------------
// G7 — Produtividade por dia da semana (radar)
// ---------------------------------------------------------------------------------------------

export function g7(data) {
  const max = nice(Math.max(...data.values, 1));
  const option = base({
    tooltip: {
      trigger: "item",
      formatter: () => head("Etapas concluídas") + data.labels.map((l, i) => row(null, fmtNumber(data.values[i], 0), l)).join(""),
    },
    radar: {
      indicator: data.labels.map((name) => ({ name, max })),
      radius: "68%",
      center: ["50%", "54%"],
      splitNumber: 4,
      axisName: { color: COLORS.text2, fontSize: 12 },
      splitLine: { lineStyle: { color: COLORS.grid } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: COLORS.grid } },
    },
    series: [
      {
        type: "radar",
        symbolSize: 6,
        data: [
          {
            value: data.values,
            name: "Etapas concluídas",
            areaStyle: { color: hexAlpha(COLORS.series1, 0.22) },
            lineStyle: { width: 2, color: COLORS.series1 },
            itemStyle: { color: COLORS.series1, borderColor: COLORS.surface, borderWidth: 2 },
          },
        ],
      },
    ],
  });
  return {
    option,
    empty: data.values.every((v) => !v),
    table: { columns: ["Dia", "Etapas concluídas"], rows: data.labels.map((l, i) => [l, data.values[i]]) },
  };
}

// ---------------------------------------------------------------------------------------------
// G8 — Progresso das metas
// ---------------------------------------------------------------------------------------------

export function g8(data) {
  const items = [...data.items].reverse();
  const option = base({
    grid: { left: 4, right: 70, top: 8, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const g = items[p.dataIndex];
        return (
          head(g.title) +
          row(COLORS.series1, `${g.progress}%`, `${g.done}/${g.total} tarefas concluídas`) +
          (g.overdue ? row(COLORS.critical, "⚠", "meta atrasada") : "") +
          (g.target_date ? row(null, fmtDate(g.target_date), "data-alvo") : "")
        );
      },
    },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    yAxis: {
      type: "category",
      data: items.map((g) => g.title),
      axisLabel: {
        width: 150,
        overflow: "truncate",
        color: COLORS.text2,
        formatter: (value, index) => (items[index]?.overdue ? `{warn|⚠} ${value}` : items[index]?.status === "concluida" ? `{ok|✓} ${value}` : value),
        rich: { warn: { color: "#b42318", fontWeight: 700 }, ok: { color: "#146c35", fontWeight: 700 } },
      },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 14,
        showBackground: true,
        backgroundStyle: { color: COLORS.track, borderRadius: 7 },
        itemStyle: { color: VIVID_GRADIENT_H, borderRadius: 7 },
        label: {
          show: true,
          position: "right",
          color: COLORS.text2,
          fontFamily: MONO,
          fontSize: 11,
          formatter: (p) => `${items[p.dataIndex].progress}% · ${items[p.dataIndex].done}/${items[p.dataIndex].total}`,
        },
        data: items.map((g) => g.progress),
      },
    ],
  });
  return {
    option,
    empty: !items.length,
    height: Math.max(160, 30 + items.length * 38),
    drill: (p) => items[p.dataIndex].id,
    table: {
      columns: ["Meta", "Progresso", "Concluídas/total", "Data-alvo", "Situação"],
      rows: data.items.map((g) => [g.title, `${g.progress}%`, `${g.done}/${g.total}`, g.target_date ? fmtDate(g.target_date) : "—", g.status === "concluida" ? "Concluída" : g.overdue ? "Atrasada" : "Em andamento"]),
    },
  };
}

// ---------------------------------------------------------------------------------------------
// G9 — Causas de atraso
// ---------------------------------------------------------------------------------------------

export function g9(data) {
  const items = [...data.items].reverse();
  const option = base({
    grid: { left: 4, right: 36, top: 8, bottom: 4, containLabel: true },
    tooltip: { trigger: "item", formatter: (p) => head(items[p.dataIndex].label) + row(COLORS.series1, fmtNumber(p.value, 0), p.value === 1 ? "adiamento" : "adiamentos") },
    xAxis: { type: "value", minInterval: 1 },
    yAxis: { type: "category", data: items.map((i) => i.label), axisLabel: { color: COLORS.text2, width: 170, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        data: items.map((i) => i.value),
        itemStyle: { color: COLORS.series1, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: COLORS.text2, fontFamily: MONO, fontSize: 11 },
      },
    ],
  });
  return {
    option,
    empty: data.total === 0,
    height: 190,
    drill: (p) => items[p.dataIndex].key,
    table: { columns: ["Motivo", "Adiamentos"], rows: data.items.map((i) => [i.label, i.value]) },
  };
}

// ---------------------------------------------------------------------------------------------
// G10 — Carga × capacidade
// ---------------------------------------------------------------------------------------------

export function g10(data) {
  const labels = data.weeks.map((w, i) => (i === data.current_index ? "Esta semana" : fmtDateShort(w)));
  const markLine =
    data.capacity !== null
      ? {
          silent: true,
          symbol: "none",
          lineStyle: { color: COLORS.text2, type: "dashed", width: 1.5 },
          label: { formatter: `Capacidade ${fmtNumber(data.capacity)} pts`, position: "insideEndTop", color: COLORS.text2, fontSize: 11 },
          data: [{ yAxis: data.capacity }],
        }
      : undefined;
  const markPoint = data.overloaded
    ? {
        symbol: "pin",
        symbolSize: 1,
        label: { show: true, formatter: "⚠ Sobrecarga", color: "#8a4b06", fontWeight: 600, fontSize: 11, offset: [0, -14] },
        data: [{ coord: [data.current_index, data.current_load] }],
      }
    : undefined;
  const option = base({
    grid: { left: 4, right: 12, top: 40, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, data: ["Concluído (pts)", "Carga (pts)"] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(29,29,27,0.05)" } },
      formatter: (list) => {
        const index = list[0].dataIndex;
        const rows = list.filter((i) => i.value !== null && i.value !== undefined).map((i) => row(i.color, `${fmtNumber(i.value, 0)} pts`, i.seriesName));
        if (data.capacity !== null) rows.push(row(COLORS.text2, `${fmtNumber(data.capacity)} pts`, "capacidade média"));
        return head(index === data.current_index ? "Semana atual (inclui atrasadas)" : `Semana de ${fmtDate(data.weeks[index])}`) + rows.join("");
      },
    },
    xAxis: { type: "category", data: labels, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", minInterval: 1, name: "pts", nameTextStyle: { color: COLORS.text3, fontSize: 11 } },
    series: [
      {
        name: "Concluído (pts)",
        type: "bar",
        barMaxWidth: 24,
        data: data.done,
        itemStyle: { color: COLORS.series1, borderRadius: [4, 4, 0, 0] },
        markLine,
      },
      {
        name: "Carga (pts)",
        type: "bar",
        barMaxWidth: 24,
        barGap: "-100%",
        data: data.load.map((v, i) => (v === null ? null : { value: v, itemStyle: i === data.current_index ? { borderColor: COLORS.text1, borderWidth: 1.5 } : undefined })),
        itemStyle: { color: COLORS.series2, borderRadius: [4, 4, 0, 0] },
        markPoint,
      },
    ],
  });
  return {
    option,
    empty: false,
    drill: (p) => data.weeks[p.dataIndex],
    table: {
      columns: ["Semana", "Concluído (pts)", "Carga (pts)"],
      rows: data.weeks.map((w, i) => [i === data.current_index ? `${fmtDate(w)} (atual)` : fmtDate(w), data.done[i] ?? "—", data.load[i] ?? "—"]),
    },
  };
}

// ---------------------------------------------------------------------------------------------
// G11 — Previsão de conclusão (Monte Carlo)
// ---------------------------------------------------------------------------------------------

export function g11(data) {
  if (data.status !== "ok") {
    return {
      option: null,
      empty: true,
      emptyText:
        data.status === "sem_pendentes"
          ? "Sem tarefas pendentes para prever."
          : `A previsão precisa de pelo menos ${data.min_weeks} semanas completas de histórico.`,
      table: { columns: ["Situação"], rows: [[data.status === "sem_pendentes" ? "Sem pendentes" : "Dados insuficientes"]] },
    };
  }
  const labels = data.curve.map((c) => fmtDateShort(c.date));
  // Percentis próximos teriam rótulos sobrepostos: rotula só os que ficam afastados do anterior rotulado;
  // todos continuam nas linhas tracejadas, nos selos abaixo do gráfico e na tabela.
  const minGap = Math.max(3, Math.round(data.curve.length / 6));
  let lastLabeled = -Infinity;
  const marks = data.percentiles
    .filter((p) => !p.beyond_horizon)
    .map((p) => {
      const index = data.curve.findIndex((c) => c.date === p.date);
      const labeled = index - lastLabeled >= minGap;
      if (labeled) lastLabeled = index;
      return { xAxis: index, name: `${p.p}% · ${fmtDateShort(p.date)}`, label: { show: labeled } };
    });
  const option = base({
    grid: { left: 4, right: 18, top: 42, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: COLORS.axis } },
      formatter: (list) => {
        const c = data.curve[list[0].dataIndex];
        return head(`Até ${fmtDate(c.date)} (${c.week} sem.)`) + row(COLORS.series1, `${fmtNumber(c.probability, 1)}%`, `de chance de concluir as ${data.pending} pendentes`);
      },
    },
    xAxis: { type: "category", boundaryGap: false, data: labels, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%" } },
    series: [
      {
        type: "line",
        smooth: 0.3,
        showSymbol: false,
        data: data.curve.map((c) => c.probability),
        lineStyle: { width: 2, color: COLORS.series1 },
        areaStyle: { color: vGradient(COLORS.series1, 0.26) },
        itemStyle: { color: COLORS.series1 },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: COLORS.text2, type: "dashed", width: 1 },
          label: { color: COLORS.text1, fontSize: 11, fontFamily: MONO, formatter: (p) => p.name },
          data: marks,
        },
      },
    ],
  });
  return {
    option,
    empty: false,
    table: {
      columns: ["Percentil", "Data", "Semanas"],
      rows: data.percentiles.map((p) => [`${p.p}%`, p.beyond_horizon ? "Além de 52 semanas" : fmtDate(p.date), p.week ?? "> 52"]),
    },
  };
}

// ---------------------------------------------------------------------------------------------
// G12 — Distribuição por fase
// ---------------------------------------------------------------------------------------------

export function g12(data) {
  const option = base({
    grid: { left: 4, right: 36, top: 8, bottom: 4, containLabel: true },
    tooltip: { trigger: "item", formatter: (p) => head(data.items[p.dataIndex].label) + row(p.color, fmtNumber(p.value, 0), p.value === 1 ? "tarefa" : "tarefas") },
    xAxis: { type: "value", minInterval: 1 },
    yAxis: { type: "category", inverse: true, data: data.items.map((i) => i.label), axisLabel: { color: COLORS.text2, width: 170, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        // Contorno sutil: o amarelo claro de Planejamento continua visível sobre o branco
        data: data.items.map((i) => ({ value: i.value, key: i.key, itemStyle: { color: PHASE_COLOR[i.key], borderRadius: [0, 4, 4, 0], borderColor: COLORS.ring, borderWidth: 1 } })),
        label: { show: true, position: "right", color: COLORS.text2, fontFamily: MONO, fontSize: 11 },
      },
    ],
  });
  return {
    option,
    empty: data.items.every((i) => !i.value),
    height: 220,
    drill: (p) => data.items[p.dataIndex].key,
    table: { columns: ["Fase", "Tarefas"], rows: data.items.map((i) => [i.label, i.value]) },
  };
}
