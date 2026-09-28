// Aba Desempenho (RF17–RF22): KPIs, filtro de período, gráficos G1–G12 interativos e drill-down.
import { html, cx } from "../lib/html.js";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { useStore, getState, setState } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Button, EmptyState, IconButton, Segmented } from "../ui/core.js";
import { EChart } from "../ui/EChart.js";
import { Modal } from "../ui/overlay.js";
import { api } from "../lib/api.js";
import { prefs } from "../lib/cache.js";
import * as charts from "../lib/charts.js";
import { fmtDate, fmtDays, fmtNumber, fmtPct } from "../lib/format.js";
import { loadDashboard, toast } from "../actions.js";

export const PERIOD_OPTIONS = [
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "90d", label: "90 dias" },
  { value: "12m", label: "12 meses" },
  { value: "all", label: "Tudo" },
];

export async function openDrill(accountId, chart, key, period) {
  if (key === undefined || key === null) return;
  try {
    const result = await api.get(
      `/api/accounts/${accountId}/dashboard/drilldown?chart=${encodeURIComponent(chart)}&key=${encodeURIComponent(key)}&period=${period}`,
      { account: getState().meId },
    );
    setState({ panel: { title: result.title, taskIds: result.task_ids, accountId } });
  } catch (error) {
    toast(error.message || "Não foi possível abrir o detalhamento.", "error");
  }
}

function Delta({ current, previous, better = "up", suffix = "", digits = 0 }) {
  if (previous === null || previous === undefined || current === null || current === undefined) return html`<span class="kpi-delta">sem comparação</span>`;
  const diff = current - previous;
  if (Math.abs(diff) < 1e-9) return html`<span class="kpi-delta">= período anterior</span>`;
  const good = better === "up" ? diff > 0 : diff < 0;
  return html`<span class=${cx("kpi-delta", good ? "good" : "bad")}>
    <${Icon} name=${diff > 0 ? "arrowUp" : "arrowDown"} size=${12} />
    ${diff > 0 ? "+" : "−"}${fmtNumber(Math.abs(diff), digits)}${suffix} vs. período anterior
  </span>`;
}

function Kpis({ kpis, onDrill, periodLabel }) {
  const prev = kpis.previous;
  return html`<div class="kpis" role="list" aria-label="Indicadores">
    <button type="button" role="listitem" class="kpi" onClick=${() => onDrill("pending")}>
      <span class="kpi-label"><${Icon} name="circle" />Pendentes</span>
      <span class="kpi-value">${fmtNumber(kpis.pending, 0)}</span>
      <span class="kpi-delta">${kpis.due_soon ? `${kpis.due_soon} vencem em até 2 dias` : "estado atual"}</span>
    </button>
    <button type="button" role="listitem" class="kpi" onClick=${() => onDrill("overdue")}>
      <span class="kpi-label tone-critical"><${Icon} name="alert" />Atrasadas</span>
      <span class=${cx("kpi-value", kpis.overdue && "bad")}>${fmtNumber(kpis.overdue, 0)}</span>
      <span class="kpi-delta">${kpis.stale ? `${kpis.stale} parada${kpis.stale > 1 ? "s" : ""}` : "estado atual"}</span>
    </button>
    <button type="button" role="listitem" class="kpi" onClick=${() => onDrill("done")}>
      <span class="kpi-label tone-good"><${Icon} name="checkCircle" />Concluídas · ${periodLabel}</span>
      <span class="kpi-value">${fmtNumber(kpis.done, 0)}</span>
      <${Delta} current=${kpis.done} previous=${prev?.done} />
    </button>
    <div role="listitem" class="kpi">
      <span class="kpi-label"><${Icon} name="gauge" />Entregue no prazo</span>
      <span class="kpi-value">${kpis.on_time_pct === null ? "—" : html`${fmtNumber(kpis.on_time_pct, 0)}<small>%</small>`}</span>
      ${kpis.on_time_base
        ? html`<${Delta} current=${kpis.on_time_pct} previous=${prev?.on_time_pct} suffix=" p.p." />`
        : html`<span class="kpi-delta">sem entregas com data</span>`}
    </div>
    <div role="listitem" class="kpi">
      <span class="kpi-label"><${Icon} name="clock" />Tempo médio de conclusão</span>
      <span class="kpi-value">${kpis.avg_completion_days === null ? "—" : html`${fmtNumber(kpis.avg_completion_days)}<small>d</small>`}</span>
      <${Delta} current=${kpis.avg_completion_days} previous=${prev?.avg_completion_days} better="down" suffix=" d" digits=${1} />
    </div>
  </div>`;
}

