/* Presentación de resultados exportados. No estima modelos ni genera señales. */
"use strict";
(() => {
  const number = (value, digits = 0) => value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  const percent = (value, signed = false) => value == null ? "—" : `${signed && value > 0 ? "+" : ""}${number(value * 100, 2).replace("-", "−")}%`;
  const date = (value) => value ? new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(new Date(`${value.slice(0, 10)}T12:00:00Z`)) : "—";
  const direction = (value) => value == null ? "—" : value > 0 ? "+1" : value < 0 ? "−1" : "0";
  const $ = (selector) => document.querySelector(selector);
  const bind = (key, value) => document.querySelectorAll(`[data-bind="${key}"]`).forEach((element) => { element.textContent = value; });
  const tone = (element, value) => { element.classList.toggle("positive", value > 0); element.classList.toggle("negative", value < 0); };

  async function loadData() {
    if (location.protocol !== "file:") {
      const names = ["overview", "series", "events"];
      const values = await Promise.all(names.map(async (name) => {
        const response = await fetch(`data/${name}.json`, { cache: "no-cache" });
        if (!response.ok) throw new Error(`No se pudo leer data/${name}.json (HTTP ${response.status}).`);
        return response.json();
      }));
      return Object.fromEntries(names.map((name, i) => [name, values[i]]));
    }
    // Exportación idéntica a los JSON, para una presentación sin servidor ni conexión.
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "data/snapshot.js";
      script.onload = () => window.BEHAVIORAL_WAVE_DATA ? resolve(window.BEHAVIORAL_WAVE_DATA) : reject(new Error("La exportación local no contiene datos."));
      script.onerror = () => reject(new Error("No se encontró data/snapshot.js. Ejecuta python -m src.export_web_data."));
      document.head.appendChild(script);
    });
  }

  function fillPage(data) {
    const o = data.overview;
    const results = Object.fromEntries(o.results.map((row) => [row.Sample, row]));
    const train = results.Train, test = results.Test;
    const values = {
      sessions: number(o.sessions), signal_count: number(o.signal_count),
      period: `${o.period.start.slice(0, 4)}–${o.period.end.slice(0, 4)}`,
      market_start: date(o.period.start), market_end: date(o.period.end), attention_end: date(o.period.attention_end),
      train_sessions: number(o.split.train_count), test_sessions: number(o.split.test_count),
      train_pct: `${number(o.split.train_share * 100)}%`, test_pct: `${number((1 - o.split.train_share) * 100)}%`,
      test_start: date(o.split.test_start), train_net: percent(train.Mean_Net_Return, true), test_net: percent(test.Mean_Net_Return, true),
      train_trades: number(train.Trades), test_trades: number(test.Trades),
      train_win: `${number(train.Win_Rate_Pct, 2)}%`, test_win: `${number(test.Win_Rate_Pct, 2)}%`,
      net_p: number(test.Net_P_Value, 4), alpha: number(o.market_model.alpha, 8), beta: number(o.market_model.beta, 6), sigma: number(o.market_model.sigma_epsilon, 6),
      horizon: number(o.horizon_sessions), baseline_days: number(o.attention.baseline_days),
      latest_ioc: number(o.attention.latest_ioc, 1), latest_ioc_date: date(o.attention.latest_ioc_date),
      ioc_threshold: number(o.thresholds.IOC_Extreme_Threshold, 2),
      car_positive: number(o.thresholds.CAR_Positive_Threshold, 4), car_negative: number(o.thresholds.CAR_Negative_Threshold, 4),
      entry_cost: percent(o.entry_cost), exit_cost: percent(o.exit_cost), round_cost: percent(o.round_trip_cost),
      train_events: number(o.signal_counts.Train), test_events: number(o.signal_counts.Test),
      test_net_precise: `${test.Mean_Net_Return > 0 ? "+" : ""}${number(test.Mean_Net_Return * 100, 3)}%`,
      net_p_precise: number(test.Net_P_Value, 6),
      abnormal_mm: percent(test.Mean_Abnormal_MarketModel, true), abnormal_capm: percent(test.Mean_Abnormal_CAPM, true),
      mm_p: number(test.MarketModel_P_Value, 6), capm_p: number(test.CAPM_P_Value, 6),
    };
    Object.entries(values).forEach(([key, value]) => bind(key, value));
    ["train", "test"].forEach((sample) => document.querySelectorAll(`[data-bind="${sample}_net"]`).forEach((element) => tone(element, results[sample === "train" ? "Train" : "Test"].Mean_Net_Return)));
    $("#ioc-meter-fill").style.width = `${o.attention.latest_ioc}%`;
    $("#ioc-meter-dot").style.left = `${o.attention.latest_ioc}%`;
    $(".meter").setAttribute("aria-label", `IOC ${number(o.attention.latest_ioc, 1)} sobre 100`);
    $("#train-bar").style.width = `${o.split.train_share * 100}%`;
    $("#test-bar").style.width = `${(1 - o.split.train_share) * 100}%`;

    const addRow = (body, cells, signedColumns = {}) => {
      const row = document.createElement("tr");
      cells.forEach((text, index) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        if (index in signedColumns) tone(cell, signedColumns[index]);
        row.appendChild(cell);
      });
      body.appendChild(row);
    };
    const statRows = [["Retorno neto Test", "Net"], ["Anormal vs Market Model", "MarketModel"], ["Anormal vs CAPM", "CAPM"]];
    for (const [label, key] of statRows) addRow($("#stat-rows"), [label, number(test[`${key}_T_Statistic`], 4), number(test[`${key}_P_Value`], 4)]);
    const recent = o.robustness;
    addRow($("#robustness-rows"), ["Principal · " + values.period, number(o.sessions), number(o.signal_count), number(test.Trades), percent(test.Mean_Net_Return, true), number(test.Net_P_Value, 4)]);
    addRow($("#robustness-rows"), ["Robustez · " + recent.label.replace("Período reciente: ", ""), number(recent.sessions), number(recent.events), number(recent.test.Trades), percent(recent.test.Mean_Net_Return, true), number(recent.test.Net_P_Value, 4)]);
    const pValues = statRows.map(([, key]) => test[`${key}_P_Value`]);
    $("#stat-verdict").textContent = pValues.every((p) => p != null && p >= .05) ? "Ninguno alcanza significancia estadística al 5%." : "Consulta los p-values y las limitaciones de la inferencia estadística.";
    const metrics = [
      ["Operaciones evaluadas", "Trades", "count"], ["Ganadoras netas", "Win_Rate_Pct", "rate"],
      ["Retorno bruto medio", "Mean_Gross_Return", "signed"], ["Retorno neto medio", "Mean_Net_Return", "signed"],
      ["Mediana neta", "Median_Net_Return", "signed"], ["Desviación estándar neta", "Std_Net_Return", "percent"],
      ["Compuesto neto de eventos · no cartera", "Cumulative_Event_Net_Return", "signed"],
      ["Anormal neto medio · Market Model", "Mean_Abnormal_MarketModel", "signed"], ["Anormal neto medio · CAPM", "Mean_Abnormal_CAPM", "signed"],
      ["Eventos incompletos", "Incomplete_Events", "count"], ["Cruces Train/Test", "Boundary_Events", "count"],
    ];
    metrics.forEach(([label, key, format]) => {
      const numbers = [results.Train[key], results.Test[key], results.Total[key]];
      const cells = numbers.map((value) => format === "count" ? number(value) : format === "rate" ? `${number(value, 2)}%` : percent(value, format === "signed"));
      addRow($("#summary-rows"), [label, ...cells], format === "signed" ? Object.fromEntries(numbers.map((value, i) => [i + 1, value])) : {});
    });
    data.events.signals.slice(-10).forEach((event) => addRow($("#signal-rows"), [date(event.Date), event.Sample, number(event.IOC, 2), number(event.CAR_Z, 4), direction(event.Signal), direction(event.Trade_Signal)]));
  }

  async function drawChart(data) {
    const chart = $("#history-chart");
    if (!window.Plotly) throw new Error("No se pudo cargar la biblioteca local del gráfico.");
    const o = data.overview, market = data.series.market, attention = data.series.attention;
    const prices = new Map(market.map((row) => [row.Date, row.NVDA_Price]));
    const attentionByDate = new Map(attention.map((row) => [row.Date, row.IOC]));
    const x = market.map((row) => row.Date);
    const traces = [
      { type: "scatter", mode: "lines", name: "NVDA · USD", x, y: market.map((row) => row.NVDA_Price), line: { color: "#1d1d1f", width: 1.55 }, connectgaps: false,
        customdata: market.map((row) => [number(row.NVDA_Price, 2), number(attentionByDate.get(row.Date), 2)]),
        hovertemplate: "Fecha: %{x|%d/%m/%Y}<br>NVDA: USD %{customdata[0]}<br>IOC del día: %{customdata[1]}<extra></extra>" },
      { type: "scatter", mode: "lines", name: "IOC", x: attention.map((row) => row.Date), y: attention.map((row) => row.IOC), yaxis: "y2", line: { color: "#0071e3", width: 1.2 }, fill: "tozeroy", fillcolor: "rgba(0,113,227,.07)", connectgaps: false,
        customdata: attention.map((row) => [number(row.IOC, 2), prices.has(row.Date) ? `USD ${number(prices.get(row.Date), 2)}` : "Sin sesión de mercado"]),
        hovertemplate: "Fecha: %{x|%d/%m/%Y}<br>IOC del día: %{customdata[0]}<br>NVDA: %{customdata[1]}<extra></extra>" },
    ];
    [1, -1].forEach((sign) => {
      const events = data.events.signals.filter((row) => row.Signal === sign);
      traces.push({ type: "scatter", mode: "markers", name: `Signal ${sign === 1 ? "+1" : "−1"}`, x: events.map((row) => row.Date), y: events.map((row) => prices.get(row.Date)),
        marker: { symbol: sign === 1 ? "triangle-up" : "triangle-down", size: 7, color: sign === 1 ? "#0071e3" : "#6e6e73", line: { color: "white", width: .7 } },
        customdata: events.map((row) => [number(row.IOC, 2), number(row.CAR_Z, 3), row.Sample, number(row.NVDA_Price, 2), date(row.Entry_Date)]),
        hovertemplate: `<b>Evento: %{x|%d/%m/%Y}</b><br>NVDA: USD %{customdata[3]}<br>IOC del día: %{customdata[0]}<br>Signal ${sign === 1 ? "+1 · Posible reversión alcista" : "−1 · Posible reversión bajista"}<br>CAR_Z: %{customdata[1]}<br>Sample: %{customdata[2]}<br>Entrada t+1: %{customdata[4]}<br>Trade_Signal en la entrada: ${sign === 1 ? "+1" : "−1"}<extra></extra>` });
    });
    const axis = { showgrid: true, gridcolor: "#f0f0f3", zeroline: false, tickfont: { color: "#6e6e73", size: 10 }, fixedrange: true };
    const layout = {
      autosize: true, margin: { l: 48, r: 15, t: 28, b: 37 }, paper_bgcolor: "white", plot_bgcolor: "white", showlegend: false,
      font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif', color: "#1d1d1f", size: 11 },
      // Una etiqueta por punto: nunca reunir eventos de fechas diferentes.
      hovermode: "closest", hoverdistance: 12, hoverlabel: { bgcolor: "white", bordercolor: "#dedee5", font: { size: 11 } }, dragmode: "zoom", separators: ",.",
      xaxis: { type: "date", anchor: "y2", range: [o.period.start, o.period.end], showgrid: false, tickfont: { color: "#6e6e73", size: 10 }, tickformat: "%Y", hoverformat: "%d/%m/%Y", fixedrange: false },
      yaxis: { ...axis, domain: [.42, 1], title: { text: "NVDA · USD", font: { size: 10, color: "#6e6e73" }, standoff: 8 }, rangemode: "tozero" },
      yaxis2: { ...axis, domain: [0, .28], title: { text: "IOC", font: { size: 10, color: "#0071e3" }, standoff: 8 }, range: [0, 105], tickvals: [0, 50, 100] },
      shapes: [
        { type: "line", xref: "x", yref: "paper", x0: o.split.test_start, x1: o.split.test_start, y0: 0, y1: 1, line: { color: "#b1b1ba", width: 1, dash: "dot" } },
        { type: "line", xref: "paper", yref: "y2", x0: 0, x1: 1, y0: o.thresholds.IOC_Extreme_Threshold, y1: o.thresholds.IOC_Extreme_Threshold, line: { color: "#0071e355", width: 1, dash: "dot" } },
      ],
      annotations: [{ x: o.split.test_start, y: 1.05, xref: "x", yref: "paper", text: "INICIO TEST", showarrow: false, font: { size: 9, color: "#6e6e73" }, xanchor: "left", xshift: 5 }],
    };
    chart.textContent = "";
    await Plotly.newPlot(chart, traces, layout, { responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false, doubleClick: "reset" });
    const startInput = $("#chart-start"), endInput = $("#chart-end");
    [startInput, endInput].forEach((input) => { input.min = o.period.start; input.max = o.period.end; });
    startInput.value = o.period.start;
    endInput.value = o.period.end;
    function setRange(start, end, selected) {
      startInput.value = start;
      endInput.value = end;
      const duration = (Date.parse(end) - Date.parse(start)) / 86400000;
      Plotly.relayout(chart, { "xaxis.range": [start, end], "xaxis.autorange": false, "xaxis.tickformat": duration > 800 ? "%Y" : duration > 100 ? "%m/%Y" : "%d/%m" });
      document.querySelectorAll("[data-range]").forEach((button) => { button.classList.toggle("selected", button.dataset.range === selected); button.setAttribute("aria-pressed", String(button.dataset.range === selected)); });
      $("#date-error").textContent = "";
    }
    document.querySelectorAll("[data-range]").forEach((button) => button.addEventListener("click", () => {
      const key = button.dataset.range;
      let start = o.period.start, end = o.period.end;
      if (key === "train") end = o.split.train_end;
      if (key === "test") start = o.split.test_start;
      if (key === "1y") { const yearAgo = new Date(`${end}T12:00:00Z`); yearAgo.setUTCFullYear(yearAgo.getUTCFullYear() - 1); start = yearAgo.toISOString().slice(0, 10); if (start < o.period.start) start = o.period.start; }
      setRange(start, end, key);
    }));
    $("#apply-dates").addEventListener("click", () => {
      const start = startInput.value, end = endInput.value;
      if (!start || !end || start >= end || start < o.period.start || end > o.period.end) {
        $("#date-error").textContent = "Selecciona un período válido dentro del histórico."; return;
      }
      setRange(start, end, null);
    });
    $("#show-signals").addEventListener("change", (event) => Plotly.restyle(chart, { visible: event.target.checked }, [2, 3]));
    chart.on("plotly_relayout", (event) => {
      if (event["xaxis.range[0]"] && event["xaxis.range[1]"]) {
        startInput.value = event["xaxis.range[0]"].slice(0, 10);
        endInput.value = event["xaxis.range[1]"].slice(0, 10);
        document.querySelectorAll("[data-range]").forEach((button) => { button.classList.remove("selected"); button.setAttribute("aria-pressed", "false"); });
      }
    });
    chart.on("plotly_doubleclick", () => { setRange(o.period.start, o.period.end, "all"); return false; });
  }

  function setupNavigation() {
    const menu = $(".menu-toggle"), nav = $("#navigation");
    const close = () => { nav.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); menu.setAttribute("aria-label", "Abrir navegación"); };
    menu.addEventListener("click", () => { const open = nav.classList.toggle("open"); menu.setAttribute("aria-expanded", String(open)); menu.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación"); });
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") { close(); menu.focus(); } });
    if ("IntersectionObserver" in window) {
      const links = [...nav.querySelectorAll("a")];
      const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) if (entry.isIntersecting) links.forEach((link) => {
          const active = link.getAttribute("href") === `#${entry.target.id}`;
          link.classList.toggle("active", active);
          if (active) link.setAttribute("aria-current", "location"); else link.removeAttribute("aria-current");
        });
      }, { rootMargin: "-15% 0px -60% 0px", threshold: 0 });
      links.forEach((link) => observer.observe($(link.getAttribute("href"))));
    }
  }

  function setupReveal() {
    if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); }
    }), { threshold: .04 });
    document.querySelectorAll(".reveal").forEach((section) => { section.classList.add("js-reveal"); observer.observe(section); });
  }

  async function init() {
    setupNavigation();
    try {
      const data = await loadData();
      fillPage(data);
      $("#data-status").hidden = true;
      try { await drawChart(data); } catch (error) {
        $("#history-chart").textContent = "El gráfico no está disponible. Puedes descargar las series JSON bajo el gráfico.";
        console.error(error);
      }
      setupReveal();
    } catch (error) {
      const status = $("#data-status");
      status.classList.add("error");
      status.textContent = `No se pudieron cargar los resultados. ${error.message}`;
      console.error(error);
    }
  }
  init();
})();
