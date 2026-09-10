"""Atención pública a NVIDIA: Wikimedia Pageviews e IOC v1 de intensidad."""

import json
import time
import warnings
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
from config import ATTENTION_START_DATE


API_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
PROJECT = "en.wikipedia"
ARTICLE = "Nvidia"
USER_AGENT = "BehavioralWave/1.0 (university behavioral finance research; NVIDIA public attention)"


class WikimediaError(RuntimeError):
    """No fue posible obtener una serie de Pageviews válida."""


def _parse_pageviews(payload: dict, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not payload["items"]:
        raise WikimediaError("Respuesta vacía o sin la lista items.")
    frame = pd.DataFrame(payload["items"])
    if not {"timestamp", "views"}.issubset(frame.columns):
        raise WikimediaError("Columnas inesperadas: se requieren timestamp y views.")
    for column, expected in {"article": ARTICLE, "access": "all-access", "agent": "user", "granularity": "daily"}.items():
        if column in frame and not frame[column].eq(expected).all():
            raise WikimediaError(f"La API devolvió un valor inesperado en {column}.")
    try:
        dates = pd.to_datetime(frame["timestamp"].astype(str), format="%Y%m%d%H", utc=True, errors="raise")
        views = pd.to_numeric(frame["views"], errors="raise")
    except (ValueError, TypeError) as exc:
        raise WikimediaError("Fechas o Pageviews inválidos.") from exc
    if dates.isna().any() or not dates.eq(dates.dt.normalize()).all():
        raise WikimediaError("Se requieren fechas diarias UTC válidas.")
    if not np.isfinite(views).all() or (views < 0).any() or not np.equal(views, np.floor(views)).all():
        raise WikimediaError("Pageviews debe contener conteos enteros no negativos.")
    result = pd.DataFrame({"Pageviews": views.to_numpy()}, index=pd.DatetimeIndex(dates).tz_localize(None)).rename_axis("Date")
    if not result.index.to_series().between(start, end).all():
        raise WikimediaError("La API devolvió fechas fuera del período solicitado.")
    if (result.groupby(level=0)["Pageviews"].nunique() > 1).any():
        raise WikimediaError("Hay conteos contradictorios para una misma fecha.")
    result = result.loc[~result.index.duplicated()].sort_index()
    # Los huecos quedan como NaN, nunca como cero ni como valores interpolados.
    # No se agregan días posteriores a la última observación publicada.
    calendar = pd.date_range(start, result.index.max(), name="Date")
    return result.reindex(calendar)


def download_wikimedia_pageviews(start=None, end=None) -> pd.DataFrame:
    """Consulta todo el período en una solicitud; los límites son inclusivos."""
    start = ATTENTION_START_DATE if start is None else start
    if start is None:
        raise ValueError("Ejecute python -m src.history_period para resolver la fecha inicial.")
    start = pd.Timestamp(start).normalize().tz_localize(None)
    latest_complete_day = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None) - pd.Timedelta(days=1)
    end = latest_complete_day if end is None else min(pd.Timestamp(end).normalize().tz_localize(None), latest_complete_day)
    if pd.isna(start) or pd.isna(end) or start > end:
        raise ValueError("Período Wikimedia inválido o sin días UTC completos.")
    url = f"{API_URL}/{PROJECT}/all-access/user/{quote(ARTICLE, safe='')}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00"
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        for attempt in range(3):
            try:
                response = session.get(url, timeout=(15, 45))
                response.raise_for_status()
            except requests.RequestException as exc:
                retryable = not isinstance(exc, requests.HTTPError) or exc.response.status_code in (429, 500, 502, 503, 504)
                if retryable and attempt < 2:
                    delay = 5 * (2 ** attempt)
                    if isinstance(exc, requests.HTTPError):
                        retry_after = exc.response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = max(delay, int(retry_after))
                    warnings.warn(f"Wikimedia: {type(exc).__name__}; reintento {attempt + 1}/2 en {delay}s.", stacklevel=2)
                    time.sleep(delay)
                    continue
                kind = "timeout" if isinstance(exc, requests.Timeout) else "error HTTP/red"
                raise WikimediaError(f"{kind} tras {attempt + 1} intento(s): {exc}") from exc
            if not response.text.strip():
                raise WikimediaError("La API devolvió una respuesta vacía.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise WikimediaError("La respuesta de Wikimedia no es JSON válido.") from exc
            result = _parse_pageviews(payload, start, end)
            missing = result.index[result["Pageviews"].isna()]
            if len(missing):
                warnings.warn(f"Wikimedia: {len(missing)} fechas faltantes; se conservan como NaN, sin imputación.", stacklevel=2)
            if result.index.max() < end:
                warnings.warn(f"Wikimedia: última fecha publicada {result.index.max():%Y-%m-%d}; se solicitó hasta {end:%Y-%m-%d}.", stacklevel=2)
            result.attrs["metadata"] = {
                "url": url, "project": PROJECT, "article": ARTICLE,
                "access": "all-access", "agent": "user", "granularity": "daily", "timezone": "UTC",
                "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "requested_start": str(start.date()), "requested_end": str(end.date()),
                "first_available": str(result["Pageviews"].first_valid_index().date()),
                "last_available": str(result["Pageviews"].last_valid_index().date()),
                "missing_dates": [str(day.date()) for day in missing],
                "baseline_days": 60, "baseline_shift": 1, "std_ddof": 1,
                "zero_sigma": "NaN; no se define un z-score con referencia constante",
                "ioc_meaning": "Intensidad de atención anormal positiva; no sentimiento ni dirección",
            }
            result.attrs["api_response"] = payload
            return result
    raise WikimediaError("Reintentos agotados.")


def calculate_attention_wave(pageviews: pd.DataFrame) -> pd.DataFrame:
    """Referencia móvil de 60 días calendario estrictamente anteriores a t."""
    if not isinstance(pageviews.index, pd.DatetimeIndex) or pageviews.empty or "Pageviews" not in pageviews:
        raise ValueError("Se requiere una serie Pageviews con índice Date de tipo datetime.")
    if pageviews.index.has_duplicates or pageviews.index.hasnans or not pageviews.index.equals(pageviews.index.normalize()):
        raise ValueError("Las fechas deben ser diarias, válidas y únicas.")
    observed = pageviews["Pageviews"].dropna()
    if not np.isfinite(observed).all() or (observed < 0).any() or not np.equal(observed, np.floor(observed)).all():
        raise ValueError("Pageviews debe contener conteos no negativos o NaN.")
    result = pageviews[["Pageviews"]].sort_index().copy()
    result = result.reindex(pd.date_range(result.index.min(), result.index.max(), name="Date"))
    result["Log_Pageviews"] = np.log1p(result["Pageviews"])
    # shift(1) excluye el día actual. Se exigen los 60 días previos completos.
    past = result["Log_Pageviews"].shift(1).rolling(window=60, min_periods=60)
    mean = past.mean()
    sigma = past.std(ddof=1)
    result["Attention_Z"] = (result["Log_Pageviews"] - mean) / sigma.where(sigma > 0)
    result["IAA"] = result["Attention_Z"].clip(lower=0)
    # IOC v1 mide intensidad: su signo no representa sentimiento ni dirección.
    result["IOC"] = 100 * np.tanh(result["IAA"] / 2)
    result["IOC_Velocity"] = result["IOC"].diff()
    result["IOC_Acceleration"] = result["IOC_Velocity"].diff()
    return result


def run_wikimedia_attention(start=None, end=None, *, raw=None) -> pd.DataFrame:
    raw = download_wikimedia_pageviews(start, end) if raw is None else raw
    wave = calculate_attention_wave(raw)
    raw_path = Path("data/raw/nvda_wikipedia_pageviews.csv")
    processed_path = Path("data/processed/attention_wave.csv")
    for frame, path in ((raw, raw_path), (wave, processed_path)):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".csv.tmp")
        frame.to_csv(temporary, index=True, date_format="%Y-%m-%d")
        temporary.replace(path)
    raw_path.with_suffix(".metadata.json").write_text(json.dumps(raw.attrs["metadata"], ensure_ascii=False, indent=2), encoding="utf-8")
    raw_path.with_suffix(".response.json").write_text(json.dumps(raw.attrs["api_response"], ensure_ascii=False), encoding="utf-8")
    return wave


