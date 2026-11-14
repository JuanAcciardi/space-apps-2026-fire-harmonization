"""Descarga los CSV anuales por país de NASA FIRMS (sin API key).

Fuente: https://firms.modaps.eosdis.nasa.gov/country/
Patrón: https://firms.modaps.eosdis.nasa.gov/data/country/{sensor}/{año}/{sensor}_{año}_{País}.csv

Sensores:
  modis       -> MODIS Terra + Aqua (1 km), 2000-2025
  viirs-snpp  -> VIIRS Suomi-NPP (375 m), 2012-2025
  viirs-jpss1 -> VIIRS NOAA-20 (375 m), 2018-2025
Los datos de 2026 no están en los anuales; se bajan por API (scripts/download_firms_api.py).
"""
import sys, time
from pathlib import Path
import requests

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
COUNTRY = "Argentina"
SENSORS = {
    "modis": range(2000, 2026),
    "viirs-snpp": range(2012, 2026),
    "viirs-jpss1": range(2018, 2026),
}
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"


def download(url: str, dest: Path, retries: int = 4) -> str:
    if dest.exists() and dest.stat().st_size > 1000:
        return "cached"
    for i in range(retries):
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                if r.status_code == 404:
                    return "404"
                r.raise_for_status()
                tmp = dest.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(dest)
                return f"{dest.stat().st_size/1e6:.1f} MB"
        except Exception as e:  # noqa: BLE001
            wait = 5 * (i + 1)
            print(f"  reintento {i+1} en {wait}s: {e}", flush=True)
            time.sleep(wait)
    return "ERROR"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for sensor, years in SENSORS.items():
        for y in years:
            name = f"{sensor}_{y}_{COUNTRY}.csv"
            dest = OUT / name
            status = download(f"{BASE}/{sensor}/{y}/{name}", dest)
            print(f"{name}: {status}", flush=True)


if __name__ == "__main__":
    main()