function ChartCard({ id, title, subtitle, built, span, drillChart, accountId, period, extra }) {
  const [table, setTable] = useState(false);
  const onClick = built.drill && drillChart ? (params) => openDrill(accountId, drillChart, built.drill(params), period) : null;
  return html`<section class=${cx("chart-card", span && `span-${span}`)} aria-labelledby=${`chart-${id}`}>
    <div class="chart-head">
      <div class="grow">
        <h3 class="chart-title" id=${`chart-${id}`}><span class="chart-id">${id.toUpperCase()}</span>${title}</h3>
        ${subtitle ? html`<p class="chart-sub">${subtitle}</p>` : null}
      </div>
      <${IconButton}
        icon=${table ? "chart" : "table"}
        size="sm"
        label=${table ? "Ver gráfico" : "Ver dados em tabela"}
        aria-pressed=${table ? "true" : "false"}
        onClick=${() => setTable(!table)}
      />
    </div>
    ${table
      ? html`<div class="table-scroll">
          <table class="data-table">
            <caption class="sr-only">${title}</caption>
            <thead><tr>${built.table.columns.map((c, i) => html`<th key=${i} class=${i ? "num" : ""}>${c}</th>`)}</tr></thead>
            <tbody>
              ${built.table.rows.length
                ? built.table.rows.map((r, i) => html`<tr key=${i}>${r.map((cell, j) => html`<td key=${j} class=${j ? "num" : ""}>${cell}</td>`)}</tr>`)
                : html`<tr><td colspan=${built.table.columns.length} class="faint">Sem dados no período.</td></tr>`}
            </tbody>
          </table>
        </div>`
      : built.empty
        ? html`<div class="chart-empty">${built.emptyText || "Sem dados no período selecionado."}</div>`
        : html`<${EChart} option=${built.option} height=${built.height || 260} minWidth=${built.minWidth} onClick=${onClick} label=${`${title}. ${subtitle || ""}`} />`}
    ${built.note ? html`<p class="chart-sub">${built.note}</p>` : null}
    ${extra || null}
    ${onClick && !built.empty && !table ? html`<p class="chart-sub"><${Icon} name="eye" size=${12} style="display:inline;vertical-align:-2px" /> Clique em um elemento para ver as tarefas.</p>` : null}
  </section>`;
}

