"""Exporta productos compactos para la web app estática -> web/data/

Formato: arrays binarios little-endian (Int16 / Float32 / Uint8) de tamaño [n_celdas x n_meses]
o [n_provincias+1 x n_dias] (la última fila es el total nacional). -1 = sin dato (sensor inactivo).
meta.json describe todo: meses, celdas (índice H3 como string), provincias, series, validación.
"""
import json
import shutil
import numpy as np
import pandas as pd
import duckdb
from src import config as C

NA = -1


def to_matrix(df, row_key, row_index, col_key, col_index, val, dtype, scale=1.0, na=NA):
    mat = np.full((len(row_index), len(col_index)), na, dtype=dtype)
    r = df[row_key].map(row_index)
    c = df[col_key].map(col_index)
    ok = r.notna() & c.notna() & df[val].notna()
    v = df.loc[ok, val].to_numpy(dtype=float) * scale
    if np.issubdtype(np.dtype(dtype), np.integer):
        v = np.clip(np.rint(v), np.iinfo(dtype).min + 1, np.iinfo(dtype).max)
    mat[r[ok].astype(int).to_numpy(), c[ok].astype(int).to_numpy()] = v.astype(dtype)
    return mat


def main():
    out = C.WEB_DATA
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    P = C.PROCESSED.as_posix()

    cells = con.execute(f"SELECT h3_4, h3_h3_to_string(h3_4) h, lat, lon, provincia, area_km2 FROM '{P}/cells.parquet' ORDER BY h3_4").df()
    h = con.execute(f"SELECT * FROM '{P}/harmonized_cell_month.parquet'").df()
    h["month"] = pd.to_datetime(h.month)
    months = pd.date_range(C.MONTH_START, C.MONTH_END, freq="MS")
    month_index = {m: i for i, m in enumerate(months)}
    cell_index = {c: i for i, c in enumerate(cells.h3_4)}
    provinces = sorted(cells.provincia.dropna().unique().tolist())
    prov_index = {p: i for i, p in enumerate(provinces)}
    cells["p"] = cells.provincia.map(prov_index).fillna(-1).astype(int)

    series = {}

    def dump(name, mat, scale=1.0, desc=""):
        fn = f"{name}.bin"
        mat.astype(mat.dtype.newbyteorder("<")).tofile(out / fn)
        series[name] = {"file": fn, "dtype": str(mat.dtype), "shape": list(mat.shape), "scale": scale, "na": NA, "desc": desc}

    # ----- celda x mes -----------------------------------------------------------------------
    for col, name, dt, sc, desc in [
        ("hotspots_MODIS", "hs_modis", np.int16, 1, "MODIS Terra+Aqua hotspots (res-6 cell-days), raw"),
        ("hotspots_SNPP", "hs_snpp", np.int16, 1, "VIIRS S-NPP hotspots, raw"),
        ("hotspots_NOAA20", "hs_noaa20", np.int16, 1, "VIIRS NOAA-20 hotspots, raw"),
        ("harm_hotspots", "hs_harm", np.int16, 10, "harmonized hotspots on S-NPP scale (ratio method), x10"),
        ("harm_hotspots_lgbm", "hs_lgbm", np.int16, 10, "harmonized hotspots, LightGBM variant, x10"),
        ("harm_lo", "hs_lo", np.int16, 10, "5% quantile band for modelled months, x10"),
        ("harm_hi", "hs_hi", np.int16, 10, "95% quantile band for modelled months, x10"),
        ("frp_MODIS", "frp_modis", np.float32, 1, "MODIS FRP sum (MW), raw"),
        ("frp_SNPP", "frp_snpp", np.float32, 1, "S-NPP FRP sum (MW), raw"),
        ("frp_NOAA20", "frp_noaa20", np.float32, 1, "NOAA-20 FRP sum (MW), raw"),
        ("harm_frp", "frp_harm", np.float32, 1, "harmonized FRP on S-NPP scale (MW)"),
        ("n_det_MODIS", "det_modis", np.int32, 1, "MODIS raw detections (pixels)"),
        ("n_det_SNPP", "det_snpp", np.int32, 1, "S-NPP raw detections (pixels)"),
        ("n_det_NOAA20", "det_noaa20", np.int32, 1, "NOAA-20 raw detections (pixels)"),
    ]:
        if col not in h.columns:
            continue
        dump(name, to_matrix(h, "h3_4", cell_index, "month", month_index, col, dt, sc), sc, desc)
    src_code = {"SNPP observed": 1, "NOAA20 scaled": 2, "MODIS x k": 3, "MODIS Terra-only bridged x k": 4}
    h["src_code"] = h.source.map(src_code).fillna(0)
    dump("src", to_matrix(h, "h3_4", cell_index, "month", month_index, "src_code", np.uint8, 1, na=0), 1,
         "source of harmonized value: " + ", ".join(f"{v}={k}" for k, v in src_code.items()))

    # ----- provincia x día (+ nacional) -------------------------------------------------------
    days = pd.date_range(C.MONTH_START, pd.Timestamp(C.MONTH_END) + pd.offsets.MonthEnd(0), freq="D")
    day_index = {d: i for i, d in enumerate(days)}
    dp = con.execute(f"SELECT * FROM '{P}/daily_province.parquet'").df()
    dp["local_date"] = pd.to_datetime(dp.local_date)
    nat = dp.groupby(["sensor_group", "local_date"], as_index=False)[["hotspots", "n_det", "frp"]].sum()
    nat["provincia"] = "__national__"
    dp = pd.concat([dp, nat], ignore_index=True)
    rows = provinces + ["__national__"]
    row_index = {p: i for i, p in enumerate(rows)}
    # ventanas de actividad: cero explícito dentro de la ventana
    windows = {"MODIS": (C.SAT_START["Terra"], None), "SNPP": (C.SAT_START["SNPP"], C.SAT_END["SNPP"]), "NOAA20": (C.SAT_START["NOAA20"], None)}
    for sg in ["MODIS", "SNPP", "NOAA20"]:
        d = dp[dp.sensor_group == sg]
        mat = to_matrix(d, "provincia", row_index, "local_date", day_index, "hotspots", np.int16)
        s, e = windows[sg]
        active = (days >= pd.Timestamp(s)) & ((days <= pd.Timestamp(e)) if e else True)
        mat[:, active & np.all(mat == NA, axis=0)] = 0
        mat[:, ~active] = NA
        dump(f"daily_hs_{sg.lower()}", mat, 1, f"{sg} daily hotspots by province (last row = national)")

    # diario armonizado: escala MODIS diario con el factor mensual provincial implícito en el registro armonizado
    hm = h.merge(cells[["h3_4", "provincia"]], on="h3_4")
    hm_nat = hm.assign(provincia="__national__")
    pm = pd.concat([hm, hm_nat]).groupby(["provincia", "month"], as_index=False)[["hotspots_MODIS", "harm_hotspots", "hotspots_SNPP"]].sum(min_count=1)
    pm["factor"] = np.where(pm.hotspots_MODIS > 0, pm.harm_hotspots / pm.hotspots_MODIS, np.nan)
    pm["use_snpp"] = pm.hotspots_SNPP.notna()
    daily_harm = np.full((len(rows), len(days)), np.nan, dtype=np.float32)
    modis_d = np.fromfile(out / "daily_hs_modis.bin", dtype="<i2").reshape(len(rows), len(days)).astype(float)
    snpp_d = np.fromfile(out / "daily_hs_snpp.bin", dtype="<i2").reshape(len(rows), len(days)).astype(float)
    n20_d = np.fromfile(out / "daily_hs_noaa20.bin", dtype="<i2").reshape(len(rows), len(days)).astype(float)
    k_n20 = json.load(open(C.PROCESSED / "validation.json"))["noaa20_to_snpp_factor"]["hotspots"]
    month_of_day = pd.DatetimeIndex(days).to_period("M").to_timestamp()
    for _, r in pm.iterrows():
        ri = row_index.get(r.provincia)
        if ri is None:
            continue
        cols = np.where(month_of_day == r.month)[0]
        if r.use_snpp:
            v = snpp_d[ri, cols]
            # días sin S-NPP pero con NOAA-20 (cortes del sensor): NOAA-20 escalado
            v = np.where((v <= 0) & (n20_d[ri, cols] > 0), n20_d[ri, cols] * k_n20, v)
            daily_harm[ri, cols] = np.where(v < 0, np.nan, v)
        elif not np.isnan(r.factor):
            daily_harm[ri, cols] = np.where(modis_d[ri, cols] < 0, np.nan, modis_d[ri, cols] * r.factor)
        else:
            daily_harm[ri, cols] = np.where(modis_d[ri, cols] < 0, np.nan, 0.0)
    daily_harm = np.where(np.isnan(daily_harm), NA, daily_harm).astype(np.float32)
    dump("daily_hs_harm", daily_harm, 1, "harmonized daily hotspots by province (S-NPP scale; pre-2012 = MODIS daily x monthly province factor)")

    # ----- meta ----------------------------------------------------------------------------------
    val = json.load(open(C.PROCESSED / "validation.json", encoding="utf-8"))
    meta = {
        "generated": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "country": C.COUNTRY,
        "months": [m.strftime("%Y-%m") for m in months],
        "days_start": days[0].strftime("%Y-%m-%d"), "n_days": len(days),
        "cells": [{"h": r.h, "lat": round(r.lat, 4), "lon": round(r.lon, 4), "p": int(r.p), "a": round(r.area_km2)} for r in cells.itertuples()],
        "provinces": provinces,
        "daily_rows": rows,
        "series": series,
        "h3_res": {"hotspot": C.H3_HOTSPOT, "cell": C.H3_CELL, "region": C.H3_REGION},
        "filters": {"types": list(C.KEEP_TYPES), "modis_min_confidence": C.MODIS_MIN_CONFIDENCE, "viirs_drop": list(C.VIIRS_DROP_CONFIDENCE)},
        "sensor_windows": {"MODIS": [C.SAT_START["Terra"], None], "SNPP": [C.SAT_START["SNPP"], C.SAT_END["SNPP"]], "NOAA20": [C.SAT_START["NOAA20"], None]},
        "validation": {k: val[k] for k in ["noaa20_to_snpp_factor", "noaa20_over_snpp_by_year", "backtest_2012_2015",
                                           "seam_2012_national", "k_national_by_month", "k_frp_national_by_month",
                                           "terra_only_bridge_national_by_month", "aggregate_uncertainty_lookup", "national_annual"]},
    }
    with open(out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, separators=(",", ":"))
    shutil.copy(C.GEO / "provincias_arg.geojson", out / "provincias.geojson")
    total = sum(f.stat().st_size for f in out.iterdir())
    print(f"{len(cells)} celdas x {len(months)} meses; {len(rows)} filas diarias x {len(days)} días; {total/1e6:.1f} MB en {out}")
    for k, v in series.items():
        print(f"  {k:16s} {v['dtype']:8s} {v['shape']}")


if __name__ == "__main__":
    main()