def print_attention_summary(wave: pd.DataFrame) -> None:
    views = wave["Pageviews"].dropna()
    ioc = wave["IOC"].dropna()
    print("\nWIKIMEDIA ATTENTION:")
    print(f"Primera fecha: {views.index.min():%Y-%m-%d}")
    print(f"Última fecha: {views.index.max():%Y-%m-%d}")
    print(f"Número de observaciones: {len(views)}")
    print(f"Promedio de Pageviews: {views.mean():.2f}")
    print(f"Máximo Pageviews: {views.max():.0f} | Fecha: {views.idxmax():%Y-%m-%d}")
    if ioc.empty:
        print("Máximo IOC: no disponible (referencia histórica insuficiente o sigma cero).")
    else:
        print(f"Máximo IOC: {ioc.max():.6f} | Fecha: {ioc.idxmax():%Y-%m-%d}")
    if wave["Pageviews"].isna().any():
        print(f"Fechas faltantes (sin imputar): {wave['Pageviews'].isna().sum()}")
    print("Últimas 5 observaciones:")
    print(wave.tail(5).to_string())


if __name__ == "__main__":
    try:
        print_attention_summary(run_wikimedia_attention())
    except WikimediaError as exc:
        raise SystemExit(f"WIKIMEDIA ATTENTION: descarga no completada. {exc}") from exc
