"""Series diarias de NVIDIA mediante GDELT DOC 2.0, sin IOC ni señales."""

import hashlib
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests


API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = "NVIDIA"
MODES = {"TimelineVolRaw": "News_Count", "TimelineTone": "News_Tone"}


class GDELTError(RuntimeError):
    """La descarga no permite construir una serie verificable."""


class HistoricalRangeError(GDELTError):
    """La API rechaza explicitamente el rango historico solicitado."""


def _parse_timeline(payload: dict, mode: str) -> pd.Series:
    """Exige datos diarios; no promedia tonos de intervalos intradiarios."""
    if not isinstance(payload, dict) or not payload.get("timeline"):
        raise GDELTError(f"{mode}: respuesta vacia o sin timeline.")
    timeline = payload["timeline"]
    if not isinstance(timeline, list) or len(timeline) != 1:
        raise GDELTError(f"{mode}: estructura de series inesperada.")
    if not isinstance(timeline[0], dict) or not isinstance(timeline[0].get("data"), list):
        raise GDELTError(f"{mode}: falta la lista data.")
    frame = pd.DataFrame(timeline[0]["data"])
    if frame.empty or not {"date", "value"}.issubset(frame.columns):
        raise GDELTError(f"{mode}: datos vacios o columnas inesperadas; se requieren date y value.")
    try:
        dates = pd.to_datetime(frame["date"], format="%Y%m%dT%H%M%SZ", utc=True, errors="raise")
        values = pd.to_numeric(frame["value"], errors="raise")
    except (ValueError, TypeError) as exc:
        raise GDELTError(f"{mode}: fechas o valores invalidos.") from exc
    if dates.isna().any() or not dates.eq(dates.dt.normalize()).all():
        raise GDELTError(f"{mode}: la respuesta no tiene resolucion diaria UTC.")
    if not np.isfinite(values).all():
        raise GDELTError(f"{mode}: valores ausentes o no finitos.")
    if mode == "TimelineVolRaw":
        if (values < 0).any() or not np.equal(values, np.floor(values)).all():
            raise GDELTError("TimelineVolRaw: los conteos deben ser enteros no negativos.")
        values = values.astype("int64")
    elif not values.between(-100, 100).all():
        raise GDELTError("TimelineTone: tono fuera del rango [-100, 100].")
    series = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates).tz_localize(None), name=MODES[mode])
    # Eliminar duplicados identicos; rechazar duplicados que se contradicen.
    if (series.groupby(level=0).nunique() > 1).any():
        raise GDELTError(f"{mode}: valores contradictorios para una misma fecha.")
    return series[~series.index.duplicated()].sort_index().rename_axis("Date")


