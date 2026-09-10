"""Auditoría independiente de archivos congelados; no descarga ni cambia CSV.

Ejecutar: python -m src.audit_final. Escribe solamente evidencia en docs/.
Las identidades se reconstruyen con sumas escalares, no con los indicadores
del pipeline. Las funciones productivas solo se usan en pruebas de perturbación.
"""

import hashlib
import json
import math
import statistics
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-9


def read_csv(name):
    frame = pd.read_csv(ROOT / name, index_col="Date", parse_dates=["Date"])
    assert not frame.empty and frame.index.is_unique and frame.index.is_monotonic_increasing, name
    return frame


def compare(actual, expected):
    np.testing.assert_allclose(actual, expected, rtol=0, atol=TOLERANCE, equal_nan=True)
    difference = np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float)
    return float(np.nanmax(np.abs(difference)))


def fit_train(x, y):
    # Forma escalar de MCO con intercepto, independiente de np.linalg.lstsq.
    x, y = list(x), list(y)
    mx, my = statistics.mean(x), statistics.mean(y)
    beta = math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / math.fsum((a - mx) ** 2 for a in x)
    alpha = my - beta * mx
    sigma = statistics.stdev(b - alpha - beta * a for a, b in zip(x, y))
    return alpha, beta, sigma


def audit_ioc():
    raw = read_csv("data/raw/tsla_wikipedia_pageviews.csv")
    saved = read_csv("data/processed/attention_wave.csv")
    assert raw.index.equals(saved.index)
    assert raw.index.equals(pd.date_range(raw.index.min(), raw.index.max(), name="Date"))
    compare(saved.Pageviews, raw.Pageviews)
    logs = [math.log1p(value) for value in raw.Pageviews]
    rows = []
    for i, day in enumerate(raw.index):
        past = logs[i - 60:i] if i >= 60 else []  # Excluye explícitamente el día i.
        mean = statistics.mean(past) if past else math.nan
        sigma = statistics.stdev(past) if past else math.nan
        z = (logs[i] - mean) / sigma if sigma > 0 else math.nan
        iaa = max(z, 0)
        rows.append([logs[i], mean, sigma, z, iaa, 100 * math.tanh(iaa / 2)])
    calculated = pd.DataFrame(rows, index=raw.index,
                              columns=["Log_Pageviews", "Media_60", "Sigma_60", "Attention_Z", "IAA", "IOC"])
    calculated["IOC_Velocity"] = calculated.IOC.diff()
    calculated["IOC_Acceleration"] = calculated.IOC_Velocity.diff()
    errors = {column: compare(saved[column], calculated[column]) for column in saved.columns if column != "Pageviews"}
    signals = read_csv("data/processed/behavioral_signals.csv")
    usable = calculated.loc[signals.index]
    dates = [("Normal", usable.index[usable.IOC.le(10)][0]),
             ("Extremo", usable.index[usable.IOC.ge(signals.IOC_Extreme_Threshold.iloc[0])][0]),
             ("Máximo", calculated.IOC.idxmax()),
             ("Evento", signals.index[signals.Signal.ne(0)][0]),
             ("Cerca del tooltip", pd.Timestamp("2021-11-05"))]
    cases = []
    for label, day in dates:
        cases.append(dict(Caso=label, Date=str(day.date()), Pageviews=int(raw.loc[day, "Pageviews"]),
                          Inicio_Referencia=str((day - pd.Timedelta(days=60)).date()),
                          Fin_Referencia=str((day - pd.Timedelta(days=1)).date()),
                          **calculated.loc[day, ["Log_Pageviews", "Media_60", "Sigma_60", "Attention_Z", "IAA", "IOC"]].to_dict(),
                          IOC_CSV=float(saved.loc[day, "IOC"])))
    return {"observations": len(saved), "max_errors": errors, "cases": cases}


