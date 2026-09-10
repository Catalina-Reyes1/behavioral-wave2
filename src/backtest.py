"""Evaluación fija de eventos, sin agregación de posiciones ni optimización."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


HOLDING_SESSIONS = 5
ENTRY_COST = 0.001
EXIT_COST = 0.001
RETURN_COLUMNS = ["Forward_Return_5D", "Strategy_Gross_Return", "Strategy_Net_Return",
                  "MarketModel_Normal_5D", "CAPM_Normal_5D",
                  "Abnormal_Strategy_MarketModel", "Abnormal_Strategy_CAPM"]


def calculate_backtest(signals: pd.DataFrame, capm: pd.DataFrame) -> pd.DataFrame:
    for name, frame, required in [
        ("Señales", signals, ["Sample", "Trade_Signal", "NVDA_Return", "VOO_Return", "AR", "IOC", "CAR_Z"]),
        ("CAPM", capm, ["Sample", "NVDA_Return", "VOO_Return", "Expected_Return", "CAPM_Expected_Return"]),
    ]:
        if frame.empty or not set(required).issubset(frame):
            raise ValueError(f"{name}: faltan datos o columnas requeridas.")
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates or frame.index.hasnans:
            raise ValueError(f"{name}: se requieren fechas válidas y únicas.")
    signals, capm = signals.sort_index(), capm.sort_index()
    if not signals.index.equals(capm.index) or not signals.Sample.equals(capm.Sample):
        raise ValueError("Señales y CAPM deben conservar exactamente el calendario y Sample del mercado.")
    for column in ["NVDA_Return", "VOO_Return"]:
        if not np.allclose(signals[column], capm[column], equal_nan=True, rtol=1e-10, atol=1e-12):
            raise ValueError(f"Los archivos usan versiones diferentes de {column}; regenere el flujo completo.")
    if not np.allclose(signals.NVDA_Return - signals.AR, capm.Expected_Return, equal_nan=True, atol=1e-12):
        raise ValueError("El retorno normal del Market Model no coincide con el AR de señales.")
    if not signals.Trade_Signal.dropna().isin([-1, 0, 1]).all():
        raise ValueError("Trade_Signal debe ser -1, 0, +1 o NaN inicial.")

    positions = np.flatnonzero(signals.Trade_Signal.isin([-1, 1]).to_numpy())
    events = signals.iloc[positions][["Sample", "Trade_Signal", "IOC", "CAR_Z"]].copy()
    events["Signal_Date"] = pd.NaT
    events["Signal_Sample"] = pd.Series(index=events.index, dtype="str")
    events["Signal_IOC"] = np.nan
    events["Signal_CAR_Z"] = np.nan
    events["Exit_Date"] = pd.NaT
    events["Crosses_Sample_Boundary"] = False
    events["Status"] = "Incomplete_Horizon"
    events["Transaction_Cost"] = ENTRY_COST + EXIT_COST
    for column in RETURN_COLUMNS:
        events[column] = np.nan
    for i in positions:
        date = signals.index[i]
        if i == 0:
            raise ValueError("Una entrada en la primera fila no tiene fecha de señal previa verificable.")
        source = signals.iloc[i - 1]
        events.loc[date, ["Signal_Date", "Signal_Sample", "Signal_IOC", "Signal_CAR_Z"]] = [signals.index[i - 1], source.Sample, source.IOC, source.CAR_Z]
        window = capm.iloc[i:i + HOLDING_SESSIONS]
        if len(window) < HOLDING_SESSIONS:
            continue
        events.loc[date, "Exit_Date"] = window.index[-1]
        events.loc[date, "Crosses_Sample_Boundary"] = source.Sample != signals.loc[date, "Sample"] or window.Sample.ne(signals.loc[date, "Sample"]).any()
        values = window[["NVDA_Return", "Expected_Return", "CAPM_Expected_Return"]].to_numpy()
        if not np.isfinite(values).all():
            events.loc[date, "Status"] = "Missing_Returns"
            continue
        # Trade_Signal ya corresponde a entrada: incluir i,...,i+4, sin otro shift.
        forward, normal_market, normal_capm = np.prod(1 + values, axis=0) - 1
        direction = signals.loc[date, "Trade_Signal"]
        gross = direction * forward
        net = gross - ENTRY_COST - EXIT_COST
        events.loc[date, RETURN_COLUMNS] = [forward, gross, net, normal_market, normal_capm,
                                           net - direction * normal_market, net - direction * normal_capm]
        events.loc[date, "Status"] = "Completed"
    return events.rename_axis("Date")


def _t_test(values: pd.Series) -> tuple[float, float]:
    if len(values) < 2 or values.std(ddof=1) == 0:
        return np.nan, np.nan
    test = stats.ttest_1samp(values.to_numpy(), popmean=0, alternative="two-sided")
    return float(test.statistic), float(test.pvalue)


def summarize_backtest(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sample in ["Train", "Test", "Total"]:
        group = events if sample == "Total" else events.loc[events.Sample.eq(sample)]
        completed = group.loc[group.Status.eq("Completed")]
        # Para separar muestras, un evento debe originarse y terminar en la misma.
        valid = completed if sample == "Total" else completed.loc[~completed.Crosses_Sample_Boundary]
        net = valid.Strategy_Net_Return
        row = {"Sample": sample, "Trades": len(valid), "Candidate_Events": len(group),
               "Incomplete_Events": int(group.Status.ne("Completed").sum()),
               "Boundary_Events": int(completed.Crosses_Sample_Boundary.sum()),
               "Win_Rate_Pct": 100 * net.gt(0).mean() if len(net) else np.nan,
               "Mean_Gross_Return": valid.Strategy_Gross_Return.mean(),
               "Mean_Net_Return": net.mean(), "Median_Net_Return": net.median(),
               "Std_Net_Return": net.std(ddof=1),
               # Compuesto DESCRIPTIVO de eventos; no curva de capital operable.
               "Cumulative_Event_Net_Return": float(np.prod(1 + net) - 1) if len(net) else np.nan,
               "Mean_Abnormal_MarketModel": valid.Abnormal_Strategy_MarketModel.mean(),
               "Mean_Abnormal_CAPM": valid.Abnormal_Strategy_CAPM.mean()}
        for name, column in [("Net", "Strategy_Net_Return"), ("MarketModel", "Abnormal_Strategy_MarketModel"), ("CAPM", "Abnormal_Strategy_CAPM")]:
            t_stat, p_value = _t_test(valid[column]) if sample == "Test" else (np.nan, np.nan)
            row[f"{name}_T_Statistic"] = t_stat
            row[f"{name}_P_Value"] = p_value
        rows.append(row)
    return pd.DataFrame(rows).set_index("Sample")


def run_backtest(signals_path="data/processed/behavioral_signals.csv", capm_path="data/processed/capm_model.csv",
                 events_path="data/processed/backtest_events.csv", summary_path="results/backtest_summary.csv") -> tuple[pd.DataFrame, pd.DataFrame]:
    signals = pd.read_csv(signals_path, index_col="Date", parse_dates=["Date"])
    capm = pd.read_csv(capm_path, index_col="Date", parse_dates=["Date"])
    events = calculate_backtest(signals, capm)
    summary = summarize_backtest(events)
    for frame, filename in [(events, events_path), (summary, summary_path)]:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=True, date_format="%Y-%m-%d")
    print("\nBEHAVIORAL WAVE BACKTEST")
    print("Horizonte: 5 sesiones | Costo entrada: 0.10% | Salida: 0.10%")
    print("Retornos en decimales; Win_Rate_Pct en porcentaje. Ganadora: retorno neto > 0.")
    print(summary.T.to_string(float_format=lambda value: f"{value:.6f}"))
    print("Acumulado compuesto de eventos independientes: no representa una cartera con solapamientos.")
    print("Tests t bilaterales nominales: el solapamiento puede invalidar el supuesto de independencia.")
    print("Cruces Train/Test se conservan en Total, pero no en las estadísticas separadas.")
    print("No se incluyen costos de préstamo de cortos. Retornos diarios cierre a cierre: ejecución aproximada.")
    print(f"Archivos creados: {events_path} | {summary_path}")
    return events, summary


if __name__ == "__main__":
    run_backtest()
