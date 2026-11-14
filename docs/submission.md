# Project page texts (Space Apps submission form)

Fill the gaps marked `[...]`. Everything must be in English. Demo: slide deck of 7 slides or fewer, or a video of 30 seconds or fewer, on a public link.

## Project Name

**Burning Activity Calendar** — one fire record from MODIS and VIIRS for Argentina *(working title; change freely)*

## High-Level Project Summary

Argentina has been watched for fire by two generations of NASA satellites: MODIS on Terra and Aqua since 2000 (1 km pixels) and VIIRS on Suomi NPP and NOAA-20 since 2012 (375 m pixels). VIIRS sees smaller and cooler fires, so it records about twice as many hot spots as MODIS for the same burning. Joined end to end, the record shows a +50% jump in 2012 that never happened on the ground. We built a reproducible pipeline and a web application that harmonize 6.5 million NASA FIRMS detections (2001 to 14 November 2026) into one consistent record on the VIIRS scale and present it as a burning activity calendar for any area of interest: a province, a drawn box or a single ~1,800 km² cell. The exchange rate between sensors is learned per cell and calendar month from the 14 years both flew, validated by predicting years the fit never saw, and every modelled value carries a calibrated 90% band. It matters now because Suomi NPP stopped delivering data on 2 November 2026 and MODIS ends in 2027: the next sensor seam is already here, and fire agencies, researchers and land managers need records that survive it.

## Link to Project Demo

`[public link to the 7-slide deck or 30 s video]` (script: docs/demo_slides.md)

## Link to Final Project

https://github.com/JuanAcciardi/space-apps-2026-fire-harmonization · https://juanacciardi.github.io/space-apps-2026-fire-harmonization/

## Detailed Project Description

**What it does.** The web app lets anyone pick an area of Argentina and see (1) hot spots per year by sensor and the harmonized series with its uncertainty band, (2) a burning activity calendar (year × month heat map) with a toggle that shows the naive joined record and its artificial 2012 jump, (3) the seasonal normal versus the selected year with rank and anomaly, (4) a day-by-day calendar for provinces and the whole country, (5) the exact source of every number (S-NPP observed, NOAA-20 scaled, MODIS × factor, Terra-only bridged) and (6) a table and CSV download. A map layer shows the factor k itself and where each value comes from.

**How it works.**
1. *Same unit for every sensor.* Detections are filtered to presumed vegetation fires (FIRMS `type = 0`, confidence not low), assigned to a local-time day (UTC−3) and an H3 resolution-6 cell (~36 km²). One cell-day with fire is one *hot spot* regardless of pixel size. Counting cells instead of pixels removes most of the 1 km vs 375 m inflation before any statistics.
2. *Learn the exchange rate.* For each H3 resolution-4 cell (~1,770 km²) and calendar month, k = S-NPP hot spots / MODIS hot spots over 2012–2025, with hierarchical shrinkage toward the region and the country where fire is sparse. The ratio has no intercept, so zero MODIS fire stays zero. The same is done for fire radiative power.
3. *Bridge the record.* Feb 2012–Oct 2026 is S-NPP as observed; from November 2026 (S-NPP ended on 2 Nov 2026) and in any month without S-NPP the value is NOAA-20 scaled by its own factor (0.97), with NOAA-21 behind it. The record therefore already crosses the sensor seam that every FIRMS user faces this month. 2001–2011 is MODIS × k. Nov 2000–Jun 2002, when only Terra flew, is first lifted to Terra+Aqua with a regional monthly factor learned in 2003–2011.
4. *Validate backwards.* Factors fitted on 2016–2025 only are used to predict S-NPP in 2012–2015. National totals come out within 1–6% per year; per-cell four-year totals have a fire-weighted error of 15%. A LightGBM Poisson model with MODIS counts, FRP, day/night share, fire days, month and location was trained the same way as a second estimate (13%). The 2012 seam test: naive record +50%, harmonized −26%, MODIS alone −30%.
5. *Say what cannot be known.* No VIIRS flew before 2012, so pre-2012 values assume each place's ratio stayed stable. They carry a 90% band calibrated on the backtest; days before 2012 are indicative only.

**Tools.** Python 3.11, DuckDB with the H3 and spatial extensions, pandas, LightGBM; a static front end with Leaflet, h3-js and Plotly reading compact binary arrays (28 MB) so it runs on GitHub Pages with no server. Every decision that can tilt a result lives in one config file and the whole pipeline reruns in minutes.

**Benefits and what it aims to achieve.** A consistent 25-year record lets emergency services and provinces compare this season against a real normal, lets scientists study trends without instrument artefacts, and gives land managers a per-area calendar of when and how much fire is typical. The method is sensor-agnostic: the same code will tie NOAA-21 to NOAA-20, and the next sensor to VIIRS.

## NASA Data

- NASA FIRMS country-yearly active fire archives for Argentina: MODIS Collection 6.1 (Terra + Aqua, 2000–2025), VIIRS S-NPP Collection 2 375 m (2012–2025), VIIRS NOAA-20 Collection 2 375 m (2018–2025). https://firms.modaps.eosdis.nasa.gov/country/
- NASA FIRMS API (area/csv): MODIS, VIIRS S-NPP, NOAA-20 and NOAA-21 standard-processing and near-real-time detections for 2026 up to 14 November, and the full NOAA-21 record since March 2023. https://firms.modaps.eosdis.nasa.gov/api/area/
- MODIS and VIIRS active fire user guides (algorithm and confidence definitions). https://www.earthdata.nasa.gov/data/tools/firms
- NASA Earthdata notice on the end of Suomi NPP data delivery (2 Nov 2026) and the MODIS-to-VIIRS transition.

## Space Agency Partner Data & Other References

- geoBoundaries (open, CC BY 4.0): Argentina ADM0 and ADM1 boundaries.
- Uber H3 hexagonal grid; DuckDB; LightGBM; Leaflet; Plotly; Esri World Light Gray basemap tiles.
- Schroeder, W. et al. (2014), *The New VIIRS 375 m active fire detection data product*, Remote Sensing of Environment.
- `[CONAE resources if used]`

## Use of Artificial Intelligence

`[Describe honestly: e.g. "We used Claude (Anthropic) as a coding assistant to draft pipeline and front-end code, which the team reviewed, ran and modified. The idea, method choices and validation design are the team's. LightGBM is used as a machine-learning cross-check of the ratio method; its outputs are shown as a variant, never as ground truth. No generated images or video."]`

## Team

**LMA** · Juan Ignacio Acciardi, Verónica Ana López Marsico · Local event: `[city]`
