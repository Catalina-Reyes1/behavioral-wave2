"""CAPM con tasa diaria aproximada de ^IRX y parámetros estimados en Train."""

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def download_irx(start, end) -> pd.DataFrame:
    # Margen previo para cubrir el primer día usando solo tasas ya observadas.
    first = pd.Timestamp(start) - pd.Timedelta(days=30)
    last = pd.Timestamp(end) + pd.Timedelta(days=1)  # end de Yahoo es exclusivo.
    raw = yf.download("^IRX", start=first.strftime("%Y-%m-%d"), end=last.strftime("%Y-%m-%d"),
                      auto_adjust=False, progress=False, timeout=30)
    if raw.empty or "Close" not in raw.columns:
        raise RuntimeError("Yahoo Finance no devolvió precios Close de ^IRX.")
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        if "^IRX" not in close:
            raise ValueError("Columnas inesperadas en la descarga de ^IRX.")
        close = close["^IRX"]
    result = close.rename("IRX_Annual_Percent").to_frame().dropna().sort_index()
    result.index = pd.DatetimeIndex(result.index).tz_localize(None).normalize()
    result.index.name = "Date"
    if result.empty or result.index.has_duplicates or not np.isfinite(result.to_numpy()).all():
        raise ValueError("La descarga de ^IRX está vacía o contiene datos inválidos.")
    return result


def calculate_capm(market: pd.DataFrame, irx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    for name, frame, columns in [("Mercado", market, ["Sample", "TSLA_Return", "VOO_Return"]),
                                  ("IRX", irx, ["IRX_Annual_Percent"])]:
        if frame.empty or not set(columns).issubset(frame.columns):
            raise ValueError(f"{name}: faltan datos o columnas requeridas.")
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates or frame.index.hasnans:
            raise ValueError(f"{name}: se requieren fechas datetime válidas y únicas.")
    result = market.sort_index().copy()
    if not result["Sample"].isin(["Train", "Test"]).all():
        raise ValueError("Sample debe conservar las etiquetas Train/Test.")
    train_dates = result.index[result["Sample"].eq("Train")]
    test_dates = result.index[result["Sample"].eq("Test")]
    if train_dates.empty or test_dates.empty or train_dates.max() >= test_dates.min():
        raise ValueError("Se requiere Train seguido de Test, sin volver a dividir.")
    rates = irx["IRX_Annual_Percent"].sort_index()
    if not np.isfinite(rates.dropna()).all():
        raise ValueError("^IRX contiene tasas no finitas.")
    # Unión antes del ffill: incluye tasas anteriores incluso en fechas sin TSLA.
    calendar = rates.index.union(result.index).sort_values()
    filled = rates.reindex(calendar).ffill()
    result["IRX_Annual_Percent"] = filled.reindex(result.index)
    observed_on = pd.Series(rates.index, index=rates.index).where(rates.notna())
    result["RF_Observation_Date"] = observed_on.reindex(calendar).ffill().reindex(result.index)
    result["RF_Daily"] = result["IRX_Annual_Percent"] / 100 / 252
    result["TSLA_Excess"] = result["TSLA_Return"] - result["RF_Daily"]
    result["Market_Excess"] = result["VOO_Return"] - result["RF_Daily"]
    train = result.loc[result["Sample"].eq("Train"), ["TSLA_Excess", "Market_Excess"]].dropna()
    if len(train) < 3 or not np.isfinite(train.to_numpy()).all():
        raise ValueError("CAPM requiere al menos tres observaciones Train válidas.")
    x = np.column_stack([np.ones(len(train)), train["Market_Excess"].to_numpy()])
    y = train["TSLA_Excess"].to_numpy()
    if np.linalg.matrix_rank(x) != 2:
        raise ValueError("Market_Excess no tiene variación suficiente en Train.")
    alpha, beta = np.linalg.lstsq(x, y, rcond=None)[0]
    sigma = float(np.std(y - x @ np.array([alpha, beta]), ddof=1))
    result["CAPM_Expected_Return"] = result["RF_Daily"] + alpha + beta * result["Market_Excess"]
    result["CAPM_AR"] = result["TSLA_Return"] - result["CAPM_Expected_Return"]
    result["Alpha_CAPM"] = alpha
    result["Beta_CAPM"] = beta
    summary = {"Alpha_CAPM": float(alpha), "Beta_CAPM": float(beta), "Sigma_Epsilon_CAPM": sigma,
               "Train_Observations": len(train),
               "Test_Observations": int(result.loc[result.Sample.eq("Test"), ["TSLA_Excess", "Market_Excess"]].notna().all(axis=1).sum()),
               "Missing_RF_Observations": int(result["RF_Daily"].isna().sum())}
    return result, summary


def run_capm(market_path="data/processed/market_model.csv", output_path="data/processed/capm_model.csv") -> pd.DataFrame:
    market = pd.read_csv(market_path, index_col="Date", parse_dates=["Date"])
    irx = download_irx(market.index.min(), market.index.max())
    result, summary = calculate_capm(market, irx)
    for frame, path in [(irx, Path("data/raw/irx.csv")), (result, Path(output_path))]:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=True, date_format="%Y-%m-%d")
    print("\nCAPM (parámetros congelados desde Train):")
    for name, value in summary.items():
        print(f"{name}: {value:.8f}" if isinstance(value, float) else f"{name}: {value}")
    print(f"Archivo creado: {output_path}")
    return result


if __name__ == "__main__":
    run_capm()