def audit_models():
    market = read_csv("data/processed/market_model.csv")
    raw = read_csv("data/raw/market_data.csv")
    compare(market[["TSLA_Return", "VOO_Return"]], raw.loc[market.index, ["TSLA_Return", "VOO_Return"]])
    train = market.loc[market.Sample.eq("Train")]
    alpha, beta, sigma = fit_train(train.VOO_Return, train.TSLA_Return)
    expected = np.array([alpha + beta * value for value in market.VOO_Return])
    ar = market.TSLA_Return.to_numpy() - expected
    car = np.array([math.fsum(ar[i - 4:i + 1]) if i >= 4 else math.nan for i in range(len(ar))])
    errors = {column: compare(market[column], value) for column, value in
              [("Expected_Return", expected), ("AR", ar), ("CAR_5", car), ("CAR_Z", car / (sigma * math.sqrt(5)))]}
    irx = read_csv("data/raw/irx.csv").IRX_Annual_Percent.dropna()
    # Buscar la última tasa cuya fecha no excede la sesión; nunca una tasa futura.
    rate_dates = [irx.index[irx.index <= day][-1] for day in market.index]
    rf = np.array([irx.loc[day] / 100 / 252 for day in rate_dates])
    capm = read_csv("data/processed/capm_model.csv")
    compare(capm.RF_Daily, rf)
    assert list(pd.to_datetime(capm.RF_Observation_Date)) == rate_dates
    n = len(train)
    a_c, b_c, s_c = fit_train(market.VOO_Return.iloc[:n] - rf[:n], market.TSLA_Return.iloc[:n] - rf[:n])
    expected_c = rf + a_c + b_c * (market.VOO_Return.to_numpy() - rf)
    compare(capm.Alpha_CAPM, a_c)
    compare(capm.Beta_CAPM, b_c)
    errors["CAPM_Expected_Return"] = compare(capm.CAPM_Expected_Return, expected_c)
    errors["CAPM_AR"] = compare(capm.CAPM_AR, market.TSLA_Return - expected_c)
    rows = []
    for day in ["2017-04-07", "2021-11-03", "2021-11-05", "2021-11-09", "2023-11-03"]:
        i = market.index.get_loc(day)
        rows.append(dict(Date=day, VOO_Return=float(market.VOO_Return.iloc[i]),
                         TSLA_Return=float(market.TSLA_Return.iloc[i]), Expected_Return=expected[i],
                         AR=ar[i], CAR_5=car[i], CAR_Z=car[i] / (sigma * math.sqrt(5))))
    return {"alpha": alpha, "beta": beta, "sigma_epsilon": sigma,
            "capm_alpha": a_c, "capm_beta": b_c, "capm_sigma": s_c, "max_errors": errors, "cases": rows}


def audit_signals():
    signals = read_csv("data/processed/behavioral_signals.csv")
    market = read_csv("data/processed/market_model.csv")
    assert signals.index.equals(market.index)
    assert signals.Sample.equals(market.Sample)
    attention = read_csv("data/processed/attention_wave.csv")
    for column in ["Pageviews", "Attention_Z", "IOC", "IOC_Velocity"]:
        compare(signals[column], attention.loc[signals.index, column])
    for column in ["TSLA_Return", "VOO_Return", "AR", "CAR_5", "CAR_Z"]:
        compare(signals[column], market[column])
    n = int(len(market) * .70)
    assert market.Sample.tolist() == ["Train"] * n + ["Test"] * (len(market) - n)
    assert str(market.index[n].date()) == "2023-11-03"
    assert str(market.index[0].date()) == "2017-04-03" and str(market.index[-1].date()) == "2026-09-08"
    assert signals.Signal.isin([-1, 0, 1]).all()
    assert pd.isna(signals.Trade_Signal.iloc[0])  # Ausencia de sesión anterior; no es una orden.
    assert signals.Trade_Signal.iloc[1:].isin([-1, 0, 1]).all()
    train = signals.iloc[:n]
    thresholds = dict(IOC_Extreme_Threshold=float(np.quantile(train.IOC.dropna(), .9)),
                      CAR_Positive_Threshold=float(np.quantile(train.CAR_Z.dropna(), .9)),
                      CAR_Negative_Threshold=float(np.quantile(train.CAR_Z.dropna(), .1)))
    for column, value in thresholds.items():
        compare(signals[column], value)
    extreme, positive, negative = thresholds.values()
    prev, previous_signal = math.nan, math.nan
    for _, row in signals.iterrows():
        exhausted = row.IOC < prev and prev >= extreme
        up, down = row.CAR_Z >= positive, row.CAR_Z <= negative
        assert not (up and down)
        signal = -1 if exhausted and up else 1 if exhausted and down else 0
        assert row.Signal == signal
        assert row.Wave_Extreme == (row.IOC >= extreme) and row.Wave_Exhaustion == exhausted
        assert row.Positive_Overreaction == up and row.Negative_Overreaction == down
        compare(row.Trade_Signal, previous_signal) if not math.isnan(previous_signal) else None
        previous_signal, prev = signal, row.IOC
    cases = []
    for day in ["2021-10-29", "2021-11-03", "2021-11-09", "2021-11-10"]:
        i = signals.index.get_loc(day)
        row = signals.iloc[i]
        cases.append(dict(Date=day, IOC_Prev=float(signals.IOC.iloc[i - 1]), IOC=float(row.IOC),
                          CAR_Z=float(row.CAR_Z), Signal=int(row.Signal),
                          Entry_Date=str(signals.index[i + 1].date()), Trade_Signal=int(signals.Trade_Signal.iloc[i + 1])))
    events = signals.loc[signals.Signal.ne(0)]
    return {"sessions": len(signals), "events": len(events), "train_events": int(events.Sample.eq("Train").sum()),
            "test_events": int(events.Sample.eq("Test").sum()), "positive": int(events.Signal.eq(1).sum()),
            "negative": int(events.Signal.eq(-1).sum()), "thresholds": thresholds, "cases": cases,
            "initial_trade_signal": "NaN: shift(1), no existe sesión previa"}


