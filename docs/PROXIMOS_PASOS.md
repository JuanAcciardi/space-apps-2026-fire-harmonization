# Próximos pasos para entregar (equipo LMA)

Estado al sábado 14/11 ~17:00: pipeline, datos y app están terminados y publicados.
- App: https://juanacciardi.github.io/space-apps-2026-fire-harmonization/
- Repo: https://github.com/JuanAcciardi/space-apps-2026-fire-harmonization
- **Cierre de entrega: domingo 15/11 a las 23:59, hora de la sede local.** Hay que apretar "Submit for Judging"; guardar no alcanza.

Quedan tres pasos. Ninguno requiere correr código.

## Paso 1 — Armar el demo (≤ 7 slides o video ≤ 30 s, en inglés)

Regla de Space Apps: un deck de **7 slides como máximo** (contando título) o un **video de 30 segundos como máximo**. Si se pasa, el proyecto queda fuera del juzgado global. Tiene que estar en un link público sin login (Google Drive, YouTube, GitHub).

- El guion slide por slide está en [demo_slides.md](demo_slides.md).
- Las capturas se sacan de la app con estas URLs (ya abren en la vista correcta):
  - El salto de 2012: `https://juanacciardi.github.io/space-apps-2026-fire-harmonization/?tab=switch`
  - Corrientes 2022 con el registro ingenuo encendido: `.../?aoi=Corrientes&year=2022&raw=1`
  - Mapa del factor k: `.../?layer=k&year=2010`
  - De dónde sale cada número en nov-2026 (la costura S-NPP → NOAA-20): `.../?year=2026&month=10&layer=src`
  - Tablas de validación: `.../?tab=method`
- Slides obligatorias: nombre del equipo (LMA), integrantes, desafío elegido.
- Cuando esté listo, pegar el link en `docs/submission.md` donde dice `[public link to the 7-slide deck or 30 s video]`.

## Paso 2 — Completar los dos huecos de los textos

Todos los textos del formulario están redactados en inglés en [submission.md](submission.md). Faltan sólo:

1. **Ciudad de la sede local** (línea final, `Local event: [city]`).
2. **"Use of Artificial Intelligence"**: hay un borrador entre corchetes. Ajustarlo a lo que realmente pasó. Space Apps pide declarar herramientas de IA usadas; el código fue asistido por Claude (Anthropic) y revisado/corrido por el equipo; LightGBM se usa como estimación de control. No hay imágenes ni video generados.

Opcional si hay tiempo: revisar el nombre del proyecto ("Burning Activity Calendar" es provisorio) en `submission.md`, `web/index.html` y `README.md`.

## Paso 3 — Cargar el formulario y enviar

En la página del proyecto en spaceappschallenge.org, copiar cada sección de `docs/submission.md` en su campo:

| Campo del formulario | De dónde copiar |
|---|---|
| Project Name | sección "Project Name" |
| High-Level Project Summary | sección homónima |
| Link to Project Demo | el link del Paso 1 |
| Link to Final Project | `https://github.com/JuanAcciardi/space-apps-2026-fire-harmonization` (y la app como segundo link dentro del texto) |
| Detailed Project Description | sección homónima |
| NASA Data | sección "NASA Data" |
| Space Agency Partner Data & Other References | sección homónima |
| Use of Artificial Intelligence | sección homónima (ya ajustada en el Paso 2) |

Después: tildar Terms and Conditions y "Confirm All Work is Original", y **Submit for Judging**. Se puede volver a editar y reenviar hasta el cierre; vale la última versión guardada. Los dos integrantes tienen que figurar en la pestaña Members del equipo.

---

## Si hace falta tocar algo

**Ver la app en local** (no necesita Python ni instalación especial, sólo un servidor estático):
```bash
cd web
python -m http.server 8765      # abrir http://localhost:8765
```
Los datos que lee la app ya están en `web/data/` dentro del repo; no hay que regenerar nada para verla o cambiar textos.

**Cambiar textos de la app**: `web/index.html` (títulos, pestañas "The 2012 switch" y "Method"), `web/app.js` (etiquetas de gráficos). Cada `git push` a `main` que toque `web/` redeploya GitHub Pages solo (tarda ~1 minuto; se ve en la pestaña Actions).

**Regenerar datos** (sólo si se cambia el método; ~15 minutos):
```bash
pip install -r requirements.txt
python scripts/download_firms.py        # ~1 GB de CSV, sin clave
python scripts/download_firms_api.py    # 2026 + NOAA-21; necesita firms_key.txt con una MAP_KEY de FIRMS (gratis en firms.modaps.eosdis.nasa.gov/api/map_key)
python -m src.ingest && python -m src.aggregate && python -m src.harmonize && python -m src.export_web
```
`firms_key.txt` está en `.gitignore`: nunca subir la clave.

**Dónde está cada cosa**: ver la tabla de layout en el [README](../README.md) y el método completo en [method.md](method.md).
