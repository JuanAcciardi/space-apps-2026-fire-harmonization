"""Armonización MODIS -> escala VIIRS (S-NPP) por celda H3 res 4 x mes.

Métodos:
  A) RATIO: k = VIIRS/MODIS por (celda, mes calendario) sobre el solapamiento, con encogimiento
     jerárquico celda -> región (h3 res 3) -> nacional (pseudo-conteo TAU). Sin intercepto: cero MODIS => cero.
  B) LGBM: regresión Poisson que predice hotspots SNPP del mes a partir de MODIS (hotspots, detecciones,
     FRP, día/noche, días con fuego), mes, lat/lon y climatología MODIS de la celda.
Puente Terra-only (2000-11 .. 2002-06): factor (Terra+Aqua)/Terra por región x mes, ajustado 2003-2011.
Validación: backtest hacia atrás (ajuste 2016-2025, predicción 2012-2015) y prueba de continuidad en 2012.
Salida: data/processed/harmonized_cell_month.parquet + data/processed/validation.json
"""
import json
import numpy as np
import pandas as pd
import duckdb
import lightgbm as lgb
from src import config as C

TAU_CELL = 30.0     # pseudo-conteo de hotspots MODIS para encoger celda -> región
TAU_REGION = 100.0  # región -> nacional
REF = "SNPP"        # escala de referencia


def ratio_factors(panel, cells, years):
    """Factores k(h3_4, mes_cal) para hotspots y FRP usando los años dados del solapamiento."""
    p = panel[(panel.sensor_group.isin(["MODIS", REF])) & (panel.month.dt.year.isin(years)) & panel.active]
    w = p.pivot_table(index=["h3_4", "month"], columns="sensor_group", values=["hotspots", "frp"]).dropna()
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index().merge(cells[["h3_4", "h3_3"]], on="h3_4")
    w["mcal"] = w.month.dt.month
    out = {}
    for var in ["hotspots", "frp"]:
        num, den = f"{var}_{REF}", f"{var}_MODIS"
        nat = w.groupby(["mcal"], as_index=False)[[num, den]].sum()
        nat["r"] = nat[num] / nat[den].clip(lower=1e-9)
        reg = (w.groupby(["h3_3", "mcal"], as_index=False)[[num, den]].sum()
                .merge(nat[["mcal", "r"]].rename(columns={"r": "r_parent"}), on="mcal"))
        reg["r"] = (reg[num] + TAU_REGION * reg["r_parent"]) / (reg[den] + TAU_REGION)
        cel = (w.groupby(["h3_4", "h3_3", "mcal"], as_index=False)[[num, den]].sum()
                .merge(reg[["h3_3", "mcal", "r"]].rename(columns={"r": "r_parent"}), on=["h3_3", "mcal"]))
        cel["r"] = (cel[num] + TAU_CELL * cel["r_parent"]) / (cel[den] + TAU_CELL)
        out[var] = cel[["h3_4", "mcal", "r"]].rename(columns={"r": f"k_{var}"})
        out[f"{var}_national"] = nat[["mcal", "r"]].rename(columns={"r": f"k_{var}"})
    return out


def lgbm_features(panel, cells):
    m = panel[(panel.sensor_group == "MODIS") & panel.active].copy()
    m = m.merge(cells[["h3_4", "lat", "lon"]], on="h3_4")
    m["mcal"] = m.month.dt.month
    m["year"] = m.month.dt.year
    clim = m.groupby(["h3_4", "mcal"])["hotspots"].mean().rename("modis_clim").reset_index()
    m = m.merge(clim, on=["h3_4", "mcal"])
    m["log_hs"] = np.log1p(m.hotspots)
    m["night_share"] = m.n_night / (m.n_day + m.n_night).clip(lower=1)
    m["frp_per_det"] = m.frp / m.n_det.clip(lower=1)
    feats = ["hotspots", "n_det", "frp", "fire_days", "night_share", "frp_per_det", "mcal", "lat", "lon", "modis_clim", "log_hs"]
    return m, feats


def fit_lgbm(X, y):
    params = dict(objective="poisson", learning_rate=0.05, num_leaves=31, min_data_in_leaf=50,
                  feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=7)
    return lgb.train(params, lgb.Dataset(X, y), num_boost_round=600)


def metrics(y, yhat, name):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    return {"method": name,
            "total_bias_pct": round(100 * (yhat.sum() / max(y.sum(), 1e-9) - 1), 2),
            "wape_pct": round(100 * np.abs(yhat - y).sum() / max(y.sum(), 1e-9), 1),
            "rmse": round(float(np.sqrt(np.mean((yhat - y) ** 2))), 2),
            "n_rows": int(len(y)), "n_rows_fire": int((y > 0).sum())}


