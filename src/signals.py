"""Eventos de agotamiento de atención y posible reversión de precio."""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd


MARKET_COLUMNS = ["Sample", "TSLA_Return", "VOO_Return", "AR", "CAR_5", "CAR_Z"]
ATTENTION_COLUMNS = ["Pageviews", "Attention_Z", "IOC", "IOC_Velocity"]


def _validate_frame(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{name}: faltan columnas {sorted(missing)}.")
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{name}: se requiere un índice Date de tipo datetime y datos no vacíos.")
    if frame.index.has_duplicates or frame.index.hasnans or not frame.index.equals(frame.index.normalize()):
        raise ValueError(f"{name}: las fechas deben ser diarias, válidas y únicas.")
    for column in columns:
        if column != "Sample":
            if not pd.api.types.is_numeric_dtype(frame[column]) or not np.isfinite(frame[column].dropna()).all():
                raise ValueError(f"{name}: {column} debe contener números finitos o NaN.")


def calculate_signals(market: pd.DataFrame, attention: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Conserva el calendario y Sample del mercado; calibra únicamente en Train."""
    _validate_frame(market, MARKET_COLUMNS, "Mercado")
    _validate_frame(attention, ATTENTION_COLUMNS, "Atención")
    market = market.sort_index()
    if not market["Sample"].isin(["Train", "Test"]).all():
        raise ValueError("Sample debe contener únicamente Train y Test.")
    train_dates = market.index[market["Sample"].eq("Train")]
    test_dates = market.index[market["Sample"].eq("Test")]
    if train_dates.empty or test_dates.empty or train_dates.max() >= test_dates.min():
        raise ValueError("Se requiere Train seguido cronológicamente de Test, sin reasignar Sample.")
    if not attention["IOC"].dropna().between(0, 100).all():
        raise ValueError("IOC debe estar entre 0 y 100.")

    # Left join: los fines de semana de Wikipedia no crean días de mercado.
    result = market[MARKET_COLUMNS].join(attention[ATTENTION_COLUMNS], how="left", validate="one_to_one")
    missing_dates = market.index.difference(attention.index)
    if len(missing_dates):
        warnings.warn(f"Se conservan {len(missing_dates)} días de mercado sin atención disponible, con NaN y sin imputación.", stacklevel=2)
    train = result.loc[result["Sample"].eq("Train")]
    if train["IOC"].dropna().empty or train["CAR_Z"].dropna().empty:
        raise ValueError("Train no tiene IOC o CAR_Z válidos para estimar los percentiles.")
    # Percentiles fijos, interpolación lineal; NaN se excluyen por variable.
    thresholds = {
        "IOC_Extreme_Threshold": float(train["IOC"].quantile(0.90, interpolation="linear")),
        "CAR_Positive_Threshold": float(train["CAR_Z"].quantile(0.90, interpolation="linear")),
        "CAR_Negative_Threshold": float(train["CAR_Z"].quantile(0.10, interpolation="linear")),
    }
    if thresholds["CAR_Negative_Threshold"] >= thresholds["CAR_Positive_Threshold"]:
        raise ValueError("Los percentiles de CAR_Z coinciden: no permiten distinguir ambas direcciones.")
    # Guardar los umbrales congelados facilita auditar Train y Test en el CSV.
    for name, value in thresholds.items():
        result[name] = value
    previous_ioc = result["IOC"].shift(1)
    result["Wave_Extreme"] = result["IOC"].ge(thresholds["IOC_Extreme_Threshold"])
    result["Wave_Exhaustion"] = result["IOC"].lt(previous_ioc) & previous_ioc.ge(thresholds["IOC_Extreme_Threshold"])
    result["Positive_Overreaction"] = result["CAR_Z"].ge(thresholds["CAR_Positive_Threshold"])
    result["Negative_Overreaction"] = result["CAR_Z"].le(thresholds["CAR_Negative_Threshold"])
    result["Signal"] = 0
    result.loc[result["Wave_Exhaustion"] & result["Positive_Overreaction"], "Signal"] = -1
    result.loc[result["Wave_Exhaustion"] & result["Negative_Overreaction"], "Signal"] = 1
    # t+1 es la siguiente fila de mercado, incluso al cruzar Train/Test.
    # La primera fila conserva NaN: no existe una señal anterior observable.
    result["Trade_Signal"] = result["Signal"].shift(1)
    return result, thresholds


def print_signals_summary(signals: pd.DataFrame, thresholds: dict) -> None:
    events = signals.loc[signals["Signal"].ne(0)]
    print("\nBEHAVIORAL SIGNALS:")
    for name, value in thresholds.items():
        print(f"{name}: {value:.8f}")
    print(f"Total de eventos (Signal != 0): {len(events)}")
    print(f"Eventos Train: {events['Sample'].eq('Train').sum()}")
    print(f"Eventos Test: {events['Sample'].eq('Test').sum()}")
    print(f"Señales alcistas (+1): {events['Signal'].eq(1).sum()}")
    print(f"Señales bajistas (-1): {events['Signal'].eq(-1).sum()}")
    print("Últimas 10 fechas con eventos:")
    print(events[["Sample", "IOC", "CAR_Z", "Signal", "Trade_Signal"]].tail(10).to_string())


def run_signals(
    market_path="data/processed/market_model.csv",
    attention_path="data/processed/attention_wave.csv",
    output_path="data/processed/behavioral_signals.csv",
) -> pd.DataFrame:
    market = pd.read_csv(market_path, index_col="Date", parse_dates=["Date"])
    attention = pd.read_csv(attention_path, index_col="Date", parse_dates=["Date"])
    signals, thresholds = calculate_signals(market, attention)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    signals.to_csv(temporary, index=True, date_format="%Y-%m-%d")
    temporary.replace(path)
    print_signals_summary(signals, thresholds)
    print(f"\nArchivo creado: {path.as_posix()}")
    return signals


if __name__ == "__main__":
    run_signals()