export function Dashboard({ accountId, period }) {
  const key = `${accountId}:${period}`;
  const entry = useStore((s) => s.dashboards[key]);
  const board = useStore((s) => s.boards[accountId]);

  useEffect(() => {
    if (!entry || entry.stale) loadDashboard(accountId, period, { force: !!entry?.stale });
  }, [key, entry?.stale]);

  // RF22: qualquer alteração em tarefas ou etapas recalcula KPIs e gráficos (com pequeno debounce)
  const tasksVersion = board?.tasks;
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return undefined;
    }
    const timer = setTimeout(() => loadDashboard(accountId, period, { force: true }), 500);
    return () => clearTimeout(timer);
  }, [tasksVersion]);

  const data = entry?.data;
  const built = useMemo(() => {
    if (!data) return null;
    const c = data.charts;
    return {
      g1: charts.g1(c.g1),
      g2: charts.g2(c.g2),
      g3: charts.g3(c.g3),
      g4: charts.g4(c.g4),
      g5: charts.g5(c.g5),
      g6: charts.g6(c.g6),
      g7: charts.g7(c.g7),
      g8: charts.g8(c.g8),
      g9: charts.g9(c.g9),
      g10: charts.g10(c.g10),
      g11: charts.g11(c.g11),
      g12: charts.g12(c.g12),
    };
  }, [data]);

  if (!data) {
    if (entry?.error) return html`<${EmptyState} icon="cloudOff" title="Dashboard indisponível" text=${entry.error} />`;
    return html`<div class="stack">
      <div class="kpis">${[1, 2, 3, 4, 5].map((i) => html`<div key=${i} class="skeleton" style="height:112px;border-radius:12px"></div>`)}</div>
      <div class="charts-grid">${[1, 2, 3, 4].map((i) => html`<div key=${i} class="chart-card skeleton" style="height:300px"></div>`)}</div>
    </div>`;
  }

  const periodLabel = data.period.label.toLowerCase();
  const common = { accountId, period };
  const g11 = data.charts.g11;
  const g10 = data.charts.g10;
  const sub = `Período: ${fmtDate(data.period.start)} a ${fmtDate(data.period.end)}`;

  return html`<div class=${cx("stack", entry.loading && "refreshing")} style="gap:18px;transition:opacity var(--dur-base)">
    <${Kpis} kpis=${data.kpis} periodLabel=${periodLabel} onDrill=${(k) => openDrill(accountId, "kpi", k, period)} />
    <div class="charts-grid">
      <${ChartCard} id="g1" span="8" title="Criadas × Concluídas" subtitle=${`Ritmo de entrega e evolução do backlog, por ${data.period.granularity === "week" ? "semana" : "dia"}`} built=${built.g1} ...${common} />
      <${ChartCard} id="g2" span="4" title="Distribuição por dificuldade" subtitle="Pendentes + concluídas no período" built=${built.g2} drillChart="g2" ...${common} />
      <${ChartCard}
        id="g3"
        span="4"
        title="Entregas no prazo"
        subtitle="Concluídas até 23:59 da data de entrega"
        built=${built.g3}
        ...${common}
        extra=${data.charts.g3.base
          ? html`<div class="row" style="justify-content:center">
              <${Button} size="sm" variant="ghost" onClick=${() => openDrill(accountId, "g3", "on_time", period)}>No prazo (${data.charts.g3.on_time})<//>
              <${Button} size="sm" variant="ghost" onClick=${() => openDrill(accountId, "g3", "late", period)}>Com atraso (${data.charts.g3.late})<//>
            </div>`
          : null}
      />
      <${ChartCard} id="g4" span="8" title="Desempenho por solicitante" subtitle="Concluídas no período, pendentes e atrasadas" built=${built.g4} drillChart="g4" ...${common} />
      <${ChartCard} id="g5" span="12" title="Mapa de atividade" subtitle=${`Etapas concluídas por dia · ${sub}`} built=${built.g5} drillChart="g5" ...${common} />
      <${ChartCard} id="g6" span="4" title="Tempo médio de conclusão" subtitle="Dias entre criação e conclusão, por nível" built=${built.g6} drillChart="g6" ...${common} />
      <${ChartCard} id="g7" span="4" title="Produtividade por dia da semana" subtitle="Etapas concluídas no período" built=${built.g7} ...${common} />
      <${ChartCard} id="g9" span="4" title="Causas de atraso" subtitle="Adiamentos por motivo no período" built=${built.g9} drillChart="g9" ...${common} />
      <${ChartCard} id="g8" span="6" title="Progresso das metas" subtitle="% de tarefas concluídas por meta" built=${built.g8} drillChart="g8" ...${common} />
      <${ChartCard} id="g12" span="6" title="Distribuição por fase" subtitle="Pendentes + concluídas no período, na ordem das fases" built=${built.g12} drillChart="g12" ...${common} />
      <${ChartCard}
        id="g10"
        span="6"
        title="Carga × capacidade"
        subtitle="Pontos: Fácil 1 · Médio 2 · Difícil 3. Independe do filtro de período."
        built=${built.g10}
        drillChart="g10"
        ...${common}
        extra=${html`<p class="chart-sub">
          ${g10.capacity === null
            ? "A capacidade aparece depois de 2 semanas completas de histórico."
            : html`Carga desta semana: <strong class="mono">${fmtNumber(g10.current_load)} pts</strong> · capacidade média (${g10.capacity_weeks} sem.): <strong class="mono">${fmtNumber(g10.capacity)} pts</strong>${g10.overloaded ? html` · <span style="color:var(--warning-text);font-weight:600">⚠ sobrecarga</span>` : ""}`}
        </p>`}
      />
      <${ChartCard}
        id="g11"
        span="6"
        title="Previsão de conclusão"
        subtitle=${g11.status === "ok"
          ? `Monte Carlo com ${fmtNumber(g11.simulations, 0)} simulações e throughput de ${g11.sample.length} semanas. Independe do filtro de período.`
          : "Simulação de Monte Carlo. Independe do filtro de período."}
        built=${built.g11}
        ...${common}
        extra=${g11.status === "ok"
          ? html`<div class="row-wrap small">
              ${g11.percentiles.map(
                (p) => html`<span key=${p.p} class="badge accent">
                  <strong class="mono">${p.p}%</strong>
                  ${p.beyond_horizon ? "além de 52 semanas" : `até ${fmtDate(p.date)}`}
                </span>`,
              )}
              <span class="faint xsmall">${g11.pending} pendentes · throughput semanal: ${g11.sample.join(", ")}</span>
            </div>`
          : null}
      />
    </div>
  </div>`;
}

