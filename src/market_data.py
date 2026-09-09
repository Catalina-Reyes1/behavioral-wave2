from pathlib import Path
import pandas as pd
import yfinance as yf


def download_market_data(asset: str, market: str, start: str | None = None, end=None) -> pd.DataFrame:
    tickers = [asset, market]
    raw = yf.download(
        tickers=tickers,
        **({"period": "max"} if start is None else {"start": start}),
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
    )

    if raw.empty:
        raise RuntimeError("No se descargaron datos desde Yahoo Finance.")

    # yfinance devuelve MultiIndex cuando hay más de un ticker.
    if isinstance(raw.columns, pd.MultiIndex):
        price_field = "Adj Close" if "Adj Close" in raw.columns.get_level_values(0) else "Close"
        prices = raw[price_field].copy()
    else:
        price_field = "Adj Close" if "Adj Close" in raw.columns else "Close"
        prices = raw[[price_field]].copy()
        prices.columns = tickers[:1]

    prices = prices.rename(columns={asset: "TSLA_Price", market: "VOO_Price"})
    prices = prices.dropna(how="all")

    prices["TSLA_Return"] = prices["TSLA_Price"].pct_change()
    prices["VOO_Return"] = prices["VOO_Price"].pct_change()

    return prices


def save_market_data(df: pd.DataFrame, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=True)
