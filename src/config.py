"""Configuración central del pipeline. Toda decisión que afecte resultados vive acá."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
GEO = ROOT / "data" / "geo"
WEB_DATA = ROOT / "web" / "data"

COUNTRY = "Argentina"
UTC_OFFSET_HOURS = -3          # Argentina no tiene horario de verano

# Resoluciones H3
H3_HOTSPOT = 6                 # celda de "hotspot" (~36 km2): 1 celda-día con fuego = 1 hotspot, sin importar el sensor
H3_CELL = 4                    # celda de agregación / factores / mapa (~1.770 km2)
H3_REGION = 3                  # nivel de encogimiento (shrinkage) de los factores (~12.400 km2)

# Filtros de detecciones
KEEP_TYPES = (0,)              # 0 = presunto fuego de vegetación; 1 volcán, 2 fuente estática, 3 offshore
MODIS_MIN_CONFIDENCE = 30      # descarta confianza "baja" (<30) según guía de usuario MODIS C6.1
VIIRS_DROP_CONFIDENCE = ("l",) # descarta 'low'

# Ventanas de disponibilidad por satélite (para distinguir "sin dato" de "cero fuego")
SAT_START = {
    "Terra": "2000-11-01",
    "Aqua": "2002-07-04",
    "SNPP": "2012-01-20",
    "NOAA20": "2018-01-01",
    "NOAA21": "2023-03-01",
}
SAT_END = {"SNPP": "2026-11-02"}

# Grupos de sensor que se comparan
SENSOR_GROUP = {"Terra": "MODIS", "Aqua": "MODIS", "SNPP": "SNPP", "NOAA20": "NOAA20", "NOAA21": "NOAA21"}

# Período de solapamiento usado para ajustar factores MODIS -> VIIRS
OVERLAP_START, OVERLAP_END = "2012-02-01", "2025-12-31"
# Años de validación hacia atrás (se ajusta sin ellos y se predice sobre ellos)
BACKTEST_YEARS = (2012, 2013, 2014, 2015)

MONTH_START, MONTH_END = "2001-01-01", "2026-11-01"
LAST_DAY = "2026-11-14"           # último día con datos (NRT); el último mes es parcial