def audit_backtest():
    market = read_csv("data/processed/market_model.csv")
    capm = read_csv("data/processed/capm_model.csv")
    signals = read_csv("data/processed/behavioral_signals.csv")
    events = read_csv("data/processed/backtest_events.csv")
    assert events.index.equals(signals.index[signals.Trade_Signal.isin([-1, 1])])
    assert events.Status.eq("Completed").all() and not events.Crosses_Sample_Boundary.any()
    computed = []
    for day, row in events.iterrows():
        i = market.index.get_loc(day)
        dates = market.index[i:i + 5]
        assert len(dates) == 5 and str(dates[-1].date()) == row.Exit_Date
        assert row.Signal_Date == str(market.index[i - 1].date())
        assert row.Trade_Signal == signals.Signal.iloc[i - 1]
        assert row.Sample == market.Sample.iloc[i] == row.Signal_Sample
        compare(row.Signal_IOC, signals.IOC.iloc[i - 1])
        compare(row.Signal_CAR_Z, signals.CAR_Z.iloc[i - 1])
        compare(row.IOC, signals.IOC.iloc[i])
        compare(row.CAR_Z, signals.CAR_Z.iloc[i])
        returns = market.TSLA_Return.iloc[i:i + 5].tolist()
        forward = math.prod(1 + r for r in returns) - 1
        normal = math.prod(1 + r for r in market.Expected_Return.iloc[i:i + 5]) - 1
        normal_c = math.prod(1 + r for r in capm.CAPM_Expected_Return.iloc[i:i + 5]) - 1
        direction = row.Trade_Signal
        gross = direction * forward
        values = dict(Forward_Return_5D=forward, Strategy_Gross_Return=gross, Transaction_Cost=.002,
                      Strategy_Net_Return=gross - .002, MarketModel_Normal_5D=normal, CAPM_Normal_5D=normal_c,
                      Abnormal_Strategy_MarketModel=gross - .002 - direction * normal,
                      Abnormal_Strategy_CAPM=gross - .002 - direction * normal_c)
        for column, value in values.items():
            compare(row[column], value)
        computed.append(dict(Date=str(day.date()), Sample=row.Sample, Trade_Signal=direction,
                             Exit_Date=row.Exit_Date, Returns=returns, **values))
    all_rows = pd.DataFrame(computed)
    summary = pd.read_csv(ROOT / "results/backtest_summary.csv", index_col="Sample")
    for sample in ["Train", "Test", "Total"]:
        group = all_rows if sample == "Total" else all_rows.loc[all_rows.Sample.eq(sample)]
        net = group.Strategy_Net_Return.tolist()
        metrics = dict(Trades=len(net), Win_Rate_Pct=100 * sum(v > 0 for v in net) / len(net),
                       Mean_Gross_Return=statistics.mean(group.Strategy_Gross_Return),
                       Mean_Net_Return=statistics.mean(net), Median_Net_Return=statistics.median(net),
                       Std_Net_Return=statistics.stdev(net), Cumulative_Event_Net_Return=math.prod(1 + v for v in net) - 1,
                       Mean_Abnormal_MarketModel=statistics.mean(group.Abnormal_Strategy_MarketModel),
                       Mean_Abnormal_CAPM=statistics.mean(group.Abnormal_Strategy_CAPM))
        for key, value in metrics.items():
            compare(summary.loc[sample, key], value)
    tests = {}
    test = all_rows.loc[all_rows.Sample.eq("Test")]
    for label, column in [("Net", "Strategy_Net_Return"), ("MarketModel", "Abnormal_Strategy_MarketModel"),
                          ("CAPM", "Abnormal_Strategy_CAPM")]:
        values = test[column].tolist()
        t = statistics.mean(values) / (statistics.stdev(values) / math.sqrt(len(values)))
        p = float(2 * student_t.sf(abs(t), len(values) - 1))
        compare(summary.loc["Test", label + "_T_Statistic"], t)
        compare(summary.loc["Test", label + "_P_Value"], p)
        tests[label] = dict(t=t, p=p)
    cases = [next(row for row in computed if row["Trade_Signal"] == 1),
             next(row for row in computed if row["Trade_Signal"] == -1),
             next(row for row in computed if row["Sample"] == "Test")]
    return {"events_checked": len(events), "cases": cases, "test_statistics": tests,
            "summary": json.loads(summary.reset_index().to_json(orient="records", double_precision=15))}


