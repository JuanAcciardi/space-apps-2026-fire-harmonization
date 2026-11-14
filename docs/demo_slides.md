# Demo deck — 7 slides max (Space Apps rule). Speaker notes in italics.

1. **Title.** Burning Activity Calendar — one fire record from MODIS and VIIRS. Team **LMA**: Juan Ignacio Acciardi, Verónica Ana López Marsico, challenge "Harmonization of MODIS and VIIRS Hot Spots" (CONAE). Screenshot of the app.

2. **The problem in one chart.** The "2012 switch" chart: naive joined record jumps +50% in 2012 while MODIS alone falls 30%. *VIIRS sees ~2× the hot spots of MODIS for the same fire. Join them and you invent a fire boom.*

3. **Same unit for every sensor.** Diagram: 1 km MODIS pixel vs cluster of 375 m VIIRS pixels inside one 36 km² H3 cell → both count as ONE hot spot that day. *Counting cells, not pixels, removes most of the inflation before any model.*

4. **Learn the exchange rate.** Map layer "Factor k" + national k by month (1.8 in Jan to 2.7 in May). *Per cell and calendar month, from the 14 years both flew, shrunk towards region and country where fire is sparse. No intercept.*

5. **Does it hold on years it never saw?** Backtest table: fit 2016–25, predict 2012–15 → national totals within 1–6%, 15% per cell; LightGBM variant 13%. Seam test 1.50× → 0.74× (control 0.70×). *Every pre-2012 value ships with a 90% band calibrated on this test.*

6. **The product.** App screenshot for Corrientes 2022: calendar, seasonality, daily calendar, source bar, CSV. *Any province, drawn box or cell. Shareable URLs. Runs on GitHub Pages with no server; 28 MB of binary arrays.*

7. **Why now, what next.** Suomi NPP data ended 2 Nov 2026; MODIS ends 2027. Same code ties NOAA-21 to NOAA-20 and the next sensor to VIIRS. Next: near-real-time 2026 via FIRMS API, CONAE SAOCOM/burned area cross-check, Latin America coverage. Links: github.com/JuanAcciardi/space-apps-2026-fire-harmonization · juanacciardi.github.io/space-apps-2026-fire-harmonization
