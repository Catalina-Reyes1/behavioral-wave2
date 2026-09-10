"""Inicio común por disponibilidad y calentamiento; no consulta resultados económicos."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from config import ASSET, MARKET, END_DATE
from src.market_data import download_market_data
from src.wikimedia_attention import download_wikimedia_pageviews, calculate_attention_wave


ROOT = Path(__file__).resolve().parents[1]


def determine_common_period(market: pd.DataFrame, attention: pd.DataFrame) -> dict:
    """Primera sesión con retornos disponibles e IOC calculable con 60 días pasados."""
    market = market.sort_index()
    attention = attention.sort_index()
    valid_market = market.loc[np.isfinite(market[["NVDA_Price", "VOO_Price", "NVDA_Return", "VOO_Return"]]).all(axis=1)]
    observed = attention.Pageviews.dropna()
    if valid_market.empty or observed.empty:
        raise ValueError("No hay historia común de precios, retornos y Pageviews.")
    # Usar el indicador existente sin modificar ventana, IAA ni IOC.
    wave = calculate_attention_wave(attention.loc[observed.index.min():observed.index.max()])
    ready = wave.index[wave.IOC.notna()]
    eligible = valid_market.index.intersection(ready)
    if eligible.empty:
        raise ValueError("No hay sesión común con los 60 días previos y sigma de atención válida.")
    first = eligible.min()
    # Límite final por datos observados, no por si generan señales o buenos resultados.
    last = valid_market.index.intersection(observed.index).max()
    previous_prices = market.loc[(market.index < first) & market[["NVDA_Price", "VOO_Price"]].notna().all(axis=1)]
    if previous_prices.empty:
        raise ValueError("Falta el cierre anterior necesario para el primer retorno efectivo.")
    return {
        "nvda_first_price": str(market.NVDA_Price.first_valid_index().date()),
        "voo_first_price": str(market.VOO_Price.first_valid_index().date()),
        "first_common_return": str(valid_market.index.min().date()),
        "attention_first_observation": str(observed.index.min().date()),
        "attention_last_observation": str(observed.index.max().date()),
        "attention_first_valid_ioc": str(ready.min().date()),
        "analysis_start": str(first.date()), "analysis_end": str(last.date()),
        "market_download_start": str(previous_prices.index.max().date()),
        "attention_warmup_days": int((first - observed.index.min()).days),
        "selection_basis": "Primera sesión con retornos de NVDA/VOO e IOC válido; ninguna métrica de backtest interviene.",
    }


def discover_history_period() -> dict:
    market = download_market_data(ASSET, MARKET, start=None, end=END_DATE)
    first_common_price = market.dropna(subset=["NVDA_Price", "VOO_Price"]).index.min()
    attention = download_wikimedia_pageviews(str(first_common_price.date()), END_DATE)
    period = determine_common_period(market, attention)
    # Guardar la respuesta de descubrimiento, sin reemplazar todavía el pipeline.
    discovery = ROOT / "data/raw/history_discovery"
    discovery.mkdir(parents=True, exist_ok=True)
    market.to_csv(discovery / "market_max.csv", date_format="%Y-%m-%d")
    attention.to_csv(discovery / "pageviews_probe.csv", date_format="%Y-%m-%d")
    (discovery / "pageviews_response.json").write_text(json.dumps(attention.attrs["api_response"], ensure_ascii=False), encoding="utf-8")
    period["pageviews_query"] = attention.attrs["metadata"]["url"]
    period["discovered_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    (ROOT / "data/raw/history_period.json").write_text(json.dumps(period, indent=2, ensure_ascii=False), encoding="utf-8")
    config = ROOT / "config.py"
    source = config.read_text(encoding="utf-8")
    for name, value in {"START_DATE": period["analysis_start"], "ATTENTION_START_DATE": period["attention_first_observation"],
                        "MARKET_DOWNLOAD_START": period["market_download_start"]}.items():
        source, replacements = re.subn(rf"^{name} = .*?$", f'{name} = "{value}"', source, flags=re.MULTILINE)
        if replacements != 1:
            raise ValueError(f"No se pudo centralizar {name} en config.py.")
    config.write_text(source, encoding="utf-8")
    print(json.dumps(period, indent=2, ensure_ascii=False))
    print("Fechas resueltas y centralizadas en config.py. Ejecute python main.py.")
    return period


if __name__ == "__main__":
    discover_history_period()
