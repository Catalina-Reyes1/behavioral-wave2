"""Exportación de resultados existentes para la web; no ejecuta ningún modelo."""

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _read(root: Path, filename: str) -> pd.DataFrame:
    frame = pd.read_csv(root / filename, index_col="Date", parse_dates=["Date"])
    if frame.empty or frame.index.has_duplicates or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"Fechas o datos inválidos: {filename}")
    return frame.sort_index()


def _records(frame: pd.DataFrame) -> list[dict]:
    frame = frame.reset_index()
    if "Date" in frame:
        frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    # pandas transforma NaN en null válido para JSON, conservando los huecos.
    return json.loads(frame.to_json(orient="records", double_precision=15))


def build_web_data(root: Path = ROOT) -> dict:
    market = _read(root, "data/processed/market_model.csv")
    attention = _read(root, "data/processed/attention_wave.csv")
    signals = _read(root, "data/processed/behavioral_signals.csv")
    capm = _read(root, "data/processed/capm_model.csv")
    events = _read(root, "data/processed/backtest_events.csv")
    summary = pd.read_csv(root / "results/backtest_summary.csv", index_col="Sample")
    attention_meta = json.loads((root / "data/raw/tsla_wikipedia_pageviews.metadata.json").read_text(encoding="utf-8"))
    for name, frame in [("señales", signals), ("CAPM", capm)]:
        if not market.index.equals(frame.index) or not market.Sample.equals(frame.Sample):
            raise ValueError(f"La versión de {name} no coincide con el calendario del mercado.")
    if not {"Train", "Test", "Total"}.issubset(summary.index):
        raise ValueError("Faltan resultados Train/Test/Total.")
    train = market.loc[market.Sample.eq("Train")]
    test = market.loc[market.Sample.eq("Test")]
    # El CSV no guarda alpha/beta: recuperar algebraicamente la recta YA GUARDADA.
    # No se estima una regresión ni se cambia el modelo. Se valida contra toda la muestra.
    low = train.loc[train.VOO_Return.idxmin()]
    high = train.loc[train.VOO_Return.idxmax()]
    beta = float((high.Expected_Return - low.Expected_Return) / (high.VOO_Return - low.VOO_Return))
    alpha = float(low.Expected_Return - beta * low.VOO_Return)
    if not np.allclose(market.Expected_Return, alpha + beta * market.VOO_Return, atol=1e-12):
        raise ValueError("Los retornos esperados guardados no corresponden a una recta congelada.")
    # Recuperar sigma de CAR_Z = CAR_5 / (sigma * sqrt(5)), sin recalcular residuos.
    reference = train.loc[train.CAR_Z.abs().idxmax()]
    sigma = float(reference.CAR_5 / reference.CAR_Z / np.sqrt(5))
    valid_car = market.CAR_Z.notna()
    if not np.allclose(market.loc[valid_car, "CAR_Z"], market.loc[valid_car, "CAR_5"] / (sigma * np.sqrt(5)), atol=1e-12):
        raise ValueError("CAR_Z guardado es inconsistente con sigma.")
    thresholds = {}
    for column in ["IOC_Extreme_Threshold", "CAR_Positive_Threshold", "CAR_Negative_Threshold"]:
        if signals[column].nunique() != 1:
            raise ValueError(f"Umbral no congelado: {column}")
        thresholds[column] = float(signals[column].iloc[0])
    completed = events.loc[events.Status.eq("Completed")]
    if int(summary.loc["Total", "Trades"]) != len(completed):
        raise ValueError("El resumen y los eventos no corresponden a la misma ejecución.")
    if completed.Transaction_Cost.nunique() != 1:
        raise ValueError("Los eventos no tienen un costo fijo.")
    # Leer las constantes de costos sin importar ni ejecutar el backtest.
    cost_constants = {}
    for node in ast.parse((root / "src/backtest.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("ENTRY_COST", "EXIT_COST"):
                    cost_constants[target.id] = float(node.value.value)
    if not np.isclose(sum(cost_constants.values()), completed.Transaction_Cost.iloc[0]):
        raise ValueError("Los costos documentados no coinciden con el CSV de eventos.")
    horizons = {market.index.get_loc(pd.Timestamp(row.Exit_Date)) - market.index.get_loc(date) + 1 for date, row in completed.iterrows()}
    if horizons != {5}:
        raise ValueError("El horizonte guardado no es de cinco sesiones.")
    signal_events = signals.loc[signals.Signal.ne(0), ["Sample", "IOC", "CAR_Z", "Signal", "Trade_Signal"]].copy()
    signal_events["TSLA_Price"] = market.loc[signal_events.index, "TSLA_Price"]
    next_session = pd.Series(market.index, index=market.index).shift(-1)
    signal_events["Entry_Date"] = next_session.reindex(signal_events.index).dt.strftime("%Y-%m-%d")
    signal_events["Entry_Trade_Signal"] = signals.Trade_Signal.shift(-1).reindex(signal_events.index)
    if not np.allclose(signal_events.Entry_Trade_Signal.dropna(), signal_events.loc[signal_events.Entry_Trade_Signal.notna(), "Signal"]):
        raise ValueError("Los eventos no corresponden a Trade_Signal en la siguiente sesión.")
    timeline = market[["TSLA_Price", "Sample"]].join(signals[["IOC", "Signal"]])
    latest_ioc = attention.IOC.dropna()
    overview = {
        "period": {"start": str(market.index.min().date()), "end": str(market.index.max().date()),
                   "attention_end": str(attention.index.max().date())},
        "sessions": len(market), "signal_count": len(signal_events),
        "split": {"train_count": len(train), "test_count": len(test), "train_end": str(train.index.max().date()),
                  "test_start": str(test.index.min().date()), "train_share": len(train) / len(market)},
        "market_model": {"alpha": alpha, "beta": beta, "sigma_epsilon": sigma},
        "capm": {"alpha": float(capm.Alpha_CAPM.iloc[0]), "beta": float(capm.Beta_CAPM.iloc[0])},
        "thresholds": thresholds, "horizon_sessions": next(iter(horizons)),
        "round_trip_cost": float(completed.Transaction_Cost.iloc[0]),
        "entry_cost": cost_constants["ENTRY_COST"], "exit_cost": cost_constants["EXIT_COST"],
        "attention": {"baseline_days": attention_meta["baseline_days"], "baseline_shift": attention_meta["baseline_shift"],
                      "article": attention_meta["article"], "project": attention_meta["project"],
                      "latest_ioc": float(latest_ioc.iloc[-1]), "latest_ioc_date": str(latest_ioc.index[-1].date())},
        "results": json.loads(summary.reset_index().to_json(orient="records", double_precision=15)),
    }
    overview["signal_counts"] = {sample: int(signal_events.Sample.eq(sample).sum()) for sample in ["Train", "Test"]}
    archive = root / "results/pre_expansion"
    archived_market = _read(archive, "data/processed/market_model.csv")
    archived_signals = _read(archive, "data/processed/behavioral_signals.csv")
    archived_summary = pd.read_csv(archive / "results/backtest_summary.csv", index_col="Sample")
    overview["robustness"] = {
        "label": "Período reciente: 2019–2026", "source": "results/pre_expansion/",
        "start": str(archived_market.index.min().date()), "end": str(archived_market.index.max().date()),
        "sessions": len(archived_market), "events": int(archived_signals.Signal.ne(0).sum()),
        "test": json.loads(archived_summary.loc["Test"].to_json(double_precision=15)),
    }
    paths = ["data/processed/market_model.csv", "data/processed/attention_wave.csv", "data/processed/behavioral_signals.csv",
             "data/processed/capm_model.csv", "data/processed/backtest_events.csv", "results/backtest_summary.csv",
             "data/raw/tsla_wikipedia_pageviews.metadata.json", "src/backtest.py"]
    paths.extend(["results/pre_expansion/data/processed/market_model.csv",
                  "results/pre_expansion/data/processed/behavioral_signals.csv",
                  "results/pre_expansion/results/backtest_summary.csv"])
    overview["sources"] = [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()} for path in paths]
    return {"overview": overview, "series": {"market": _records(timeline), "attention": _records(attention[["IOC", "Pageviews"]])},
            "events": {"signals": _records(signal_events), "trades": _records(events)}}


def export_web_data(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    data = build_web_data(root)
    output = output_dir if output_dir is not None else root / "app/data"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in data.items():
        (output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    # El mismo contenido para abrir index.html por doble clic (fetch file:// se bloquea).
    serialized = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("</", "<\\/")
    (output / "snapshot.js").write_text("window.BEHAVIORAL_WAVE_DATA = " + serialized + ";\n", encoding="utf-8")
    print(f"Exportación web: {data['overview']['sessions']} sesiones, {data['overview']['signal_count']} eventos.")
    print(f"Archivos creados en {output}")
    return data


if __name__ == "__main__":
    export_web_data()
