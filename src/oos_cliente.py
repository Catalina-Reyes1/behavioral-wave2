"""Trabajo de Aplicación II: evaluación fuera de muestra del indicador para la pestaña "Para el cliente".

Lee solo los datos ya exportados en app/data (series.json y events.json) y escribe
app/data/cliente.js. La curva de capital la dibuja app/cliente.js con data/snapshot.js. No recalcula umbrales ni toca el estudio principal.

Diseño
- Activo: NVDA. Horizonte: 5 sesiones (el mismo de la Evaluación 1).
- Período fuera de muestra: Test (15/05/2023 a 08/09/2026). Umbrales congelados en Train.
- Ventana recursiva (expansiva): en cada fecha t solo se usan datos conocidos en t.
- R2oos: pronóstico del modelo y = a + b * señal (estimado con los eventos ya cerrados en t)
  contra la media histórica recursiva del retorno a 5 sesiones de NVDA.
- MDA: acierto de la dirección que da la señal (+1 sube, -1 baja).
- Anatolyev y Gerko (2005): prueba de rentabilidad en exceso, una cola.
- Chequeo complementario diario: r(t+1) = a + b * IOC(t), ventana recursiva.

Uso: python -m src.oos_cliente
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
TEST_START = pd.Timestamp("2023-05-15")
COST = 0.001  # 0,10% por lado


def anatolyev_gerko(direction, y):
    """Estadístico EP de Anatolyev y Gerko (2005) y valor p de una cola."""
    d = np.asarray(direction, float)
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


def load():
    s = json.loads((DATA / "series.json").read_text(encoding="utf-8"))
    ev = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    m = pd.DataFrame(s["market"])
    m["Date"] = pd.to_datetime(m["Date"])
    m = m.set_index("Date").sort_index()
    m["r"] = m["NVDA_Price"].pct_change()
    m["y5"] = m["NVDA_Price"].shift(-5) / m["NVDA_Price"] - 1  # conocido recién en t+5
    tr = pd.DataFrame(ev["trades"])
    for c in ["Date", "Signal_Date", "Exit_Date"]:
        tr[c] = pd.to_datetime(tr[c])
    return m, tr


def event_oos(m, tr):
    idx = m.index
    test = tr[tr["Sample"] == "Test"].sort_values("Signal_Date")
    rows = []
    for _, e in test.iterrows():
        t = e["Signal_Date"]
        pos = idx.get_loc(t)
        past = tr[tr["Exit_Date"] <= t]  # solo eventos ya cerrados en t
        X = np.column_stack([np.ones(len(past)), past["Trade_Signal"]])
        a, b = np.linalg.lstsq(X, past["Forward_Return_5D"].to_numpy(), rcond=None)[0]
        bench = m["y5"].iloc[: pos - 5 + 1].mean()  # media histórica recursiva
        rows.append(dict(date=t, direction=e["Trade_Signal"], y=e["Forward_Return_5D"],
                         forecast=a + b * e["Trade_Signal"], bench=bench))
    o = pd.DataFrame(rows)
    ecm_m = float(((o.y - o.forecast) ** 2).mean())
    ecm_b = float(((o.y - o.bench) ** 2).mean())
    hits = int((np.sign(o.direction) == np.sign(o.y)).sum())
    ep, p = anatolyev_gerko(o.direction, o.y)
    return dict(
        n=len(o), first=str(o.date.min().date()), last=str(o.date.max().date()),
        n_long=int((o.direction > 0).sum()), n_short=int((o.direction < 0).sum()),
        ecm_model=ecm_m, ecm_bench=ecm_b, r2oos=1 - ecm_m / ecm_b,
        forecast_always_up=bool((o.forecast > 0).all()),
        mda=hits / len(o), hits=hits, up_share=float((o.y > 0).mean()),
        mda_binom_p=float(stats.binomtest(hits, len(o), 0.5, alternative="greater").pvalue),
        ag_stat=ep, ag_p=p,
        gross_mean_test=float(tr.loc[tr["Sample"] == "Test", "Strategy_Gross_Return"].mean()),
        train_net_mean=float(tr.loc[tr["Sample"] == "Train", "Strategy_Net_Return"].mean()),
        test_net_mean=float(tr.loc[tr["Sample"] == "Test", "Strategy_Net_Return"].mean()),
    )


def daily_check(m):
    df = m[["IOC", "NVDA_Price"]].copy()
    df["y"] = df["NVDA_Price"].shift(-1) / df["NVDA_Price"] - 1
    idx = df.index
    rows = []
    for t in idx[idx >= TEST_START]:
        pos = idx.get_loc(t)
        if pd.isna(df["y"].iloc[pos]):
            continue
        past = df.iloc[:pos].dropna(subset=["IOC", "y"])  # y(s) conocido en s+1 <= t
        X = np.column_stack([np.ones(len(past)), past["IOC"]])
        a, b = np.linalg.lstsq(X, past["y"].to_numpy(), rcond=None)[0]
        rows.append((df["y"].iloc[pos], a + b * df["IOC"].iloc[pos], past["y"].mean()))
    o = pd.DataFrame(rows, columns=["y", "f", "bench"])
    return dict(
        n=len(o),
        r2oos=float(1 - ((o.y - o.f) ** 2).sum() / ((o.y - o.bench) ** 2).sum()),
        mda=float((np.sign(o.f) == np.sign(o.y)).mean()),
        up_share=float((o.y > 0).mean()),
        share_forecast_up=float((o.f > 0).mean()),
    )


def backtest(m, tr, mode):
    te = m[m.index >= TEST_START]
    pos = pd.Series(0.0, index=te.index)
    cost = pd.Series(0.0, index=te.index)
    n, busy = 0, None
    for _, e in tr[tr["Sample"] == "Test"].sort_values("Date").iterrows():
        if busy is not None and e["Date"] <= busy:
            continue  # ya hay una operación abierta: no se apilan posiciones
        d = e["Trade_Signal"]
        if mode == "solo_compras" and d < 0:
            continue
        days = te.loc[e["Date"]:e["Exit_Date"]].index
        pos.loc[days] = d
        cost.loc[days[0]] += COST
        cost.loc[days[-1]] += COST
        n += 1
        busy = e["Exit_Date"]
    if mode == "buy_and_hold":
        pos[:] = 1.0
        cost[:] = 0.0
        n = 1
    ret = pos * te["r"] - cost
    return ret, pos, n


def metrics(ret, pos, n):
    eq = (1 + ret).cumprod()
    T = len(ret)
    return dict(
        total=float(eq.iloc[-1] - 1),
        annual=float(eq.iloc[-1] ** (252 / T) - 1),
        vol=float(ret.std() * np.sqrt(252)),
        sharpe=float(ret.mean() / ret.std() * np.sqrt(252)),
        max_dd=float((eq / eq.cummax() - 1).min()),
        invested=float((pos != 0).mean()),
        trades=int(n),
    )


def by_signal(tr):
    out = []
    for sample in ["Train", "Test"]:
        for d in [1, -1]:
            x = tr[(tr["Sample"] == sample) & (tr["Trade_Signal"] == d)]["Strategy_Net_Return"]
            out.append(dict(sample=sample, direction=d, n=len(x), win=float((x > 0).mean()),
                            mean=float(x.mean()), p=float(stats.ttest_1samp(x, 0).pvalue)))
    return out


def main():
    m, tr = load()
    te = m[m.index >= TEST_START]
    table, yearly = {}, {}
    for mode in ["buy_and_hold", "ioc", "solo_compras"]:
        ret, pos, n = backtest(m, tr, mode)
        table[mode] = metrics(ret, pos, n)
        yearly[mode] = {str(y): float((1 + g).prod() - 1) for y, g in ret.groupby(ret.index.year)}
    # Usuario que mantiene NVDA y sale del mercado ante cada señal -1 (alerta de salida).
    ret_bh, _, _ = backtest(m, tr, "buy_and_hold")
    ret_short, pos_short, n_short = backtest(m, tr, "ioc")
    out_days = pos_short < 0
    alt = ret_bh.where(~out_days, 0.0)
    exits = int((out_days & ~out_days.shift(1, fill_value=False)).sum())
    holder_exit = metrics(alt - (out_days.astype(float).diff().abs().fillna(0) * COST), (~out_days).astype(float), exits)

    result = dict(
        period=dict(test_start=str(te.index[0].date()), test_end=str(te.index[-1].date()), sessions=len(te)),
        events=event_oos(m, tr),
        daily=daily_check(m),
        table=table,
        yearly=yearly,
        holder_exit=holder_exit,
        by_signal=by_signal(tr),
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
    # La curva de capital se dibuja en el navegador con los mismos precios y operaciones (data/snapshot.js).
    (DATA / "cliente.js").write_text("window.BW_CLIENTE = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