def main():
    con = duckdb.connect()
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    panel = con.execute(f"SELECT * FROM '{(C.PROCESSED/'panel_cell_month.parquet').as_posix()}'").df()
    cells = con.execute(f"SELECT * FROM '{(C.PROCESSED/'cells.parquet').as_posix()}'").df()
    panel["month"] = pd.to_datetime(panel.month)
    val = {}

    # ---------- puente Terra-only -----------------------------------------------------------
    det = (C.INTERIM / "detections.parquet").as_posix()
    types = ",".join(map(str, C.KEEP_TYPES))
    ta = con.execute(f"""
      WITH h AS (
        SELECT h3_cell_to_parent(h3_6,{C.H3_REGION}) h3_3, month(local_date) mcal, local_date, h3_6,
               max((satellite='Terra')::INT) terra
        FROM '{det}' WHERE sensor_group='MODIS' AND type IN ({types}) AND confidence<>'l'
              AND local_date BETWEEN DATE '2003-01-01' AND DATE '2011-12-31'
        GROUP BY 1,2,3,4)
      SELECT h3_3, mcal, count(*) both_hs, sum(terra) terra_hs FROM h GROUP BY 1,2""").df()
    nat_ta = ta.groupby("mcal", as_index=False)[["both_hs", "terra_hs"]].sum()
    nat_ta["r_parent"] = nat_ta.both_hs / nat_ta.terra_hs
    ta = ta.merge(nat_ta[["mcal", "r_parent"]], on="mcal")
    ta["k_terra"] = (ta.both_hs + TAU_REGION * ta.r_parent) / (ta.terra_hs + TAU_REGION)
    val["terra_only_bridge_national_by_month"] = {int(k): float(v) for k, v in zip(nat_ta.mcal, (nat_ta.both_hs / nat_ta.terra_hs).round(3))}

    # ---------- NOAA20 vs SNPP ----------------------------------------------------------------
    ov = panel[panel.sensor_group.isin(["SNPP", "NOAA20"]) & panel.active & (panel.month >= "2018-04-01")]
    pv = ov.pivot_table(index=["h3_4", "month"], columns="sensor_group", values=["hotspots", "frp"]).dropna()
    pv.columns = [f"{a}_{b}" for a, b in pv.columns]
    pv = pv.reset_index()
    by_year = pv.groupby(pv.month.dt.year).sum(numeric_only=True)
    val["noaa20_over_snpp_by_year"] = {
        "hotspots": {int(k): float(v) for k, v in (by_year.hotspots_NOAA20 / by_year.hotspots_SNPP).round(3).items()},
        "frp": {int(k): float(v) for k, v in (by_year.frp_NOAA20 / by_year.frp_SNPP).round(3).items()}}
    k_n20 = pv.hotspots_SNPP.sum() / pv.hotspots_NOAA20.sum()
    k_n20_frp = pv.frp_SNPP.sum() / pv.frp_NOAA20.sum()
    val["noaa20_to_snpp_factor"] = {"hotspots": round(float(k_n20), 4), "frp": round(float(k_n20_frp), 4)}

    # ---------- backtest: ajustar 2016-2025, predecir 2012-2015 -----------------------------
    overlap_years = list(range(2012, 2026))
    fit_years = [y for y in overlap_years if y not in C.BACKTEST_YEARS]
    fac_bt = ratio_factors(panel, cells, fit_years)
    m, feats = lgbm_features(panel, cells)
    tgt = (panel[(panel.sensor_group == REF) & panel.active][["h3_4", "month", "hotspots", "frp"]]
           .rename(columns={"hotspots": "y_hs", "frp": "y_frp"}))
    m = m.merge(tgt, on=["h3_4", "month"], how="inner")
    m = m.merge(fac_bt["hotspots"], on=["h3_4", "mcal"]).merge(fac_bt["frp"], on=["h3_4", "mcal"])
    m["pred_ratio"] = m.hotspots * m.k_hotspots
    tr, te = m[m.year.isin(fit_years)], m[m.year.isin(C.BACKTEST_YEARS)].copy()
    booster = fit_lgbm(tr[feats], tr.y_hs)
    te["pred_lgbm"] = booster.predict(te[feats])
    te["pred_raw"] = te.hotspots
    bt = {"cell_month": [metrics(te.y_hs, te.pred_raw, "raw MODIS (no harmonization)"),
                         metrics(te.y_hs, te.pred_ratio, "ratio shrunk"),
                         metrics(te.y_hs, te.pred_lgbm, "lightgbm poisson")]}
    ann = te.groupby("year")[["y_hs", "pred_raw", "pred_ratio", "pred_lgbm"]].sum()
    bt["national_annual"] = {int(k): {kk: int(vv) for kk, vv in v.items()} for k, v in ann.round(0).to_dict(orient="index").items()}
    cell4 = te.groupby("h3_4")[["y_hs", "pred_ratio", "pred_lgbm"]].sum()
    cell4 = cell4[cell4.y_hs >= 20]
    for mth in ["pred_ratio", "pred_lgbm"]:
        err = (cell4[mth] / cell4.y_hs - 1).abs()
        bt[f"cell_4yr_fire_weighted_abs_err_{mth}"] = round(float(np.average(err, weights=cell4.y_hs)), 3)
        bt[f"cell_4yr_median_abs_err_{mth}"] = round(float(err.median()), 3)
    val["backtest_2012_2015"] = bt
    val["lgbm_feature_gain"] = dict(zip(feats, [round(float(g), 1) for g in booster.feature_importance("gain")]))

    # ---------- ajuste final con todo el solapamiento ----------------------------------------
    fac = ratio_factors(panel, cells, overlap_years)
    mall, _ = lgbm_features(panel, cells)
    mall = mall.merge(tgt, on=["h3_4", "month"], how="left")
    fit_mask = mall.year.isin(overlap_years) & mall.y_hs.notna()
    booster_all = fit_lgbm(mall[fit_mask][feats], mall[fit_mask].y_hs)
    mall["lgbm_hs"] = booster_all.predict(mall[feats])
    mall = mall.merge(fac["hotspots"], on=["h3_4", "mcal"]).merge(fac["frp"], on=["h3_4", "mcal"])
    mall = mall.merge(cells[["h3_4", "h3_3"]], on="h3_4").merge(ta[["h3_3", "mcal", "k_terra"]], on=["h3_3", "mcal"], how="left")
    aqua_first_full_month = (pd.Timestamp(C.SAT_START["Aqua"]) + pd.offsets.MonthBegin(1)).normalize()
    terra_only = mall.month < aqua_first_full_month
    mall["bridge"] = np.where(terra_only, mall.k_terra.fillna(1.0), 1.0)
    mall["ratio_hs"] = mall.hotspots * mall.bridge * mall.k_hotspots
    mall["ratio_frp"] = mall.frp * mall.bridge * mall.k_frp
    mall["lgbm_hs"] = np.where(terra_only, mall.lgbm_hs * mall.bridge, mall.lgbm_hs)

    # ---------- registro armonizado final ---------------------------------------------------
    wide = panel[panel.active].pivot_table(index=["h3_4", "month"], columns="sensor_group", values=["hotspots", "frp", "n_det"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    h = wide.merge(mall[["h3_4", "month", "ratio_hs", "ratio_frp", "lgbm_hs", "k_hotspots", "k_frp", "bridge"]],
                   on=["h3_4", "month"], how="left")
    snpp_ok = h["hotspots_SNPP"].notna()
    n20_ok = h["hotspots_NOAA20"].notna()
    h["harm_hotspots"] = np.where(snpp_ok, h["hotspots_SNPP"], np.where(n20_ok, h["hotspots_NOAA20"] * k_n20, h["ratio_hs"]))
    h["harm_frp"] = np.where(snpp_ok, h["frp_SNPP"], np.where(n20_ok, h["frp_NOAA20"] * k_n20_frp, h["ratio_frp"]))
    h["harm_hotspots_lgbm"] = np.where(snpp_ok, h["hotspots_SNPP"], np.where(n20_ok, h["hotspots_NOAA20"] * k_n20, h["lgbm_hs"]))
    h["source"] = np.where(snpp_ok, "SNPP observed",
                  np.where(n20_ok, "NOAA20 scaled",
                  np.where(h.bridge.fillna(1) != 1, "MODIS Terra-only bridged x k", "MODIS x k")))

    # banda de incertidumbre para valores modelados: cuantiles del error relativo del backtest por tamaño de predicción
    edges = [0, 2, 5, 10, 25, 50, 100, 1e9]
    te_m = te[te.pred_ratio > 0].copy()
    te_m["bin"] = pd.cut(te_m.pred_ratio, edges)
    qs = {}
    for b, g in te_m.groupby("bin", observed=True):
        r = g.y_hs / g.pred_ratio
        qs[str(b)] = (float(np.quantile(r, 0.05)), float(np.quantile(r, 0.95)))
    val["uncertainty_ratio_quantiles_by_pred_bin"] = {k: [round(v[0], 3), round(v[1], 3)] for k, v in qs.items()}
    hb = pd.cut(h.ratio_hs.fillna(0), edges).astype(str)
    lo = hb.map(lambda b: qs.get(b, (0.0, 0.0))[0]).astype(float).fillna(0.0)
    hi = hb.map(lambda b: qs.get(b, (0.0, 0.0))[1]).astype(float).fillna(0.0)
    modelled = ~snpp_ok & ~n20_ok
    h["harm_lo"] = np.where(modelled, h.ratio_hs.fillna(0) * lo, h.harm_hotspots)
    h["harm_hi"] = np.where(modelled, np.maximum(h.ratio_hs.fillna(0) * hi, (h.ratio_hs.fillna(0) > 0).astype(float)), h.harm_hotspots)

    # ---------- prueba de continuidad en 2012 (nacional) ------------------------------------
    nat = h.groupby(h.month.dt.year)[["hotspots_MODIS", "hotspots_SNPP", "hotspots_NOAA20", "harm_hotspots", "harm_hotspots_lgbm", "harm_lo", "harm_hi"]].sum(min_count=1).astype(float)
    raw_join = pd.Series(np.where(nat.hotspots_SNPP.notna(), nat.hotspots_SNPP, nat.hotspots_MODIS), index=nat.index)
    pre, post = slice(2009, 2011), slice(2013, 2015)
    val["seam_2012_national"] = {
        "raw_joined_post_over_pre": round(float(raw_join.loc[post].mean() / raw_join.loc[pre].mean()), 3),
        "harmonized_post_over_pre": round(float(nat.harm_hotspots.loc[post].mean() / nat.harm_hotspots.loc[pre].mean()), 3),
        "harmonized_lgbm_post_over_pre": round(float(nat.harm_hotspots_lgbm.loc[post].mean() / nat.harm_hotspots_lgbm.loc[pre].mean()), 3),
        "modis_only_post_over_pre": round(float(nat.hotspots_MODIS.loc[post].mean() / nat.hotspots_MODIS.loc[pre].mean()), 3)}
    val["national_annual"] = {int(k): {kk: (None if pd.isna(vv) else int(round(vv))) for kk, vv in v.items()}
                              for k, v in nat.to_dict(orient="index").items()}
    val["k_national_by_month"] = {int(k): float(v) for k, v in zip(fac["hotspots_national"].mcal, fac["hotspots_national"].k_hotspots.round(3))}
    val["k_frp_national_by_month"] = {int(k): float(v) for k, v in zip(fac["frp_national"].mcal, fac["frp_national"].k_frp.round(3))}

    # ---------- incertidumbre de agregados (provincia/nacional x mes/año) para la app -----------
    te2 = te.merge(cells[["h3_4", "provincia"]], on="h3_4")
    aggs = []
    for keys in [["h3_4", "month"], ["h3_4", "year"], ["provincia", "month"], ["provincia", "year"], ["year", "month"], ["year"]]:
        g = te2.groupby(keys)[["y_hs", "pred_ratio"]].sum()
        aggs.append(g[g.pred_ratio > 0])
    A = pd.concat(aggs)
    A["r"] = A.y_hs / A.pred_ratio
    log_edges = np.array([0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 1e9])
    A["bin"] = pd.cut(A.pred_ratio, log_edges)
    unc = []
    for b, g in A.groupby("bin", observed=True):
        if len(g) >= 20:
            unc.append({"pred_min": float(b.left), "pred_max": float(min(b.right, 1e9)), "n": int(len(g)),
                        "q05": round(float(np.quantile(g.r, 0.05)), 3), "q50": round(float(np.quantile(g.r, 0.5)), 3),
                        "q95": round(float(np.quantile(g.r, 0.95)), 3)})
    val["aggregate_uncertainty_lookup"] = unc

    h.to_parquet(C.PROCESSED / "harmonized_cell_month.parquet", index=False)
    fac["hotspots"].merge(fac["frp"], on=["h3_4", "mcal"]).to_parquet(C.PROCESSED / "factors_cell_month.parquet", index=False)
    booster_all.save_model(str(C.PROCESSED / "lgbm_modis_to_snpp.txt"))
    with open(C.PROCESSED / "validation.json", "w", encoding="utf-8") as f:
        json.dump(val, f, indent=1)
    show = {k: val[k] for k in ["noaa20_to_snpp_factor", "backtest_2012_2015", "seam_2012_national", "k_national_by_month", "terra_only_bridge_national_by_month"]}
    print(json.dumps(show, indent=1))
    print(pd.DataFrame(val["national_annual"]).T.to_string())


if __name__ == "__main__":
    main()