def audit_test_isolation():
    from src.abnormal_returns import calculate_abnormal_returns
    from src.capm_model import calculate_capm
    from src.signals import calculate_signals
    from src.wikimedia_attention import calculate_attention_wave

    market = read_csv("data/processed/market_model.csv")
    attention = read_csv("data/processed/attention_wave.csv")
    irx = read_csv("data/raw/irx.csv")
    altered = market.copy()
    test = altered.Sample.eq("Test")
    altered.loc[test, ["TSLA_Return", "VOO_Return", "CAR_Z"]] = [100, -50, 10000]
    original_mm, params = calculate_abnormal_returns(market)
    changed_mm, new_params = calculate_abnormal_returns(altered)
    assert params == new_params
    pd.testing.assert_frame_equal(original_mm.loc[~test], changed_mm.loc[~test])
    modified_irx = irx.copy()
    modified_irx.loc[modified_irx.index >= market.index[test][0], "IRX_Annual_Percent"] = 500
    original_c, params = calculate_capm(market, irx)
    changed_c, new_params = calculate_capm(altered, modified_irx)
    assert params == new_params
    pd.testing.assert_frame_equal(original_c.loc[~test], changed_c.loc[~test])
    changed_attention = attention.copy()
    changed_attention.loc[changed_attention.index >= market.index[test][0], "IOC"] = 100
    original_s, thresholds = calculate_signals(market, attention)
    changed_s, new_thresholds = calculate_signals(altered, changed_attention)
    assert thresholds == new_thresholds
    pd.testing.assert_frame_equal(original_s.loc[~test], changed_s.loc[~test])
    raw = read_csv("data/raw/tsla_wikipedia_pageviews.csv")
    changed_raw = raw.copy()
    cut = pd.Timestamp("2021-11-05")
    changed_raw.loc[changed_raw.index > cut, "Pageviews"] = 99999999
    original_a = calculate_attention_wave(raw)
    changed_a = calculate_attention_wave(changed_raw)
    pd.testing.assert_frame_equal(original_a.loc[:cut], changed_a.loc[:cut])
    return {"market_parameters_and_train": True, "capm_parameters_and_train": True,
            "thresholds_and_train_signals": True, "future_pageviews_do_not_change_past_ioc": True}


def audit_web():
    from src.export_web_data import build_web_data
    data = {name: json.loads((ROOT / f"app/data/{name}.json").read_text(encoding="utf-8"))
            for name in ["overview", "series", "events"]}
    assert data == build_web_data()
    snapshot = (ROOT / "app/data/snapshot.js").read_text(encoding="utf-8")
    assert json.loads(snapshot.removeprefix("window.BEHAVIORAL_WAVE_DATA = ").removesuffix(";\n")) == data
    signals = read_csv("data/processed/behavioral_signals.csv")
    market = read_csv("data/processed/market_model.csv")
    exported = data["events"]["signals"]
    assert [row["Date"] for row in exported] == [str(day.date()) for day in signals.index[signals.Signal.ne(0)]]
    for row in exported:
        day = pd.Timestamp(row["Date"])
        i = signals.index.get_loc(day)
        for column in ["IOC", "CAR_Z", "Signal", "Trade_Signal"]:
            compare(row[column], signals.loc[day, column])
        assert row["Sample"] == signals.Sample.loc[day]
        assert row["Entry_Date"] == str(signals.index[i + 1].date())
        assert row["Entry_Trade_Signal"] == row["Signal"]
        compare(row["TSLA_Price"], market.TSLA_Price.loc[day])
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert 'hovermode: "closest"' in js and 'hovermode: "x unified"' not in js
    return {"all_json_equal_csv_export": True, "snapshot_identical": True, "event_dates_checked": len(exported),
            "tooltip_records": [row for row in exported if row["Date"] in ["2021-11-03", "2021-11-09"]]}


def audit_hashes():
    manifest = json.loads((ROOT / "docs/audit_input_hashes.json").read_text(encoding="utf-8"))
    unchanged = []
    for path, expected in manifest.items():
        if path == "config.py":  # Única excepción: fija el corte ya solicitado, antes END_DATE=None.
            continue
        assert hashlib.sha256((ROOT / path.replace("\\", "/")).read_bytes()).hexdigest() == expected, path
        unchanged.append(path)
    return {"unchanged_files": unchanged, "exception": "config.py: END_DATE fija 2026-09-08; no cambia resultados"}


def run_audit():
    return {"tolerance_absolute": TOLERANCE, "ioc": audit_ioc(), "models": audit_models(),
            "signals": audit_signals(), "backtest": audit_backtest(), "test_isolation": audit_test_isolation(),
            "web": audit_web(), "hashes": audit_hashes()}


if __name__ == "__main__":
    evidence = run_audit()
    path = ROOT / "docs/audit_calculations.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    print(f"Auditoría independiente aprobada. Evidencia: {path}")
