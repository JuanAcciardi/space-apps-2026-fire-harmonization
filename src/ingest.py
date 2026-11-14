"""Lee los CSV crudos de FIRMS, unifica el esquema MODIS/VIIRS y escribe data/interim/detections.parquet.

Decisiones:
- Se conservan TODAS las detecciones (sin filtrar) con columnas de calidad; los filtros se aplican al agregar.
- Hora local = UTC-3. local_date es la fecha del calendario de quema (las pasadas nocturnas ~01-05 UTC caen el día anterior local).
- Celdas H3 res 6 (hotspot), 4 (celda de análisis) y 3 (región) calculadas con la extensión h3 de DuckDB.
"""
import duckdb
from src import config as C


def main() -> None:
    C.INTERIM.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    raw = C.RAW.as_posix()
    out = (C.INTERIM / "detections.parquet").as_posix()

    modis = f"""
    SELECT latitude, longitude,
           CASE satellite WHEN 'Terra' THEN 'Terra' WHEN 'T' THEN 'Terra' ELSE 'Aqua' END AS satellite,
           'MODIS' AS instrument,
           acq_date, acq_time,
           brightness AS bright_main, bright_t31 AS bright_aux, scan, track, frp, daynight, type,
           confidence AS confidence_num,
           CASE WHEN confidence < 30 THEN 'l' WHEN confidence < 80 THEN 'n' ELSE 'h' END AS confidence,
           version::VARCHAR AS version
    FROM read_csv('{raw}/modis_*_{C.COUNTRY}.csv', union_by_name=true,
                  types={{'acq_time':'VARCHAR','confidence':'BIGINT','version':'VARCHAR','type':'DOUBLE'}})
    """
    viirs = f"""
    SELECT latitude, longitude,
           CASE satellite WHEN 'N' THEN 'SNPP' WHEN 'N20' THEN 'NOAA20' WHEN 'N21' THEN 'NOAA21' ELSE satellite END AS satellite,
           'VIIRS' AS instrument,
           acq_date, acq_time,
           bright_ti4 AS bright_main, bright_ti5 AS bright_aux, scan, track, frp, daynight, type,
           NULL::BIGINT AS confidence_num,
           lower(confidence)[1:1] AS confidence,
           version::VARCHAR AS version
    FROM read_csv('{raw}/viirs-*_{C.COUNTRY}.csv', union_by_name=true,
                  types={{'acq_time':'VARCHAR','confidence':'VARCHAR','version':'VARCHAR','type':'DOUBLE'}})
    """
    con.execute(f"""
    COPY (
      WITH u AS ({modis} UNION ALL BY NAME {viirs}),
      t AS (
        SELECT *,
               acq_date::TIMESTAMP + INTERVAL (lpad(acq_time,4,'0')[1:2]::INT) HOUR
                                   + INTERVAL (lpad(acq_time,4,'0')[3:4]::INT) MINUTE AS acq_utc
        FROM u)
      SELECT latitude, longitude, satellite, instrument,
             CASE satellite WHEN 'Terra' THEN 'MODIS' WHEN 'Aqua' THEN 'MODIS' ELSE satellite END AS sensor_group,
             acq_utc,
             (acq_utc + INTERVAL ({C.UTC_OFFSET_HOURS}) HOUR)::DATE AS local_date,
             bright_main, bright_aux, scan, track, frp, daynight, coalesce(type,0)::TINYINT AS type,
             confidence, confidence_num, version,
             h3_latlng_to_cell(latitude, longitude, {C.H3_HOTSPOT}) AS h3_6,
             h3_latlng_to_cell(latitude, longitude, {C.H3_CELL}) AS h3_4,
             h3_latlng_to_cell(latitude, longitude, {C.H3_REGION}) AS h3_3
      FROM t
    ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """)
    print(con.execute(f"""
        SELECT sensor_group, satellite, count(*) n, min(local_date) d0, max(local_date) d1,
               round(100.0*avg((type=0)::INT),1) pct_type0, round(100.0*avg((confidence='l')::INT),1) pct_low
        FROM '{out}' GROUP BY 1,2 ORDER BY 1,2""").df().to_string())


if __name__ == "__main__":
    main()
