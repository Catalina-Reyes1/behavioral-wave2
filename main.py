import json
from datetime import date, timedelta
from pathlib import Path

from config import ASSET, MARKET, START_DATE, END_DATE, TRAIN_RATIO, ATTENTION_START_DATE, MARKET_DOWNLOAD_START
from src.abnormal_returns import calculate_abnormal_returns
from src.market_data import download_market_data, save_market_data
from src.wikimedia_attention import WikimediaError, download_wikimedia_pageviews, run_wikimedia_attention, print_attention_summary
from src.signals import run_signals
from src.capm_model import run_capm
from src.backtest import run_backtest
from src.history_period import determine_common_period
from src.export_web_data import export_web_data


def main():
    if any(value is None for value in [START_DATE, ATTENTION_START_DATE, MARKET_DOWNLOAD_START]):
        raise RuntimeError("Ejecute python -m src.history_period antes de regenerar el pipeline.")
    print(f"Descargando datos: {ASSET} vs {MARKET}...")
    df = download_market_data(
        asset=ASSET,
        market=MARKET,
        start=MARKET_DOWNLOAD_START,
        # Yahoo excluye end; Wikimedia y el período del estudio lo incluyen.
        end=(date.fromisoformat(END_DATE) + timedelta(days=1)).isoformat() if END_DATE else None,
    )

    # Adquirir las fuentes primero para conocer el extremo común sin mirar resultados.
    raw_attention = download_wikimedia_pageviews(start=ATTENTION_START_DATE, end=END_DATE)
    period = determine_common_period(df, raw_attention)
    if period["analysis_start"] != START_DATE:
        raise RuntimeError("Cambió la disponibilidad inicial; vuelva a ejecutar python -m src.history_period.")
    if END_DATE is not None and period["analysis_end"] != END_DATE:
        raise RuntimeError("Las fuentes no cubren el corte final congelado; se conservan los resultados anteriores.")
    df = df.loc[:period["analysis_end"]]
    save_market_data(df, "data/raw/market_data.csv")
    Path("data/processed/analysis_period.json").write_text(json.dumps(period, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Período efectivo común: {START_DATE} a {period['analysis_end']}")

    print("\nÚltimas observaciones:")
    print(df.tail())
    print("\nArchivo creado: data/raw/market_data.csv")
    print(f"Observaciones: {len(df):,}")

    market_model, summary = calculate_abnormal_returns(df.loc[START_DATE:], TRAIN_RATIO)
    save_market_data(market_model, "data/processed/market_model.csv")

    print("\nModelo de mercado (estimado solo con Train):")
    print(f"Alpha: {summary['alpha']:.8f}")
    print(f"Beta: {summary['beta']:.8f}")
    print(f"Sigma epsilon: {summary['sigma_epsilon']:.8f}")
    print(f"Observaciones Train: {summary['n_train']}")
    print(f"Observaciones Test: {summary['n_test']}")
    print(f"Fecha de inicio Test: {summary['test_start']:%Y-%m-%d}")
    columns = [
        "NVDA_Return", "VOO_Return", "Expected_Return", "AR",
        "CAR_5", "CAR_Z", "Sample",
    ]
    print("\nUltimas 5 observaciones del modelo:")
    print(market_model[columns].tail(5).to_string())
    print("\nArchivo creado: data/processed/market_model.csv")

    try:
        attention = run_wikimedia_attention(raw=raw_attention)
    except WikimediaError as exc:
        raise SystemExit(f"\nWIKIMEDIA ATTENTION: descarga no completada. {exc}") from exc
    print_attention_summary(attention)
    print("\nArchivo creado: data/raw/nvda_wikipedia_pageviews.csv")
    print("Archivo creado: data/processed/attention_wave.csv")
    run_signals()
    run_capm()
    run_backtest()
    export_web_data()


if __name__ == "__main__":
    main()
