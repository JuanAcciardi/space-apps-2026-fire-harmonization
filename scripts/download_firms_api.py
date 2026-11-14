"""Completa el archivo con la API de FIRMS (requiere MAP_KEY): lo que no está en los CSV anuales por país.

- 2026 para MODIS, VIIRS S-NPP (hasta 2026-11-02) y VIIRS NOAA-20: SP hasta donde llega y NRT después.
- VIIRS NOAA-21 completo (SP desde 2023-03-01 + NRT), que no existe en los anuales por país.
La API devuelve una caja (bbox), así que se filtran los puntos dentro del polígono de Argentina.
Salida con el mismo nombre/patrón que los anuales: data/raw/{sensor}_{año}_Argentina.csv

Uso: python scripts/download_firms_api.py   (lee firms_key.txt o FIRMS_MAP_KEY)
"""
import io
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BBOX = "-74,-56,-53,-21"  # W,S,E,N
API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}/{start}"
AVAIL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{key}/ALL"

# sensor de salida -> (prefijo de fuente API, primer día a pedir)
PLAN = {
    "modis": ("MODIS", date(2026, 1, 1)),
    "viirs-snpp": ("VIIRS_SNPP", date(2026, 1, 1)),
    "viirs-jpss1": ("VIIRS_NOAA20", date(2026, 1, 1)),
    "viirs-jpss2": ("VIIRS_NOAA21", date(2023, 3, 1)),
}


def key() -> str:
    k = os.environ.get("FIRMS_MAP_KEY") or (ROOT / "firms_key.txt").read_text().strip()
    if not k:
        sys.exit("Falta la MAP_KEY de FIRMS (firms_key.txt o FIRMS_MAP_KEY)")
    return k


def fetch(url: str, retries: int = 4) -> pd.DataFrame:
    for i in range(retries):
        r = requests.get(url, timeout=180)
        if r.status_code == 200 and r.text.strip():
            if r.text.startswith("Invalid") or r.text.startswith("<"):
                raise RuntimeError(r.text[:200])
            return pd.read_csv(io.StringIO(r.text), dtype={"acq_time": str, "confidence": str, "version": str})
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"sin respuesta: {url}")


def windows(d0: date, d1: date, step: int = 5):
    d = d0
    while d <= d1:
        n = min(step, (d1 - d).days + 1)
        yield d, n
        d += timedelta(days=n)


def main():
    k = key()
    avail = pd.read_csv(io.StringIO(requests.get(AVAIL.format(key=k), timeout=60).text))
    avail = {r.data_id: (date.fromisoformat(r.min_date), date.fromisoformat(r.max_date)) for r in avail.itertuples()}
    arg = gpd.read_file(ROOT / "data" / "geo" / "argentina_adm0.geojson").geometry.union_all()
    arg_prep = gpd.GeoSeries([arg]).iloc[0]
    n_req = 0
    for sensor, (prefix, first) in PLAN.items():
        frames = []
        for kind in ("SP", "NRT"):
            src = f"{prefix}_{kind}"
            if src not in avail:
                continue
            a0, a1 = avail[src]
            d0, d1 = max(first, a0), a1
            if kind == "NRT" and f"{prefix}_SP" in avail:
                d0 = max(d0, avail[f"{prefix}_SP"][1] + timedelta(days=1))  # NRT solo después del SP
            if d0 > d1:
                continue
            for start, n in windows(d0, d1):
                df = fetch(API.format(key=k, source=src, bbox=BBOX, days=n, start=start.isoformat()))
                n_req += 1
                if len(df):
                    df["product"] = src
                    frames.append(df)
                print(f"  {src} {start} +{n}d: {len(df)} filas", flush=True)
                if n_req % 40 == 0:
                    time.sleep(2)
        if not frames:
            print(f"{sensor}: nada")
            continue
        df = pd.concat(frames, ignore_index=True)
        inside = gpd.GeoSeries([Point(xy) for xy in zip(df.longitude, df.latitude)]).within(arg_prep)
        df = df[inside.values].copy()
        if "type" not in df.columns:
            df["type"] = pd.NA
        df["acq_date"] = pd.to_datetime(df.acq_date)
        for y, g in df.groupby(df.acq_date.dt.year):
            out = RAW / f"{sensor}_{y}_Argentina.csv"
            if out.exists() and y < 2026 and sensor != "viirs-jpss2":
                continue  # no pisar anuales oficiales
            g.assign(acq_date=g.acq_date.dt.strftime("%Y-%m-%d")).to_csv(out, index=False)
            print(f"{out.name}: {len(g)} filas ({g.acq_date.min().date()} .. {g.acq_date.max().date()})", flush=True)


if __name__ == "__main__":
    main()
