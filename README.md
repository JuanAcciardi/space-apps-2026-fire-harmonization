# Harmonization of MODIS and VIIRS Hot Spots — Argentina

NASA Space Apps Challenge 2026 (Nov 14–15) · Challenge written by CONAE: *Harmonization of MODIS and VIIRS Hot Spots*.

**Team LMA** — Juan Ignacio Acciardi, Verónica Ana López Marsico.

> **Para continuar la entrega (demo, textos, formulario): [docs/PROXIMOS_PASOS.md](docs/PROXIMOS_PASOS.md).** Cierre: domingo 15/11, 23:59 hora de la sede.

**Web app:** https://juanacciardi.github.io/space-apps-2026-fire-harmonization/ · Official challenge text: [docs/challenge.md](docs/challenge.md) · Submission texts: [docs/submission.md](docs/submission.md) · Presentación: [PDF](docs/presentacion/Burning%20Activity%20Calendar%20%E2%80%94%20Team%20LMA%20demo.pdf) y [versión HTML en español](docs/presentacion/burning-activity-calendar.html)

**Goal.** Turn 25 years of NASA FIRMS active-fire detections (MODIS Terra/Aqua, 1 km, since 2000; VIIRS S-NPP / NOAA-20, 375 m, since 2012) into **one consistent burning-activity record** for any area of interest in Argentina, and show it as a **burning activity calendar** in a web app.

**Why.** VIIRS detects several times more hot spots than MODIS for the same fire activity. Concatenating the two records creates an artificial jump in 2012. S-NPP stopped delivering data on 2 Nov 2026 and MODIS Terra/Aqua end in 2027, so the next sensor transition is already here.

## Layout

```
scripts/download_firms.py   FIRMS country-yearly CSVs (no API key needed) -> data/raw/
src/config.py               every decision that can tilt a result (grid, filters, windows)
src/ingest.py               raw CSV -> data/interim/detections.parquet (unified schema, local date, H3 cells)
src/aggregate.py            detections -> hotspots (H3 res-6 cell-days) -> cell x month panel per sensor
src/harmonize.py            MODIS -> VIIRS-scale factors (ratio with shrinkage) + LightGBM model, validation
src/export_web.py           compact data products for the web app -> web/data/
web/                        static web app (map + burning activity calendar)
notebooks/                  narrated analysis (the 2012 jump, validation, examples)
docs/                       method, limitations, submission texts
```

## Run

```bash
pip install -r requirements.txt
python scripts/download_firms.py            # country-yearly CSVs, no key needed
python scripts/download_firms_api.py        # 2026 + NOAA-21 via API (needs firms_key.txt with a FIRMS MAP_KEY)
python -m src.ingest
python -m src.aggregate
python -m src.harmonize
python -m src.export_web
```

## Data

- NASA FIRMS country yearly archives: https://firms.modaps.eosdis.nasa.gov/country/ (MODIS C6.1, VIIRS S-NPP C2, VIIRS NOAA-20 C2)
- NASA FIRMS API (area/csv, SP + NRT) for 2026 and NOAA-21: https://firms.modaps.eosdis.nasa.gov/api/area/
- Boundaries: geoBoundaries ARG ADM0/ADM1 (open)