class _Client:
    def __init__(self, session, cache_dir: Path):
        self.session = session
        self.cache_dir = cache_dir
        self.last_request = 0.0
        self.records = []

    def fetch(self, mode: str, bounds: dict) -> pd.Series:
        params = {"query": QUERY, "mode": mode, "format": "json", "timelinesmooth": 0, **bounds}
        # Las respuestas originales permiten reproducir el CSV sin consultar otra vez.
        cache_key = dict(params)
        if "timespan" in bounds:
            cache_key["as_of_utc"] = str(pd.Timestamp.now(tz="UTC").date())
        key = hashlib.sha256(json.dumps(cache_key, sort_keys=True).encode()).hexdigest()[:20]
        path = self.cache_dir / f"{mode}_{key}.json"
        if path.exists():
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                if snapshot["params"] != params:
                    raise ValueError("Parametros de cache incompatibles")
                series = _parse_timeline(snapshot["response"], mode)
            except (ValueError, KeyError, TypeError) as exc:
                raise GDELTError(f"Cache invalida: {path}") from exc
            self.records.append({"file": str(path), "params": params, "retrieved_at": snapshot["retrieved_at"], "cached": True})
            return series

        for attempt in range(3):
            # GDELT exige al menos cinco segundos entre solicitudes.
            time.sleep(max(0, 6 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.get(API_URL, params=params, timeout=(15, 40))
                response.raise_for_status()
            except requests.RequestException as exc:
                retryable = not isinstance(exc, requests.HTTPError) or exc.response.status_code in (429, 500, 502, 503, 504)
                if retryable and attempt < 2:
                    delay = 30 * (2 ** attempt)
                    if isinstance(exc, requests.HTTPError):
                        retry_after = exc.response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(60, max(delay, int(retry_after)))
                    warnings.warn(f"GDELT {mode}: {type(exc).__name__}; reintento {attempt + 1}/2 en {delay}s.", stacklevel=2)
                    time.sleep(delay)
                    continue
                kind = "timeout" if isinstance(exc, requests.Timeout) else "error HTTP/red"
                raise GDELTError(f"{mode}: {kind} tras {attempt + 1} intento(s): {exc}") from exc
            if not response.text.strip():
                raise GDELTError(f"{mode}: respuesta HTTP vacia.")
            try:
                payload = response.json()
            except ValueError as exc:
                message = response.text.strip()[:500]
                lower = message.lower()
                # Solo un rechazo explicito de antiguedad permite probar el rango reciente.
                if "date" in lower and ("too far in the past" in lower or "within the last" in lower):
                    raise HistoricalRangeError(f"{mode}: {message}") from exc
                raise GDELTError(f"{mode}: se esperaba JSON; API respondio: {message}") from exc
            series = _parse_timeline(payload, mode)
            snapshot = {"params": params, "url": response.url, "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(), "response": payload}
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
            self.records.append({"file": str(path), "params": params, "retrieved_at": snapshot["retrieved_at"], "cached": False})
            return series
        raise GDELTError(f"{mode}: reintentos agotados.")


def _windows(start: pd.Timestamp, end: pd.Timestamp):
    """Ventanas de hasta 365 dias; ampliar la ultima asegura pasos diarios (>7 dias)."""
    cursor = start
    while cursor <= end:
        stop = min(cursor + pd.Timedelta(days=364), end)
        query_start = min(cursor, stop - pd.Timedelta(days=8))
        yield query_start, stop
        cursor = stop + pd.Timedelta(days=1)


def _combine(volume: pd.Series, tone: pd.Series, start, end) -> pd.DataFrame:
    if not volume.index.equals(tone.index):
        raise GDELTError("Volumen y tono tienen fechas diferentes; no se imputan observaciones.")
    frame = pd.concat([volume, tone], axis=1).loc[start:end]
    if frame.empty:
        raise GDELTError("La API no devolvio observaciones dentro del rango solicitado.")
    # Sin articulos, el tono medio no esta definido, aunque GDELT devuelva cero.
    frame.loc[frame["News_Count"].eq(0), "News_Tone"] = np.nan
    return frame


def download_gdelt_data(start="2019-01-01", end=None, output_path="data/raw/nvda_gdelt.csv") -> pd.DataFrame:
    """Descarga dias UTC cerrados y guarda CSV, respuestas y metadatos de cobertura.

    end es inclusivo. El dia actual se excluye por estar incompleto. No se
    sobreescribe el CSV anterior si falla alguna ventana o modo requerido.
    """
    start = pd.Timestamp(start).normalize().tz_localize(None)
    latest = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None) - pd.Timedelta(days=1)
    end = latest if end is None else min(pd.Timestamp(end).normalize().tz_localize(None), latest)
    if pd.isna(start) or pd.isna(end) or start > end:
        raise ValueError("Rango de fechas GDELT invalido o sin dias UTC completos.")
    path = Path(output_path)
    frames = []
    limitation = None
    with requests.Session() as session:
        session.headers.update({"User-Agent": "BehavioralWave/1.0 (university research; GDELT DOC 2.0)"})
        client = _Client(session, path.parent / "gdelt_responses")
        try:
            for window_start, window_end in _windows(start, end):
                print(f"GDELT: consultando {window_start:%Y-%m-%d} a {window_end:%Y-%m-%d}...", flush=True)
                bounds = {"startdatetime": window_start.strftime("%Y%m%d000000"), "enddatetime": window_end.strftime("%Y%m%d235959")}
                volume = client.fetch("TimelineVolRaw", bounds)
                tone = client.fetch("TimelineTone", bounds)
                if not volume.index.to_series().between(window_start, window_end).all() or not tone.index.to_series().between(window_start, window_end).all():
                    raise GDELTError("La API devolvio fechas fuera de la ventana solicitada.")
                frames.append(_combine(volume, tone, start, end))
        except HistoricalRangeError as exc:
            if frames:
                raise
            limitation = f"Historico rechazado por la API: {exc}. Se consulto solamente timespan=3m."
            warnings.warn(limitation, stacklevel=2)
            volume = client.fetch("TimelineVolRaw", {"timespan": "3m"})
            tone = client.fetch("TimelineTone", {"timespan": "3m"})
            frames = [_combine(volume, tone, start, end)]

    result = pd.concat(frames).sort_index()
    if (result.groupby(level=0).nunique(dropna=False) > 1).any().any():
        raise GDELTError("Las ventanas solapadas contienen valores contradictorios.")
    result = result.loc[~result.index.duplicated()].rename_axis("Date")
    missing = pd.date_range(start, end).difference(result.index)
    metadata = {
        "endpoint": API_URL, "query": QUERY,
        "requested_start": str(start.date()), "requested_end": str(end.date()),
        "available_start": str(result.index.min().date()), "available_end": str(result.index.max().date()),
        "complete_requested_range": len(missing) == 0,
        "missing_dates": [str(date.date()) for date in missing],
        "limitation": limitation, "timezone": "UTC", "current_day_excluded": True,
        "source_breadth": "Pendiente: no se ha validado la exhaustividad del desglose TimelineSourceCountry.",
        "requests": client.records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    result.to_csv(temporary, index=True, date_format="%Y-%m-%d")
    temporary.replace(path)
    path.with_suffix(".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(missing):
        warnings.warn(f"GDELT: faltan {len(missing)} dias del rango solicitado; consulte {path.with_suffix('.metadata.json')}. No se rellenaron con ceros.", stacklevel=2)
    result.attrs["metadata"] = metadata
    return result


def print_gdelt_summary(df: pd.DataFrame) -> None:
    print("\nGDELT:")
    print(f"Primera fecha disponible: {df.index.min():%Y-%m-%d}")
    print(f"Ultima fecha disponible: {df.index.max():%Y-%m-%d}")
    print(f"Numero de dias obtenidos: {len(df)}")
    print(f"Promedio de News_Count: {df['News_Count'].mean():.2f}")
    print(f"Minimo de News_Tone: {df['News_Tone'].min():.6f}")
    print(f"Maximo de News_Tone: {df['News_Tone'].max():.6f}")
    print("Ultimas 5 observaciones:")
    print(df.tail(5).to_string())


if __name__ == "__main__":
    try:
        print_gdelt_summary(download_gdelt_data())
    except GDELTError as exc:
        raise SystemExit(f"GDELT: descarga no completada. {exc}") from exc
