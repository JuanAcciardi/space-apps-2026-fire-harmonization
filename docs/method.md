# Method, validation and limitations

Team LMA · NASA Space Apps Challenge 2026 · *Harmonization of MODIS and VIIRS Hot Spots* (CONAE)

## 1. Why the records cannot be joined as they are

| | MODIS (Terra 2000–, Aqua 2002–) | VIIRS (S-NPP 2012–Nov 2026, NOAA-20 2018–, NOAA-21 2023–) |
|---|---|---|
| Pixel at nadir | 1 km | 375 m |
| Overpasses (local time) | 10:30 / 22:30 (Terra), 13:30 / 01:30 (Aqua) | 13:30 / 01:30 |
| Sensitivity | misses small and cool fires | detects fires several times smaller |
| Confidence field | 0–100 | low / nominal / high |

For the same burning, VIIRS reports more pixels (finer grid) **and** more fires (higher sensitivity). In Argentina, after collapsing pixels into cell-days, S-NPP still records **1.8× (January) to 2.7× (May)** the MODIS count. A record that is MODIS until 2011 and VIIRS afterwards therefore shows a +50% jump in 2012 that the fires never made.

## 2. Pipeline (all code in `src/`, every tunable in `src/config.py`)

1. **Ingest.** FIRMS country-yearly CSVs (no key) plus the FIRMS API for 2026 and NOAA-21. One schema for both instruments; acquisition time converted to local date (UTC−3); H3 cells at resolutions 6, 4 and 3 computed in DuckDB.
2. **Filter.** `type = 0` (presumed vegetation fire; drops volcanoes, gas flares and other static sources) and confidence not *low* (MODIS < 30). Near-real-time rows have no `type` field and are treated as vegetation fire; they cover only the last ~3 months.
3. **Hot spot.** One H3 res-6 cell (~36 km²) with ≥ 1 detection on one local day, per sensor group (MODIS = Terra+Aqua, S-NPP, NOAA-20, NOAA-21). Fire radiative power (FRP) is summed per cell-day. Counting cell-days instead of pixels removes most of the pixel-size effect and makes the unit identical across sensors.
4. **Panel.** Hot spots, detections, FRP, day/night split and fire days per res-4 cell (~1,770 km², 2,028 cells cover Argentina) × month × sensor group, with explicit zeros while a sensor was flying and NULL when it was not.
5. **Factors.** For each cell *c* and calendar month *m*:
   k(c,m) = (V(c,m) + τ₁·k(r,m)) / (M(c,m) + τ₁), with k(r,m) = (V(r,m) + τ₂·k(nat,m)) / (M(r,m) + τ₂)
   where V and M are S-NPP and MODIS hot spots summed over 2012–2025, *r* the parent res-3 region, τ₁ = 30 and τ₂ = 100 pseudo-hot spots. Cells with little fire inherit their region's ratio; regions with little fire inherit the national one. The same is done for FRP. There is no intercept, so zero MODIS fire maps to zero.
6. **Terra-only bridge.** Before Aqua (Nov 2000–Jun 2002) MODIS saw only the morning/evening overpasses. The factor (Terra+Aqua cell-days)/(Terra cell-days) per region × calendar month, learned in 2003–2011, lifts those months to the Terra+Aqua level before k is applied. It ranges 1.8 (Dec–Jan) to 4.3 (June) nationally.
7. **Reference scale and sensor ties.** The harmonized record is on the S-NPP scale. NOAA-20 is tied to S-NPP by a single ratio over 2018–2025 (0.97 for hot spots, 1.02 for FRP; the yearly ratios sit between 1.00 and 1.10). NOAA-21 is tied the same way over 2023–2025. The harmonized value for a cell-month is, in order of preference: S-NPP observed (Feb 2012–Oct 2026), NOAA-20 × k₂₀, NOAA-21 × k₂₁, MODIS × bridge × k.
8. **Second estimate.** A LightGBM Poisson regression predicts S-NPP hot spots from MODIS hot spots, detections, FRP, fire days, night share, FRP per detection, calendar month, latitude, longitude and the cell's MODIS climatology. It is shown as a variant, not as the main record.

## 3. Validation

**Backtest.** Factors are fitted on 2016–2025 only and used to predict S-NPP in 2012–2015, years the fit never saw.

| Level | Raw MODIS | Ratio × k | LightGBM |
|---|---|---|---|
| National total, 4 years | −52% | 0.0% | +1.7% |
| National total, worst single year | −55% | −6% (2014) | +8% (2014) |
| Cell × month weighted abs. error | 61% | 49% | 44% |
| Cell 4-year total, fire-weighted abs. error (cells ≥ 20 hot spots) | – | 15% | 13% |

**Seam test.** Mean of 2013–2015 over mean of 2009–2011, Argentina: naive joined record 1.50×, harmonized 0.74×, MODIS alone (same satellites on both sides) 0.70×, LightGBM variant 0.78×. The harmonized record moves with the control; the naive one does not.

**Sensor ties.** NOAA-20 / S-NPP by year: 1.00–1.10 (hot spots), 0.90–1.05 (FRP).

**Uncertainty.** For every modelled aggregate (any set of cells, any month or year) the app looks up the 5th and 95th percentile of observed/predicted in the backtest for aggregates of similar predicted size. A province-year of ~5,000 hot spots carries roughly ±20%; a single cell-month of 5 hot spots carries a band from 0 to about 2.3×. Bands are shown in the chart, the tiles and the CSV.

## 4. Limitations, stated plainly

- **No VIIRS flew before 2012.** The pre-2012 record assumes each place's VIIRS/MODIS ratio stayed as measured in 2012–2025. Land-use change, different fire regimes or agricultural practice could shift it. The backtest shows the ratios are stable across 2012–2025, not that they held in 2003.
- **Days before 2012 are indicative.** Daily values are MODIS days scaled by the month's province factor: they preserve the monthly total but the day-to-day pattern is what MODIS saw (and MODIS night overpasses see less).
- **Partial months and the Nov 2026 seam.** S-NPP ended on 2 Nov 2026; November 2026 is NOAA-20 scaled, and the month is incomplete. Near-real-time data lack the static-source flag.
- **FRP is not harmonized as well as counts.** VIIRS 375 m FRP per fire is systematically lower than MODIS FRP for the same fire (k_FRP 0.6–1.0), so FRP comparisons across the seam are weaker than hot-spot comparisons.
- **Clouds and overpass gaps.** Absence of detection is not absence of fire. The record is of *detected* burning.
- **Grid scale.** 36 km² hot spots and 1,770 km² cells are right for calendars and regional patterns, not for mapping individual fire perimeters.
- **Argentina only, by design.** The method is country-agnostic; the FIRMS country archives exist for every country and the pipeline reruns by changing one config value.

## 5. Reproducibility

```
pip install -r requirements.txt
python scripts/download_firms.py        # ~1 GB of CSV, no key
python scripts/download_firms_api.py    # 2026 + NOAA-21, needs a FIRMS MAP_KEY in firms_key.txt
python -m src.ingest && python -m src.aggregate && python -m src.harmonize && python -m src.export_web
```

Runs in about ten minutes on a laptop. Outputs: `data/processed/*.parquet`, `data/processed/validation.json`, `web/data/*` (binary arrays read by the static app).