function ReviewsModal({ accountId, onClose }) {
  const [reviews, setReviews] = useState(null);
  useEffect(() => {
    api
      .get(`/api/accounts/${accountId}/weekly-reviews`)
      .then(setReviews)
      .catch(() => setReviews([]));
  }, [accountId]);
  return html`<${Modal} title="Revisões semanais" icon="history" onClose=${onClose}>
    ${reviews === null
      ? html`<div class="skeleton" style="height:120px"></div>`
      : reviews.length
        ? html`<table class="data-table">
            <thead><tr><th>Semana</th><th class="num">Concluídas</th><th class="num">Atrasadas</th><th class="num">Adiadas</th><th class="num">Pontos</th></tr></thead>
            <tbody>
              ${reviews.map(
                (r) => html`<tr key=${r.week_start}>
                  <td>${fmtDate(r.summary.week_start)} a ${fmtDate(r.summary.week_end)}</td>
                  <td class="num">${r.summary.current.done}</td>
                  <td class="num">${r.summary.current.late}</td>
                  <td class="num">${r.summary.current.postponed}</td>
                  <td class="num">${r.summary.current.points}</td>
                </tr>`,
              )}
            </tbody>
          </table>`
        : html`<${EmptyState} compact icon="history" title="Nenhuma revisão ainda" text="A revisão da semana anterior aparece no primeiro acesso de cada semana." />`}
  <//>`;
}

export function PeriodFilter({ value, onChange }) {
  return html`<${Segmented} label="Período" value=${value} options=${PERIOD_OPTIONS} onChange=${onChange} />`;
}

export function usePeriod(key = "period") {
  const [period, setPeriod] = useState(() => prefs.get(key, "30d"));
  const choose = (value) => {
    setPeriod(value);
    prefs.set(key, value);
  };
  return [period, choose];
}

export function PerformanceView() {
  const meId = useStore((s) => s.meId);
  const [period, setPeriod] = usePeriod();
  const [reviews, setReviews] = useState(false);
  return html`<div class="stack" style="gap:18px">
    <header class="page-head">
      <div>
        <h1 class="page-title">Desempenho</h1>
        <p class="page-subtitle">Indicadores e gráficos das suas tarefas. Clique nos gráficos para ver as tarefas correspondentes.</p>
      </div>
      <${Button} icon="history" onClick=${() => setReviews(true)}>Revisões semanais<//>
    </header>
    <div class="toolbar toolbar-row" role="toolbar" aria-label="Filtros">
      <${PeriodFilter} value=${period} onChange=${setPeriod} />
    </div>
    <${Dashboard} accountId=${meId} period=${period} />
    ${reviews ? html`<${ReviewsModal} accountId=${meId} onClose=${() => setReviews(false)} />` : null}
  </div>`;
}
