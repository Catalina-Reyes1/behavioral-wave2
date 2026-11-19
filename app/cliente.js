(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const D = window.BW_CLIENTE;
  const fmt = (x, d = 2) => Number(x).toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (x, d = 1, sign = false) => (sign && x > 0 ? "+" : "") + fmt(x * 100, d).replace("-", "−") + "%";
  const sgn = (x, d = 1) => pct(x, d, true);
  const date = (s) => s.split("-").reverse().join("/");

  function bind(key, value) { document.querySelectorAll(`[data-v="${key}"]`).forEach((el) => { el.textContent = value; }); }

  function setupNavigation() {
    const menu = $(".menu-toggle"), nav = $("#navigation");
    const close = () => { nav.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); };
    menu.addEventListener("click", () => { const open = nav.classList.toggle("open"); menu.setAttribute("aria-expanded", String(open)); });
    nav.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
  }

  function fill() {
    const e = D.events, d = D.daily, t = D.table, y = D.yearly, h = D.holder_exit;
    const sig = (s, dir) => D.by_signal.find((r) => r.sample === s && r.direction === dir);
    const bh = t.buy_and_hold, ioc = t.ioc, lo = t.solo_compras;
    const period = `${date(D.period.test_start)} al ${date(D.period.test_end)}`;
    const vals = {
      r2: sgn(e.r2oos, 1), r2_abs: pct(Math.abs(e.r2oos), 1), r2_daily: sgn(d.r2oos, 2), r2_daily2: sgn(d.r2oos, 2),
      ecm_m: fmt(e.ecm_model * 1e4, 1) + " × 10⁻⁴", ecm_b: fmt(e.ecm_bench * 1e4, 1) + " × 10⁻⁴",
      mda: pct(e.mda, 1), up: pct(e.up_share, 0), up2: pct(e.up_share, 0), hits: e.hits,
      binom: fmt(e.mda_binom_p, 3), mda_gap: fmt((e.up_share - e.mda) * 100, 1),
      mda_daily: pct(d.mda, 1), up_daily: pct(d.up_share, 1),
      ag: fmt(e.ag_stat, 2).replace("-", "−"), agp: fmt(e.ag_p, 3), agp2: fmt(e.ag_p, 3),
      period, period2: period, sessions: D.period.sessions.toLocaleString("es-CL"),
      n_events: e.n, n_events2: e.n, n_events3: e.n, n_events4: e.n, n_long: e.n_long, n_long2: e.n_long, n_short: e.n_short,
      ioc_total: sgn(ioc.total, 1), bh_total: sgn(bh.total, 0), bh_total2: sgn(bh.total, 0), ops: ioc.trades,
      lo_total: sgn(lo.total, 1), lo_dd: pct(lo.max_dd, 1), lo_inv: pct(lo.invested, 1),
      tr_up: sgn(sig("Train", 1).mean, 1), te_up: sgn(sig("Test", 1).mean, 1), te_up_p: fmt(sig("Test", 1).p, 2),
      tr_dn: sgn(sig("Train", -1).mean, 1), te_dn: sgn(sig("Test", -1).mean, 1),
      y25: sgn(y.ioc["2025"], 1), y24bh: sgn(y.buy_and_hold["2024"], 0), y24ioc: pct(Math.abs(y.ioc["2024"]), 1),
      ioc_out: pct(1 - ioc.invested, 0), hx_total: sgn(h.total, 0), hx_dd: pct(h.max_dd, 1),
      gross: pct(Math.abs(e.gross_mean_test ?? 0), 2), tr_mean: sgn(e.train_net_mean ?? 0, 2), te_mean: sgn(e.test_net_mean ?? 0, 2),
      bh_mult: fmt(1 + bh.total, 1),
    };
    Object.entries(vals).forEach(([k, v]) => bind(k, v));

    const cls = (x) => (x > 0 ? "positive" : x < 0 ? "negative" : "");
    const rows = [
      ["Retorno total", (m) => sgn(m.total, 1), (m) => m.total],
      ["Retorno anualizado", (m) => sgn(m.annual, 1), (m) => m.annual],
      ["Volatilidad anualizada", (m) => pct(m.vol, 1)],
      ["Sharpe", (m) => fmt(m.sharpe, 2).replace("-", "−"), (m) => m.sharpe],
      ["Máxima caída", (m) => pct(m.max_dd, 1)],
      ["Tiempo invertido", (m) => pct(m.invested, 1)],
      ["Operaciones", (m) => String(m.trades)],
    ];
    const body = $("#perf-rows");
    rows.forEach(([label, f, c]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${label}</td>` + [bh, ioc, lo].map((m) => `<td class="num ${c ? cls(c(m)) : ""}">${f(m)}</td>`).join("");
      body.appendChild(tr);
    });
    const yb = $("#year-rows");
    Object.keys(y.buy_and_hold).forEach((yr) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${yr}</td>` + ["buy_and_hold", "ioc", "solo_compras"].map((k) => `<td class="num ${cls(y[k][yr])}">${sgn(y[k][yr], 1)}</td>`).join("");
      yb.appendChild(tr);
    });
    const sb = $("#signal-rows");
    D.by_signal.forEach((r) => {
      const tr = document.createElement("tr");
      if (r.sample === "Test") tr.className = "highlight";
      tr.innerHTML = `<td><b>${r.direction > 0 ? "+1 · compra" : "−1 · venta"}</b></td><td>${r.sample === "Test" ? "Test (fuera de muestra)" : "Train"}</td><td class="num">${r.n}</td><td class="num">${pct(r.win, 1)}</td><td class="num ${cls(r.mean)}">${sgn(r.mean, 2)}</td><td class="num">${fmt(r.p, 3)}</td>`;
      sb.appendChild(tr);
    });
  }

  // Curva de capital con los mismos precios y operaciones del estudio (misma lógica que src/oos_cliente.py).
  function curves() {
    const S = window.BEHAVIORAL_WAVE_DATA;
    const market = S.series.market.filter((r) => r.Date >= D.period.test_start);
    const dates = market.map((r) => r.Date);
    const prev = S.series.market[S.series.market.length - market.length - 1].NVDA_Price;
    const ret = market.map((r, i) => r.NVDA_Price / (i ? market[i - 1].NVDA_Price : prev) - 1);
    const trades = S.events.trades.filter((t) => t.Sample === "Test").sort((a, b) => a.Date.localeCompare(b.Date));
    const build = (mode) => {
      const pos = dates.map(() => (mode === "buy_and_hold" ? 1 : 0)), cost = dates.map(() => 0);
      let busy = null;
      if (mode !== "buy_and_hold") trades.forEach((t) => {
        if (busy && t.Date <= busy) return;
        if (mode === "solo_compras" && t.Trade_Signal < 0) return;
        const a = dates.indexOf(t.Date), b = dates.indexOf(t.Exit_Date);
        for (let i = a; i <= b; i++) pos[i] = t.Trade_Signal;
        cost[a] += 0.001; cost[b] += 0.001; busy = t.Exit_Date;
      });
      let eq = 1;
      return ret.map((r, i) => (eq *= 1 + pos[i] * r - cost[i]));
    };
    return { dates, buy_and_hold: build("buy_and_hold"), ioc: build("ioc"), solo_compras: build("solo_compras") };
  }

  function chart() {
    const el = $("#equity-chart");
    if (!window.Plotly || !window.BEHAVIORAL_WAVE_DATA) { el.textContent = "No se pudo cargar el gráfico."; return; }
    const C = curves();
    window.BW_CURVES = C;
    const x = C.dates;
    const line = (name, y, color, width) => ({ type: "scatter", mode: "lines", name, x, y, line: { color, width },
      hovertemplate: `${name}<br>%{x|%d/%m/%Y}: US$ %{y:,.2f}<extra></extra>` });
    const traces = [
      line("Comprar y mantener NVDA", C.buy_and_hold, "#1d1d1f", 1.6),
      line("Estrategia IOC", C.ioc, "#0071e3", 1.8),
      line("IOC solo compras", C.solo_compras, "#17804a", 1.8),
    ];
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
