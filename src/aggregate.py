"""detections.parquet -> hotspots (celda H3 res 6 x día x sensor) -> panel celda res 4 x mes x sensor.

Un "hotspot" es una celda res-6 (~36 km2) con al menos una detección de fuego de vegetación en un día local.
Contar celdas-día y no píxeles elimina la mayor parte de la inflación por tamaño de píxel (1 km vs 375 m).
El panel incluye ceros explícitos cuando el sensor estaba operativo y NULL cuando no lo estaba.
"""
import duckdb
from src import config as C


def main() -> None:
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial;")
    det = (C.INTERIM / "detections.parquet").as_posix()
    types = ",".join(str(t) for t in C.KEEP_TYPES)
    drop_conf = ",".join(f"'{c}'" for c in C.VIIRS_DROP_CONFIDENCE)

    # --- 1. hotspots -------------------------------------------------------------------------
    con.execute(f"""
    CREATE TABLE hotspots AS
    SELECT sensor_group, h3_6, local_date,
           h3_cell_to_parent(h3_6, {C.H3_CELL}) AS h3_4,
           h3_cell_to_parent(h3_6, {C.H3_REGION}) AS h3_3,
           count(*) AS n_det,
           sum(frp) AS frp,
           max(frp) AS frp_max,
           sum((daynight='D')::INT) AS n_day,
           sum((daynight='N')::INT) AS n_night,
           count(DISTINCT satellite) AS n_sats
    FROM '{det}'
    WHERE type IN ({types}) AND confidence NOT IN ({drop_conf})
    GROUP BY 1,2,3
    """)
    con.execute(f"COPY hotspots TO '{(C.PROCESSED/'hotspots.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    # --- 2. celdas res-4 que cubren Argentina + provincia por centroide ----------------------
    adm0 = (C.GEO / "argentina_adm0.geojson").as_posix()
    adm1 = (C.GEO / "provincias_arg.geojson").as_posix()
    con.execute(f"""
    CREATE TABLE cells AS
    WITH g AS (SELECT geom FROM ST_Read('{adm0}')),
    c AS (SELECT DISTINCT unnest(h3_polygon_wkt_to_cells_experimental(ST_AsText(geom), {C.H3_CELL}, 'overlap')) AS h3_4 FROM g)
    SELECT c.h3_4,
           h3_cell_to_lat(c.h3_4) AS lat, h3_cell_to_lng(c.h3_4) AS lon,
           h3_cell_to_parent(c.h3_4, {C.H3_REGION}) AS h3_3,
           h3_cell_area(c.h3_4, 'km^2') AS area_km2,
           p.shapeName AS provincia
    FROM c
    LEFT JOIN ST_Read('{adm1}') p
      ON ST_Within(ST_Point(h3_cell_to_lng(c.h3_4), h3_cell_to_lat(c.h3_4)), p.geom)
    """)
    # celdas con fuego fuera del polígono (costa, islas) se agregan igual
    con.execute(f"""
    INSERT INTO cells
    SELECT DISTINCT h.h3_4, h3_cell_to_lat(h.h3_4), h3_cell_to_lng(h.h3_4), h.h3_3, h3_cell_area(h.h3_4,'km^2'), NULL
    FROM hotspots h ANTI JOIN cells c USING (h3_4)
    """)
    con.execute(f"""
    UPDATE cells SET provincia = (
        SELECT p.shapeName FROM ST_Read('{adm1}') p
        ORDER BY ST_Distance(ST_Point(cells.lon, cells.lat), p.geom) LIMIT 1)
    WHERE provincia IS NULL
    """)
    con.execute(f"COPY cells TO '{(C.PROCESSED/'cells.parquet').as_posix()}' (FORMAT PARQUET)")

    # --- 3. panel celda x mes x sensor con ceros explícitos y NULL fuera de operación ---------
    con.execute(f"""
    CREATE TABLE sensors(sensor_group VARCHAR, start DATE, "end" DATE);
    INSERT INTO sensors VALUES
      ('MODIS',  DATE '{C.SAT_START["Terra"]}',  NULL),
      ('SNPP',   DATE '{C.SAT_START["SNPP"]}',   DATE '{C.SAT_END["SNPP"]}'),
      ('NOAA20', DATE '{C.SAT_START["NOAA20"]}', NULL),
      ('NOAA21', DATE '{C.SAT_START["NOAA21"]}', NULL);
    """)
    con.execute(f"""
    CREATE TABLE panel AS
    WITH months AS (SELECT unnest(generate_series(DATE '{C.MONTH_START}', DATE '{C.MONTH_END}', INTERVAL 1 MONTH))::DATE AS month),
    grid AS (
      SELECT c.h3_4, m.month, s.sensor_group,
             (m.month >= date_trunc('month', s.start) AND (s."end" IS NULL OR m.month <= s."end")) AS active
      FROM cells c CROSS JOIN months m CROSS JOIN sensors s
      WHERE s.sensor_group IN (SELECT DISTINCT sensor_group FROM hotspots)
    ),
    agg AS (
      SELECT h3_4, date_trunc('month', local_date)::DATE AS month, sensor_group,
             count(*) AS hotspots, sum(n_det) AS n_det, sum(frp) AS frp,
             sum(n_day) AS n_day, sum(n_night) AS n_night,
             count(DISTINCT local_date) AS fire_days
      FROM hotspots GROUP BY 1,2,3
    )
    SELECT g.h3_4, g.month, g.sensor_group, g.active,
           CASE WHEN g.active THEN coalesce(a.hotspots,0) END AS hotspots,
           CASE WHEN g.active THEN coalesce(a.n_det,0) END AS n_det,
           CASE WHEN g.active THEN coalesce(a.frp,0) END AS frp,
           CASE WHEN g.active THEN coalesce(a.n_day,0) END AS n_day,
           CASE WHEN g.active THEN coalesce(a.n_night,0) END AS n_night,
           CASE WHEN g.active THEN coalesce(a.fire_days,0) END AS fire_days
    FROM grid g LEFT JOIN agg a USING (h3_4, month, sensor_group)
    """)
    con.execute(f"COPY panel TO '{(C.PROCESSED/'panel_cell_month.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    # --- 4. series diarias por provincia y nacional (para el calendario diario) --------------
    con.execute(f"""
    COPY (
      SELECT c.provincia, h.sensor_group, h.local_date,
             count(*) AS hotspots, sum(n_det) AS n_det, sum(frp) AS frp
      FROM hotspots h JOIN cells c USING (h3_4)
      GROUP BY 1,2,3 ORDER BY 1,2,3
    ) TO '{(C.PROCESSED/'daily_province.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    # --- 5. hotspots diarios por celda res-4 (para calendario diario de un área dibujada) ----
    con.execute(f"""
    COPY (
      SELECT h3_4, sensor_group, local_date, count(*) AS hotspots, sum(n_det) AS n_det, sum(frp) AS frp
      FROM hotspots GROUP BY 1,2,3 ORDER BY 1,2,3
    ) TO '{(C.PROCESSED/'daily_cell.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    print(con.execute("SELECT count(*) celdas, count(DISTINCT provincia) provincias, count(*) FILTER (provincia IS NULL) sin_prov FROM cells").fetchall())
    print(con.execute("""SELECT sensor_group, count(*) filas, sum(hotspots) hotspots, sum(n_det) dets, round(sum(frp)) frp
                         FROM panel GROUP BY 1 ORDER BY 1""").df().to_string())
    print(con.execute("""SELECT year(month) y, sensor_group, sum(hotspots) hs, sum(n_det) det FROM panel
                         WHERE active GROUP BY 1,2 ORDER BY 1,2""").df().pivot(index='y', columns='sensor_group', values='hs').to_string())


if __name__ == "__main__":
    main()
