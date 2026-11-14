# Official challenge text (NASA Space Apps 2026, written by CONAE)

**Harmonization of MODIS and VIIRS Hot Spots**

> Understanding how burning activity is distributed across our planet over time, including wildfires and agricultural burns intense enough to be detected by satellite sensors, enables us to anticipate critical periods, guide monitoring efforts, and improve fire response. Satellites have tracked active fire hotspots for more than two decades, but the record is split across sensors whose data cannot be compared directly, leaving fire managers without a consistent picture of when and where burning has occurred. Your challenge is to build a web application that harmonizes these records into a burning activity calendar based on active fire hotspots, enabling early warning and emergency responders, scientists, and land managers to examine historical fire patterns, unusual conditions, and critical periods within a selected area of interest.

## How the app answers each phrase

| Challenge phrase | Where it lives in the app |
|---|---|
| harmonizes these records | ratio-with-shrinkage factors per cell × month, Terra-only bridge, NOAA-20 tie; "Method & validation" tab |
| burning activity calendar | year × month heat map and day × year heat map, harmonized |
| selected area of interest | province list, drawn box, single or multi-cell click; shareable URL |
| historical fire patterns | hot spots per year by sensor + harmonized with 90% band; seasonality bars |
| unusual conditions | hero tiles: value vs median normal, rank of N years, anomaly % |
| critical periods | critical-period tile: the shortest run of months holding most of the fire |
| early warning / responders / land managers | daily calendar, CSV download, source of every number |
