"""Trabajo de Aplicación II: evaluación fuera de muestra del indicador para la hoja "Para el cliente".

Usa las mismas señales, umbrales (IOC 65,39 fijado en Train) y operaciones exportadas por la
Evaluación 1 en app/data (series.json y events.json). No recalcula ni modifica nada de ese estudio.

Corrección de temporización respecto de la Evaluación 1
- La señal del día t usa las visitas de Wikipedia del día t (día UTC), que recién se completan
  después del cierre de la bolsa. Por eso aquí se entra al cierre de t+1 y se sale 5 sesiones después:
  retorno = P(t+6) / P(t+1) - 1.

Diseño
- Activo: NVDA. Horizonte: 5 sesiones. Período fuera de muestra: Test (15/05/2023 a 08/09/2026).
- Ventana recursiva (expansiva): en cada fecha t solo se usan datos conocidos al cierre de t.
- R2oos: pronóstico y = a + b * señal, estimado con los eventos ya cerrados en t, contra la media
  histórica recursiva del retorno a 5 sesiones de NVDA.
- Clark y West (2007), una cola, para saber si el R2oos es significativo.
- MDA y Anatolyev y Gerko (2005, una cola): dirección de la señal (+1 sube, -1 baja).
- Chequeo en todas las sesiones de Test: el mismo modelo a 5 sesiones, con señal 0 los días sin evento.
- Backtest: la caja rinde la tasa libre de riesgo (^IRX / 100 / 252, la misma de la Evaluación 1);
  Sharpe sobre retorno en exceso; costo de 0,10% por lado, también para comprar y mantener.

Uso
  python -m src.oos_cliente --descargar   # descarga ^IRX y VOO (GitHub Actions) y guarda data/trabajo2/irx_voo.csv
  python -m src.oos_cliente               # usa data/trabajo2/irx_voo.csv si existe
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
EXTRA = ROOT / "data" / "trabajo2" / "irx_voo.csv"
TEST_START = pd.Timestamp("2023-05-15")
H = 5          # sesiones de tenencia
COST = 0.001   # 0,10% por lado


def anatolyev_gerko(direction, y):
    """Estadístico EP de Anatolyev y Gerko (2005) y valor p de una cola. None si la dirección no varía."""
    d = np.sign(np.asarray(direction, float))
    y = np.asarray(y, float)
    T = len(y)
    A = np.mean(d * y)
    B = np.mean(d) * np.mean(y)
    p = 0.5 * (1 + np.mean(d))
    V = 4 / T**2 * p * (1 - p) * np.sum((y - y.mean()) ** 2)
    if V <= 0:
        return None, None
    ep = (A - B) / np.sqrt(V)
    return float(ep), float(1 - stats.norm.cdf(ep))


def clark_west(y, f, bench):
    """Clark y West (2007): ¿el modelo reduce el error frente a la media histórica? Una cola, t con errores de Newey-West."""
    y, f, bench = (np.asarray(v, float) for v in (y, f, bench))
    adj = (y - bench) ** 2 - ((y - f) ** 2 - (bench - f) ** 2)
    T = len(adj)
    u = adj - adj.mean()
    L = H - 1                                                     # rezagos por ventanas de 5 sesiones que se solapan
    v = np.sum(u * u) / T
    for k in range(1, L + 1):
        v += 2 * (1 - k / (L + 1)) * np.sum(u[k:] * u[:-k]) / T
    t = adj.mean() / np.sqrt(v / T)
    return float(t), float(1 - stats.norm.cdf(t))


def load():
    s = json.loads((DATA / "series.json").read_text(encoding="utf-8"))
    ev = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    m = pd.DataFrame(s["market"])
    m["Date"] = pd.to_datetime(m["Date"])
    m = m.set_index("Date").sort_index()
    m["r"] = m["NVDA_Price"].pct_change()
    m["ma50"] = m["NVDA_Price"].rolling(50).mean()  # usa cierres hasta t: conocida al cierre de t
    tr = pd.DataFrame(ev["trades"])
    for c in ["Date", "Signal_Date", "Exit_Date"]:
        tr[c] = pd.to_datetime(tr[c])
    P = m["NVDA_Price"].to_numpy()
    i = np.array([m.index.get_loc(d) for d in tr["Signal_Date"]])
    tr["i"] = i
    tr["entry_i"] = i + 1
    tr["exit_i"] = i + 1 + H
    tr["y"] = P[i + 1 + H] / P[i + 1] - 1                    # retorno de NVDA entre t+1 y t+6
    tr["net"] = tr["Trade_Signal"] * tr["y"] - 2 * COST      # retorno de la operación después de costos
    tr["below_ma50"] = m["NVDA_Price"].to_numpy()[i] < m["ma50"].to_numpy()[i]
    return m, tr


def load_extra(download):
    """^IRX y VOO. Con --descargar los baja de Yahoo Finance igual que la Evaluación 1."""
    if download:
        import yfinance as yf

        raw = yf.download(["^IRX", "VOO"], start="2023-04-01", end="2026-09-10", auto_adjust=False,
                          progress=False, group_by="column")
        irx = raw["Close"]["^IRX"].rename("IRX_Annual_Percent")
        field = "Adj Close" if "Adj Close" in raw.columns.get_level_values(0) else "Close"
        voo = raw[field]["VOO"].rename("VOO_Price")
        extra = pd.concat([irx, voo], axis=1).sort_index()
        extra.index = pd.to_datetime(extra.index).tz_localize(None)
        extra.index.name = "Date"
        EXTRA.parent.mkdir(parents=True, exist_ok=True)
        extra.to_csv(EXTRA)
    if EXTRA.exists():
        return pd.read_csv(EXTRA, parse_dates=["Date"], index_col="Date")
    return None


def rf_and_voo(m, extra):
    idx = m.index
    if extra is None or extra["IRX_Annual_Percent"].dropna().empty:
        return pd.Series(0.0, index=idx), None, "no disponible (caja al 0%)"
    rates = extra["IRX_Annual_Percent"].dropna()
    cal = idx.union(rates.index)
    rate = rates.reindex(cal).ffill().reindex(idx)              # solo arrastra tasas anteriores
    # El interés del día d se devenga con la tasa observada al cierre de d-1.
    rf = (rate / 100 / 252).shift(1).fillna(0.0)
    voo = extra["VOO_Price"].dropna().reindex(idx) if "VOO_Price" in extra else None
    return rf, voo, "^IRX (Yahoo Finance)"


def event_oos(m, tr):
    P = pd.Series(m["NVDA_Price"].to_numpy())
    y5_end = P / P.shift(H) - 1                                   # ventana de 5 sesiones que termina en s
    test = tr[tr["Sample"] == "Test"].sort_values("i")
    rows = []
    for _, e in test.iterrows():
        t = e["i"]
        past = tr[tr["exit_i"] <= t]                              # eventos ya cerrados al cierre de t
        X = np.column_stack([np.ones(len(past)), past["Trade_Signal"]])
        a, b = np.linalg.lstsq(X, past["y"].to_numpy(), rcond=None)[0]
        bench = y5_end.iloc[: t + 1].mean()                       # retornos a 5 sesiones ya conocidos en t
        rows.append(dict(direction=e["Trade_Signal"], y=e["y"], net=e["net"],
                         forecast=a + b * e["Trade_Signal"], bench=bench))
    o = pd.DataFrame(rows)
    ecm_m = float(((o.y - o.forecast) ** 2).mean())
    ecm_b = float(((o.y - o.bench) ** 2).mean())
    hits = int((np.sign(o.direction) == np.sign(o.y)).sum())
    ep, p = anatolyev_gerko(o.direction, o.y)
    cw, cw_p = clark_west(o.y, o.forecast, o.bench)
    # Ventanas que se solapan con la anterior (comparten días de retorno).
    starts = test["entry_i"].to_numpy()
    overlap = int(np.sum(np.diff(starts) < H))
    return dict(
        n=len(o), n_long=int((o.direction > 0).sum()), n_short=int((o.direction < 0).sum()),
        ecm_model=ecm_m, ecm_bench=ecm_b, r2oos=1 - ecm_m / ecm_b,
        forecast_down=int((o.forecast < 0).sum()),
        mda_forecast=float((np.sign(o.forecast) == np.sign(o.y)).mean()),
        mda=hits / len(o), hits=hits, up_share=float((o.y > 0).mean()),
        mda_binom_p=float(stats.binomtest(hits, len(o), 0.5, alternative="greater").pvalue),
        ag_stat=ep, ag_p=p, cw_stat=cw, cw_p=cw_p,
        win_net=float((o.net > 0).mean()), mean_net=float(o.net.mean()), mean_gross=float((o.net + 2 * COST).mean()),
        overlapping=overlap,
    )


def all_days_check(m, tr):
    """Mismo modelo a 5 sesiones en todas las sesiones de Test (señal 0 los días sin evento)."""
    P = m["NVDA_Price"].to_numpy()
    n = len(P)
    sig = pd.Series(0.0, index=range(n))
    sig[tr["i"].to_numpy()] = tr["Trade_Signal"].to_numpy()
    y = pd.Series(np.nan, index=range(n))
    y.iloc[: n - 1 - H] = P[1 + H:] / P[1: n - H] - 1             # y(s) = P(s+6)/P(s+1) - 1, conocido en s+6
    y5_end = pd.Series(P) / pd.Series(P).shift(H) - 1
    first = m.index.get_loc(TEST_START)
    rows = []
    for t in range(first, n - 1 - H):
        k = t - (1 + H) + 1                                       # pares con s+6 <= t
        X = np.column_stack([np.ones(k), sig.iloc[:k]])
        a, b = np.linalg.lstsq(X, y.iloc[:k].to_numpy(), rcond=None)[0]
        rows.append((y.iloc[t], a + b * sig.iloc[t], y5_end.iloc[: t + 1].mean()))
    o = pd.DataFrame(rows, columns=["y", "f", "bench"])
    ep, p = anatolyev_gerko(o.f, o.y)
    cw, cw_p = clark_west(o.y, o.f, o.bench)
    return dict(
        n=len(o),
        r2oos=float(1 - ((o.y - o.f) ** 2).sum() / ((o.y - o.bench) ** 2).sum()),
        mda=float((np.sign(o.f) == np.sign(o.y)).mean()),
        up_share=float((o.y > 0).mean()),
        share_forecast_up=float((o.f > 0).mean()),
        ag_stat=ep, ag_p=p, cw_stat=cw, cw_p=cw_p,
    )


def schedule(m, tr, mode):
    """Posición diaria en Test y costos. No se apilan operaciones: una señal con otra abierta se ignora."""
    first = m.index.get_loc(TEST_START)
    n = len(m)
    pos = np.zeros(n)
    cost = np.zeros(n)
    trades, busy = 0, -1
    for _, e in tr[tr["Sample"] == "Test"].sort_values("entry_i").iterrows():
        if e["entry_i"] <= busy:
            continue
        d = e["Trade_Signal"]
        if (mode == "solo_compras" and d < 0) or (mode == "solo_ventas" and d > 0):
            continue
        pos[e["entry_i"] + 1: e["exit_i"] + 1] = d                # retornos de t+2 a t+6
        cost[e["entry_i"]] += COST                                # compra o venta al cierre de t+1
        cost[e["exit_i"]] += COST                                 # cierre al final de t+6
        trades += 1
        busy = e["exit_i"]
    return pos[first:], cost[first:], trades


def returns(r, rf, pos, cost):
    """Largo: r. Corto: rf - r (la garantía en caja rinde rf; sin costo de préstamo). Sin posición: rf."""
    return np.where(pos > 0, r, np.where(pos < 0, rf - r, rf)) - cost


def metrics(ret, rf, pos, trades):
    ret = pd.Series(np.asarray(ret, float))
    ex = ret - rf.to_numpy()
    eq = (1 + ret).cumprod()
    T = len(ret)
    return dict(
        total=float(eq.iloc[-1] - 1),
        annual=float(eq.iloc[-1] ** (252 / T) - 1),
        vol=float(ret.std() * np.sqrt(252)),
        sharpe=float(ex.mean() / ex.std() * np.sqrt(252)),
        max_dd=float((eq / eq.cummax() - 1).min()),
        invested=float((np.asarray(pos) != 0).mean()),
        trades=int(trades),
    )


def by_group(tr, col, values):
    out = []
    for sample in ["Train", "Test"]:
        for v in values:
            x = tr[(tr["Sample"] == sample) & (tr[col] == v)]
            out.append(dict(sample=sample, key=bool(v) if isinstance(v, (bool, np.bool_)) else float(v), n=len(x),
                            n_long=int((x["Trade_Signal"] > 0).sum()),
                            win=float((x["net"] > 0).mean()), mean=float(x["net"].mean()),
                            mean_gross=float((x["Trade_Signal"] * x["y"]).mean()),
                            p=float(stats.ttest_1samp(x["net"], 0).pvalue) if len(x) > 1 else None))
    return out


def main(download=False):
    m, tr = load()
    extra = load_extra(download)
    rf_all, voo_all, rf_source = rf_and_voo(m, extra)
    te = m[m.index >= TEST_START]
    first = m.index.get_loc(TEST_START)
    r = te["r"].to_numpy()
    rf = rf_all.iloc[first:]

    table, yearly, curves = {}, {}, {}

    def add(name, ret, pos, trades):
        table[name] = metrics(ret, rf, pos, trades)
        s = pd.Series(ret, index=te.index)
        yearly[name] = {str(y): float((1 + g).prod() - 1) for y, g in s.groupby(s.index.year)}
        curves[name] = [round(v, 4) for v in (1 + s).cumprod().tolist()]

    ones = np.ones(len(te))
    bh_cost = np.zeros(len(te))
    bh_cost[0] = COST                                            # entrada de 0,10% también para comprar y mantener
    add("buy_and_hold", r - bh_cost, ones, 1)
    for mode in ["ioc", "solo_compras"]:
        pos, cost, k = schedule(m, tr, mode)
        add(mode, returns(r, rf.to_numpy(), pos, cost), pos, k)
    if voo_all is not None and voo_all.iloc[first - 1:].notna().all():
        rv = (voo_all / voo_all.shift(1) - 1).iloc[first:].to_numpy()
        add("voo", rv - bh_cost, ones, 1)

    # Inversionista que mantiene NVDA y pasa a caja durante cada señal -1.
    pos_s, _, k_s = schedule(m, tr, "solo_ventas")
    out = pos_s < 0
    inside = (~out).astype(float)
    switch = np.abs(np.diff(np.concatenate([[0.0], inside]))) * COST   # entrada inicial, salidas y reentradas
    hx = np.where(out, rf.to_numpy(), r) - switch
    holder_exit = metrics(hx, rf, inside, k_s)

    sig_groups = by_group(tr, "Trade_Signal", [1.0, -1.0])
    regime = by_group(tr, "below_ma50", [True, False])
    eval1 = {s: dict(mean=float(tr.loc[tr["Sample"] == s, "Strategy_Net_Return"].mean()),
                     win=float((tr.loc[tr["Sample"] == s, "Strategy_Net_Return"] > 0).mean()),
                     mean_t1=float(tr.loc[tr["Sample"] == s, "net"].mean()),
                     win_t1=float((tr.loc[tr["Sample"] == s, "net"] > 0).mean()),
                     p_t1=float(stats.ttest_1samp(tr.loc[tr["Sample"] == s, "net"], 0).pvalue)) for s in ["Train", "Test"]}
    up_test = next(g for g in sig_groups if g["sample"] == "Test" and g["key"] == 1.0)

    result = dict(
        period=dict(test_start=str(te.index[0].date()), test_end=str(te.index[-1].date()), sessions=len(te)),
        rf_source=rf_source, rf_mean_annual=float(rf.mean() * 252),
        events=event_oos(m, tr),
        all_days=all_days_check(m, tr),
        eval1=eval1,
        table=table,
        yearly=yearly,
        holder_exit=holder_exit,
        by_signal=sig_groups,
        regime_ma50=regime,
        breakeven_long=up_test["mean_gross"],   # costo ida y vuelta que deja en cero el retorno medio de las señales +1 en Test
        dates=[d.strftime("%Y-%m-%d") for d in te.index],
        curves=curves,
    )

    def rnd(x):
        if isinstance(x, float):
            return round(x, 6)
        if isinstance(x, dict):
            return {k: rnd(v) for k, v in x.items()}
        if isinstance(x, list):
            return [rnd(v) for v in x]
        return x

    result = rnd(result)
    (DATA / "cliente.js").write_text("window.BW_CLIENTE = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                     encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("dates", "curves")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(download="--descargar" in sys.argv)
