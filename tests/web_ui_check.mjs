/* Prueba de ejecución DOM/Plotly simulada. No sustituye inspección visual. */
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import assert from "node:assert/strict";

export async function checkWebUI(root) {
  const html = await readFile(`${root}/app/index.html`, "utf8");
  const code = await readFile(`${root}/app/app.js`, "utf8");
  const snapshot = await readFile(`${root}/app/data/snapshot.js`, "utf8");
  const data = Object.fromEntries(await Promise.all(["overview", "series", "events"].map(async name =>
    [name, JSON.parse(await readFile(`${root}/app/data/${name}.json`, "utf8"))])));
  new vm.Script(code); new vm.Script(snapshot);
  const passed = [];
  for (const protocol of ["http:", "file:"]) {
    function element() {
      const classes = new Set();
      return { textContent: "", children: [], style: {}, attributes: {}, listeners: {}, dataset: {},
        classList: { add: x => classes.add(x), remove: x => classes.delete(x),
          toggle(x, force) { const yes = force ?? !classes.has(x); yes ? classes.add(x) : classes.delete(x); return yes; } },
        setAttribute(k, v) { this.attributes[k] = v; }, getAttribute(k) { return this.attributes[k]; },
        removeAttribute(k) { delete this.attributes[k]; }, appendChild(child) { this.children.push(child); },
        addEventListener(k, handler) { this.listeners[k] = handler; }, on(k, handler) { this.listeners[k] = handler; },
        querySelectorAll() { return []; }, focus() {} };
    }
    const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [`#${m[1]}`, element()]));
    const bindings = new Map([...html.matchAll(/data-bind="([^"]+)"/g)].map(m => [m[1], element()]));
    const rangeButtons = [...html.matchAll(/data-range="([^"]+)"/g)].map(m => Object.assign(element(), { dataset: { range: m[1] } }));
    const others = new Map([[".menu-toggle", element()], [".meter", element()]]);
    const errors = [], relayouts = [], restyles = [];
    let plotted, context;
    const document = {
      querySelector(selector) { assert(ids.has(selector) || others.has(selector), selector); return ids.get(selector) ?? others.get(selector); },
      querySelectorAll(selector) {
        if (selector === "[data-range]") return rangeButtons;
        const match = selector.match(/^\[data-bind="(.+)"\]$/);
        return match && bindings.has(match[1]) ? [bindings.get(match[1])] : [];
      },
      createElement: element, addEventListener() {},
      head: { appendChild(script) { assert.equal(script.src, "data/snapshot.js"); vm.runInContext(snapshot, context); script.onload(); } },
    };
    const Plotly = { async newPlot(chart, traces, layout, config) { plotted = { traces, layout, config }; },
      relayout(chart, update) { relayouts.push(update); }, restyle(chart, update, traces) { restyles.push({ update, traces }); } };
    const window = { Plotly };
    context = vm.createContext({ document, window, Plotly, location: { protocol }, Intl, Date,
      console: { error: error => errors.push(String(error)) },
      fetch: async path => ({ ok: true, json: async () => data[path.match(/data\/(.+)\.json/)[1]] }) });
    vm.runInContext(code, context);
    for (let i = 0; i < 20; i++) await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(errors, []);
    assert.equal(ids.get("#data-status").hidden, true);
    assert.equal(bindings.get("sessions").textContent, "2.371");
    assert.equal(bindings.get("signal_count").textContent, "70");
    assert.equal(bindings.get("train_events").textContent, "53");
    assert.equal(bindings.get("test_events").textContent, "17");
    assert.equal(bindings.get("test_net_precise").textContent, "+1,684%");
    assert.equal(bindings.get("net_p_precise").textContent, "0,342869");
    assert.equal(ids.get("#robustness-rows").children.length, 2);
    assert.equal(ids.get("#signal-rows").children.length, 10);
    assert.equal(plotted.traces.length, 4);
    assert.equal(plotted.traces[2].x.length + plotted.traces[3].x.length, 70);
    assert.equal(plotted.layout.hovermode, "closest");
    for (const [day, signal, entry] of [["2021-11-03", -1, "04-11-2021"], ["2021-11-09", 1, "10-11-2021"]]) {
      const trace = plotted.traces[signal === 1 ? 2 : 3];
      const i = trace.x.indexOf(day);
      assert(i >= 0);
      assert.equal(trace.customdata[i][4], entry);
      assert.equal(trace.customdata[i][2], "Train");
      assert(trace.hovertemplate.includes("%{x|%d/%m/%Y}"));
      assert(trace.hovertemplate.includes("Trade_Signal en la entrada"));
    }
    rangeButtons.find(b => b.dataset.range === "test").listeners.click();
    assert.equal(relayouts.at(-1)["xaxis.range"][0], "2023-11-03");
    ids.get("#chart-start").value = "2021-11-01";
    ids.get("#chart-end").value = "2021-11-12";
    ids.get("#apply-dates").listeners.click();
    assert.equal(relayouts.at(-1)["xaxis.range"][0], "2021-11-01");
    ids.get("#show-signals").listeners.change({ target: { checked: false } });
    assert.equal(restyles.at(-1).update.visible, false);
    const menu = others.get(".menu-toggle");
    menu.listeners.click(); assert.equal(menu.attributes["aria-expanded"], "true");
    menu.listeners.click(); assert.equal(menu.attributes["aria-expanded"], "false");
    passed.push({ protocol, status: "passed", chart_markers: 70, mode: "simulated DOM and Plotly; no visual rendering" });
  }
  return passed;
}
