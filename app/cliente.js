(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const D = window.BW_CLIENTE;
  const fmt = (x, d = 2) => Number(x).toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d }).replace("-", "−");
  const pct = (x, d = 1, sign = false) => (sign && x > 0 ? "+" : "") + fmt(x * 100, d) + "%";
  const sgn = (x, d = 1) => pct(x, d, true);
  const date = (s) => s.split("-").reverse().join("/");
  const cls = (x) => (x > 0 ? "positive" : x < 0 ? "negative" : "");

  const SERIES = [
    ["buy_and_hold", "Comprar y mantener NVDA", "#1d1d1f"],
    ["ioc", "Estrategia IOC", "#0071e3"],
    ["solo_compras", "IOC solo compras (+1)", "#17804a"],
    ["voo", "Referencia: comprar y mantener VOO", "#a1a1a6"],
  ];

  function bind(key, value) { document.querySelectorAll(`[data-v="${key}"]`).forEach((el) => { el.textContent = value; }); }

  function setupNavigation() {
    const menu = $(".menu-toggle"), nav = $("#navigation");
    const close = () => { nav.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); };
    menu.addEventListener("click", () => { const open = nav.classList.toggle("open"); menu.setAttribute("aria-expanded", String(open)); });
    nav.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
  }

  function row(cells) { const tr = document.createElement("tr"); tr.innerHTML = cells.join(""); return tr; }

  function fill() {
    const e = D.events, a = D.all_days, t = D.table, y = D.yearly, h = D.holder_exit;
    const sig = (s, k) => D.by_signal.find((r) => r.sample === s && r.key === k);
    const reg = (s, k) => D.regime_ma50.find((r) => r.sample === s && r.key === k);
    const bh = t.buy_and_hold, ioc = t.ioc, lo = t.solo_compras;
    const period = `${date(D.period.test_start)} al ${date(D.period.test_end)}`;
    const vals = {
      r2: sgn(e.r2oos, 1), r2_abs: pct(Math.abs(e.r2oos), 1), r2_all: sgn(a.r2oos, 2), r2_all2: sgn(a.r2oos, 2),
      ecm_m: fmt(e.ecm_model * 1e4, 1) + " × 10⁻⁴", ecm_b: fmt(e.ecm_bench * 1e4, 1) + " × 10⁻⁴",
      cw: fmt(e.cw_stat, 2), cwp: fmt(e.cw_p, 3), cwp_all: fmt(a.cw_p, 3), n_all: a.n.toLocaleString("es-CL"),
      mda: pct(e.mda, 1), mda_f: pct(e.mda_forecast, 1), up: pct(e.up_share, 1), up2: pct(e.up_share, 1), up3: pct(e.up_share, 1), up_all: pct(a.up_share, 1), hits: e.hits, hits2: e.hits,
      binom: fmt(e.mda_binom_p, 3), mda_gap: fmt((e.up_share - e.mda) * 100, 1), mda_gap_all: fmt((e.mda - a.up_share) * 100, 1), win_net: pct(e.win_net, 1),
      ag: fmt(e.ag_stat, 2), agp: fmt(e.ag_p, 3), agp2: fmt(e.ag_p, 3), overlap: e.overlapping,
      period, period2: period, sessions: D.period.sessions.toLocaleString("es-CL"),
      n_events: e.n, n_events2: e.n, n_events3: e.n, n_events4: e.n, n_events5: e.n, n_events6: e.n, n_events7: e.n, n_events8: e.n, n_events9: e.n,
      n_long: e.n_long, n_long2: e.n_long, n_short: e.n_short,
      rf_src: D.rf_source.startsWith("^IRX") ? "letras del Tesoro de EE.UU. a 13 semanas, ^IRX" : D.rf_source, rf_mean: pct(D.rf_mean_annual, 2),
      ioc_total: sgn(ioc.total, 1), bh_total: sgn(bh.total, 1), bh_total2: sgn(bh.total, 1), ops: ioc.trades,
      lo_total: sgn(lo.total, 1), lo_dd: pct(lo.max_dd, 1), lo_inv: pct(lo.invested, 1),
      tr_up: sgn(sig("Train", 1).mean, 2), te_up: sgn(sig("Test", 1).mean, 2),
      tr_up_p: fmt(sig("Train", 1).p, 3), te_up_p: fmt(sig("Test", 1).p, 3),
      tr_dn: sgn(sig("Train", -1).mean, 2), te_dn: sgn(sig("Test", -1).mean, 2),
      rg_tr_below: sgn(reg("Train", true).mean, 2), rg_te_below: sgn(reg("Test", true).mean, 2),
      rg_tr_above: sgn(reg("Train", false).mean, 2), rg_te_above: sgn(reg("Test", false).mean, 2),
      y24bh: sgn(y.buy_and_hold["2024"], 1), y24ioc: sgn(y.ioc["2024"], 1),
      ioc_out: pct(1 - ioc.invested, 1), hx_total: sgn(h.total, 1), hx_dd: pct(h.max_dd, 1),
      gross: sgn(e.mean_gross, 2), net_all: sgn(e.mean_net, 2), breakeven: pct(D.breakeven_long, 2),
      tr_mean: sgn(D.eval1.Train.mean_t1, 2), te_mean: sgn(D.eval1.Test.mean_t1, 2),
      bh_mult: fmt(1 + bh.total, 1),
      te_all_p: fmt(D.eval1.Test.p_t1, 3), tr_all_p: fmt(D.eval1.Train.p_t1, 3),
    };
    Object.entries(vals).forEach(([k, v]) => bind(k, v));

    $("#eval1-rows").append(...["Train", "Test"].map((s) => {
      const r = D.eval1[s];
      return row([`<td>${s}</td>`, `<td class="num">${sgn(r.mean, 2)} · ${pct(r.win, 1)} ganadoras</td>`, `<td class="num"><b>${sgn(r.mean_t1, 2)} · ${pct(r.win_t1, 1)} ganadoras</b></td>`]);
    }));

    const cols = SERIES.filter(([k]) => t[k]);
    const head = (first) => row([`<th>${first}</th>`, ...cols.map(([, n]) => `<th class="num">${n.replace("Referencia: comprar y mantener", "Ref.: comprar y mantener")}</th>`)]);
    $("#perf-head").append(head("Métrica"));
    $("#year-head").append(head("Año"));
    [
      ["Retorno total", (m) => sgn(m.total, 1), (m) => m.total],
      ["Retorno anualizado", (m) => sgn(m.annual, 1), (m) => m.annual],
      ["Volatilidad anualizada", (m) => pct(m.vol, 1)],
      ["Sharpe (en exceso de rf)", (m) => fmt(m.sharpe, 2), (m) => m.sharpe],
      ["Máxima caída", (m) => pct(m.max_dd, 1)],
      ["Tiempo invertido en la acción", (m) => pct(m.invested, 1)],
      ["Operaciones", (m) => String(m.trades)],
    ].forEach(([label, f, c]) => $("#perf-rows").append(row([`<td>${label}</td>`, ...cols.map(([k]) => `<td class="num ${c ? cls(c(t[k])) : ""}">${f(t[k])}</td>`)])));
    Object.keys(y.buy_and_hold).forEach((yr) => $("#year-rows").append(row([`<td>${yr}</td>`, ...cols.map(([k]) => `<td class="num ${cls(y[k][yr])}">${sgn(y[k][yr], 1)}</td>`)])));

    D.by_signal.forEach((r) => {
      const tr = row([`<td><b>${r.key > 0 ? "+1 · compra" : "−1 · venta"}</b></td>`, `<td>${r.sample === "Test" ? "Test (fuera de muestra)" : "Train"}</td>`, `<td class="num">${r.n}</td>`, `<td class="num">${pct(r.win, 1)}</td>`, `<td class="num ${cls(r.mean)}">${sgn(r.mean, 2)}</td>`, `<td class="num">${fmt(r.p, 3)}</td>`]);
      if (r.sample === "Test") tr.className = "highlight";
      $("#signal-rows").append(tr);
    });
    D.regime_ma50.forEach((r) => {
      const tr = row([`<td><b>${r.key ? "Bajo la media de 50" : "Sobre la media de 50"}</b></td>`, `<td>${r.sample === "Test" ? "Test (fuera de muestra)" : "Train"}</td>`, `<td class="num">${r.n}</td>`, `<td class="num">${r.n_long}</td>`, `<td class="num">${pct(r.win, 1)}</td>`, `<td class="num ${cls(r.mean)}">${sgn(r.mean, 2)}</td>`, `<td class="num">${fmt(r.p, 3)}</td>`]);
      if (r.sample === "Test") tr.className = "highlight";
      $("#regime-rows").append(tr);
    });

    $("#legend").innerHTML = SERIES.filter(([k]) => D.curves[k]).map(([, n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join("");
  }

  function chart() {
    const el = $("#equity-chart");
    if (!window.Plotly) { el.textContent = "No se pudo cargar el gráfico."; return; }
    const traces = SERIES.filter(([k]) => D.curves[k]).map(([k, name, color]) => ({
      type: "scatter", mode: "lines", name, x: D.dates, y: D.curves[k], line: { color, width: k === "voo" ? 1.3 : 1.8, dash: k === "voo" ? "dot" : "solid" },
      hovertemplate: `${name}<br>%{x|%d/%m/%Y}: US$ %{y:,.2f}<extra></extra>`,
    }));
    const axis = { showgrid: true, gridcolor: "#f0f0f3", zeroline: false, tickfont: { color: "#6e6e73", size: 10 }, fixedrange: true };
    Plotly.newPlot(el, traces, {
      autosize: true, margin: { l: 52, r: 15, t: 12, b: 36 }, paper_bgcolor: "white", plot_bgcolor: "white", showlegend: false,
      font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif', color: "#1d1d1f", size: 11 },
      hovermode: "x unified", hoverlabel: { bgcolor: "white", bordercolor: "#dedee5", font: { size: 11 } }, separators: ",.",
      xaxis: { type: "date", showgrid: false, tickfont: { color: "#6e6e73", size: 10 }, fixedrange: true, tickformat: "%m/%Y" },
      yaxis: { ...axis, type: "log", tickvals: [0.5, 1, 2, 4, 8], ticktext: ["0,5", "1", "2", "4", "8"], title: { text: "US$ (log)", font: { size: 10, color: "#6e6e73" } } },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1, line: { color: "#b1b1ba", width: 1, dash: "dot" } }],
    }, { responsive: true, displaylogo: false, displayModeBar: false });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    if (!D) { document.body.insertAdjacentHTML("afterbegin", '<p class="error-note">No se pudieron cargar los datos de esta hoja.</p>'); return; }
    fill();
    chart();
  });
})();
