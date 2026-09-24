"""Build per-port feature matrix (visits + WPI) and write CSV/JSON coverage artifacts."""

import os
import json
import logging
from typing import Any
import numpy as np
import pandas as pd
from scipy.stats import entropy as scipy_entropy

from source.config.logger import setup_logging
from source.config.db import get_db_connection

logger = setup_logging(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "port_feature_matrix")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MIN_VISITS = 20  # ports below this are dropped

# Ship types tracked individually; everything else → "other"
SHIP_TYPES_OF_INTEREST = [
    "Cargo", "Tanker", "Passenger", "Fishing",
    "Tug", "HSC", "Dredging", "Sailing", "Towing",
    "Pilot", "SAR", "Other",
]

# WPI Yes/No/Unknown → 1/0/NaN after encoding
WPI_BINARY_COLS = [
    "facility_ro_ro", "facility_solid_bulk", "facility_liquid_bulk",
    "facility_container", "facility_breakbulk", "facility_oil_terminal",
    "facility_lng_terminal",
    "cranes_fixed", "cranes_mobile", "cranes_floating", "cranes_container",
    "lifts_100plus_tons", "lifts_50_100_tons",
    "services_ice_breaking", "services_diving",
    "pilotage_compulsory", "tugs_assistance",
    "restriction_ice", "restriction_tide", "restriction_heavy_swell",
    "supplies_fuel_oil", "supplies_diesel_oil", "supplies_potable_water",
]

HARBOR_SIZE_MAP = {"Very Small": 1, "Small": 2, "Medium": 3, "Large": 4}
SHELTER_MAP     = {"None": 0, "Poor": 1, "Fair": 2, "Good": 3, "Excellent": 4}


def fetch_port_visits() -> pd.DataFrame:
    logger.info("Fetching port visits with WPI metadata...")
    query = """
        SELECT
            v.id             AS visit_id,
            v.mmsi,
            v.port_id,
            p.un_locode,
            p.name           AS port_name,
            p.country_code,
            v.arrival_time,
            v.departure_time,
            v.stay_duration_hours,
            v.ship_type,
            v.cargo_type,
            v.length_m,
            v.width_m,
            v.draught_m,
            v.declared_destination,
            v.n_positions
        FROM public.port_visits v
        JOIN public.ports p ON v.port_id = p.id
        WHERE v.stay_duration_hours IS NOT NULL
          AND v.stay_duration_hours >= 1.0
        ORDER BY p.un_locode, v.arrival_time;
    """
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn, parse_dates=["arrival_time", "departure_time"])
        logger.info(f"Loaded {len(df):,} visits across {df['un_locode'].nunique()} ports.")
        return df
    finally:
        conn.close()


def fetch_wpi_infrastructure() -> pd.DataFrame:
    """Load WPI physical/facility columns; one row per un_locode."""
    logger.info("Fetching WPI infrastructure metadata...")

    binary_cols_sql = ",\n            ".join(f"p.{c}" for c in WPI_BINARY_COLS)

    query = f"""
        SELECT
            p.id            AS port_id,
            p.un_locode,
            p.name          AS port_name,
            p.country_code,
            p.harbor_size,
            p.harbor_type,
            p.harbor_use,
            p.shelter_afforded,
            p.tidal_range_m,
            p.entrance_width_m,
            p.channel_depth_m,
            p.anchorage_depth_m,
            p.cargo_pier_depth_m,
            p.oil_terminal_depth_m,
            p.max_vessel_length_m,
            p.max_vessel_beam_m,
            p.max_vessel_draft_m,
            ST_X(p.geom::geometry) AS longitude,
            ST_Y(p.geom::geometry) AS latitude,
            {binary_cols_sql}
        FROM public.ports p
        ORDER BY p.un_locode;
    """
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn)
        logger.info(f"Loaded WPI metadata for {len(df):,} ports.")
        return df
    finally:
        conn.close()


def _shannon_entropy(series: pd.Series) -> float:
    """Normalised Shannon entropy (0 = uniform, 1 = maximally diverse)."""
    counts = series.value_counts(dropna=True)
    if counts.empty or counts.sum() == 0:
        return np.nan
    probs = counts / counts.sum()
    return float(scipy_entropy(probs, base=len(probs)) if len(probs) > 1 else 0.0)


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: total visits, unique vessels, repeat ratio, throughput rate."""
    logger.info("  Computing volume features...")

    span_days  = (df["arrival_time"].max() - df["arrival_time"].min()).days
    span_weeks = max(span_days / 7.0, 1.0)

    grp = df.groupby("un_locode")

    vol = pd.DataFrame({
        "total_visits":        grp.size(),
        "unique_vessels":      grp["mmsi"].nunique(),
        "visits_per_week":     grp.size() / span_weeks,
        "avg_vessels_per_day": grp.size() / max(span_days, 1.0),
    })
    vol["repeat_visitor_ratio"] = 1.0 - (vol["unique_vessels"] / vol["total_visits"])
    vol["avg_visits_per_vessel"] = vol["total_visits"] / vol["unique_vessels"]

    return vol.reset_index()


def compute_stay_duration_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: median/IQR stay duration + short/long stay percentages."""
    logger.info("  Computing stay duration features...")

    def _port_stats(g):
        h = g["stay_duration_hours"].dropna()
        if h.empty:
            return pd.Series(dtype=float)
        return pd.Series({
            "median_stay_h":  h.median(),
            "mean_stay_h":    h.mean(),
            "std_stay_h":     h.std(),
            "p25_stay_h":     h.quantile(0.25),
            "p75_stay_h":     h.quantile(0.75),
            "stay_iqr_h":     h.quantile(0.75) - h.quantile(0.25),
            "pct_short_stay": (h < 4.0).mean() * 100.0,   # hours
            "pct_long_stay":  (h > 48.0).mean() * 100.0,  # hours
        })

    return df.groupby("un_locode").apply(_port_stats).reset_index()


def compute_ship_type_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port ship-type % vector + entropy; rare/blank types → Other."""
    logger.info("  Computing ship type features...")

    df = df.copy()

    def _normalise_type(st):
        if pd.isna(st) or str(st).strip() in ("", "Undefined", "Unknown"):
            return "Other"
        st_clean = str(st).strip()
        return st_clean if st_clean in SHIP_TYPES_OF_INTEREST else "Other"

    df["ship_type_norm"] = df["ship_type"].apply(_normalise_type)

    pivot = (
        df.groupby(["un_locode", "ship_type_norm"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=SHIP_TYPES_OF_INTEREST, fill_value=0)
    )

    totals = pivot.sum(axis=1)
    pct = pivot.div(totals, axis=0) * 100.0
    pct.columns = [f"pct_{c.lower()}" for c in pct.columns]

    pct["dominant_ship_type"] = pivot.idxmax(axis=1)

    def _entropy_row(row):
        probs = row[SHIP_TYPES_OF_INTEREST].values.astype(float)
        probs = probs[probs > 0]
        if len(probs) == 0:
            return np.nan
        probs = probs / probs.sum()
        return float(scipy_entropy(probs, base=min(len(probs), len(SHIP_TYPES_OF_INTEREST))))

    pct["ship_type_entropy"] = pivot.apply(_entropy_row, axis=1)

    return pct.reset_index()


def compute_vessel_size_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: percentile profiles of vessel length and draught."""
    logger.info("  Computing vessel size features...")

    def _size_stats(g):
        L = g["length_m"].dropna()
        D = g["draught_m"].dropna()

        length_stats = {
            "median_length_m": L.median() if not L.empty else np.nan,
            "mean_length_m":   L.mean() if not L.empty else np.nan,
            "std_length_m":    L.std() if not L.empty else np.nan,
            "p25_length_m":    L.quantile(0.25) if not L.empty else np.nan,
            "p75_length_m":    L.quantile(0.75) if not L.empty else np.nan,
            "iqr_length_m":    (L.quantile(0.75) - L.quantile(0.25)) if not L.empty else np.nan,
            "p90_length_m":    L.quantile(0.90) if not L.empty else np.nan,
        }
        draught_stats = {
            "median_draught_m": D.median() if not D.empty else np.nan,
            "mean_draught_m":   D.mean() if not D.empty else np.nan,
            "std_draught_m":    D.std() if not D.empty else np.nan,
            "iqr_draught_m":    (D.quantile(0.75) - D.quantile(0.25)) if not D.empty else np.nan,
            "p90_draught_m":    D.quantile(0.90) if not D.empty else np.nan,
        }
        return pd.Series({**length_stats, **draught_stats})

    # Drop implausible dimensions (length ≤ 10 m, draught ≤ 0)
    mask_length = df["length_m"].isna() | (df["length_m"] > 10.0)
    mask_draught = df["draught_m"].isna() | (df["draught_m"] > 0.0)
    df_clean = df[mask_length & mask_draught].copy()

    return df_clean.groupby("un_locode").apply(_size_stats).reset_index()


def compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: night/weekend ratios and peak-hour entropy."""
    logger.info("  Computing temporal features...")

    df = df.copy()
    arrival_dt: Any = pd.to_datetime(df["arrival_time"])
    df["arrival_hour"] = arrival_dt.dt.hour
    df["arrival_dow"]  = arrival_dt.dt.dayofweek

    def _temporal_stats(g):
        n = len(g)
        if n == 0:
            return pd.Series(dtype=float)

        night_mask   = (g["arrival_hour"] >= 22) | (g["arrival_hour"] < 6)
        weekend_mask = g["arrival_dow"].isin([5, 6])

        hour_counts = g["arrival_hour"].value_counts()
        all_hours = pd.Series(0, index=range(24))
        hour_counts = (all_hours + hour_counts).fillna(0)
        probs = hour_counts / hour_counts.sum()
        probs = probs[probs > 0]
        peak_ent = float(scipy_entropy(probs, base=24)) if len(probs) > 0 else np.nan

        return pd.Series({
            "night_visit_ratio":   float(night_mask.mean() * 100.0),
            "weekend_visit_ratio": float(weekend_mask.mean() * 100.0),
            "peak_hour_entropy":   peak_ent,
        })

    return df.groupby("un_locode").apply(_temporal_stats).reset_index()


def compute_seasonal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: seasonal coefficient of variation (monthly visit count STDDEV/MEAN)."""
    logger.info("  Computing seasonal features...")

    df = df.copy()
    arrival_dt: Any = pd.to_datetime(df["arrival_time"])
    df["year_month"] = arrival_dt.dt.to_period("M")

    monthly = df.groupby(["un_locode", "year_month"]).size().reset_index(name="monthly_visits")

    def _seasonal(g):
        mc = g["monthly_visits"]
        mean_v = mc.mean()
        if mean_v == 0 or len(mc) < 2:
            return pd.Series({"seasonal_cv": np.nan, "busiest_month": np.nan})
        cv = mc.std() / mean_v
        busiest = g.loc[g["monthly_visits"].idxmax(), "year_month"]
        return pd.Series({"seasonal_cv": float(cv), "busiest_month": str(busiest)})

    return monthly.groupby("un_locode").apply(_seasonal).reset_index()


def compute_flow_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-port: destination diversity and intra-country flow ratio."""
    logger.info("  Computing flow features...")

    def _flow_stats(g):
        dest = g["declared_destination"].dropna()
        if dest.empty:
            return pd.Series({"destination_diversity": np.nan, "match_rate": np.nan, "intra_country_ratio": np.nan})

        dest_ent = _shannon_entropy(dest)

        port_name = str(g["port_name"].iloc[0]).lower()
        country_code = str(g["country_code"].iloc[0]).lower()

        # Match rate: destination string contains port name (or first 5 chars)
        def _matches_port(d):
            d = str(d).lower()
            return port_name in d or (len(port_name) > 5 and port_name[:5] in d)

        # Intra-country: destination mentions country code or common English name
        country_names = {
            "pl": "poland", "de": "germany", "dk": "denmark", "se": "sweden",
            "lt": "lithuania", "lv": "latvia", "ee": "estonia", "fi": "finland", "ru": "russia"
        }
        country_name = country_names.get(country_code, "")

        def _is_intra(d):
            d = str(d).lower()
            return bool(country_code in d or (country_name and country_name in d))

        match_rate = dest.apply(_matches_port).astype(float).mean() * 100.0
        intra_ratio = dest.apply(_is_intra).astype(float).mean() * 100.0

        return pd.Series({
            "destination_diversity": dest_ent,
            "match_rate":            match_rate,
            "intra_country_ratio":   intra_ratio,
        })

    return df.groupby("un_locode").apply(_flow_stats).reset_index()


def encode_wpi_infrastructure(wpi: pd.DataFrame) -> pd.DataFrame:
    """Encode WPI categoricals/binaries: Yes→1, No→0, Unknown/NULL→NaN."""
    logger.info("  Encoding WPI infrastructure features...")

    wpi = wpi.copy()

    wpi["harbor_size_int"]    = wpi["harbor_size"].map(HARBOR_SIZE_MAP)
    wpi["shelter_afforded_int"] = wpi["shelter_afforded"].map(SHELTER_MAP)

    def _yn_encode(val):
        if pd.isna(val):
            return np.nan
        v = str(val).strip().lower()
        if v in ("yes", "y", "true", "1"):
            return 1.0
        if v in ("no", "n", "false", "0"):
            return 0.0
        return np.nan

    for col in WPI_BINARY_COLS:
        if col in wpi.columns:
            wpi[f"{col}_bin"] = wpi[col].apply(_yn_encode)

    keep_cols = (
        ["port_id", "un_locode", "port_name", "country_code",
         "harbor_size_int", "shelter_afforded_int",
         "harbor_type", "harbor_use",
         "tidal_range_m", "entrance_width_m", "channel_depth_m",
         "anchorage_depth_m", "cargo_pier_depth_m",
         "max_vessel_length_m", "max_vessel_beam_m", "max_vessel_draft_m",
         "longitude", "latitude"]
        + [f"{c}_bin" for c in WPI_BINARY_COLS if c in wpi.columns]
    )
    keep_cols = [c for c in keep_cols if c in wpi.columns]

    return wpi[keep_cols]


def assemble_feature_matrix(visits: pd.DataFrame, wpi_enc: pd.DataFrame) -> pd.DataFrame:
    """Merge visit feature blocks with WPI encoding on un_locode."""
    logger.info("Assembling consolidated feature matrix...")

    blocks = [
        compute_volume_features(visits),
        compute_stay_duration_features(visits),
        compute_ship_type_features(visits),
        compute_vessel_size_features(visits),
        compute_temporal_features(visits),
        compute_seasonal_features(visits),
        compute_flow_features(visits),
    ]

    matrix = blocks[0]
    for block in blocks[1:]:
        matrix = pd.merge(matrix, block, on="un_locode", how="left")

    matrix = pd.merge(
        matrix,
        wpi_enc,
        on="un_locode",
        how="left",
        suffixes=("", "_wpi"),
    )

    has_obs_draught = "p90_draught_m" in matrix.columns and "max_vessel_draft_m" in matrix.columns
    if has_obs_draught:
        matrix["draught_utilization"] = (
            matrix["p90_draught_m"] / matrix["max_vessel_draft_m"].replace(0, np.nan)
        )

    logger.info(f"Feature matrix shape: {matrix.shape[0]} ports × {matrix.shape[1]} features")
    return matrix


def generate_coverage_report(matrix: pd.DataFrame) -> dict:
    """NULL rate and coverage % per feature column."""
    total = len(matrix)
    report = {}
    for col in matrix.columns:
        null_count = matrix[col].isna().sum()
        report[col] = {
            "null_count":   null_count,
            "null_pct":     round(null_count / total * 100, 1) if total > 0 else 0.0,
            "coverage_pct": round((total - null_count) / total * 100, 1) if total > 0 else 0.0,
        }
    return dict(sorted(report.items(), key=lambda x: x[1]["null_pct"], reverse=True))


def run_feature_matrix_builder():
    logger.info("=" * 70)
    logger.info("Starting Port Feature Matrix Builder")
    logger.info("=" * 70)

    visits = fetch_port_visits()
    
    from source.analysis.ports.preprocessing import optimize_memory_usage
    visits = optimize_memory_usage(visits)
    
    wpi    = fetch_wpi_infrastructure()

    if visits.empty:
        logger.error("No port visits found. Run port_visit_extractor.py first!")
        return

    wpi_enc = encode_wpi_infrastructure(wpi)

    matrix_raw = assemble_feature_matrix(visits, wpi_enc)

    raw_path = os.path.join(OUTPUT_DIR, "port_features_raw.csv")
    matrix_raw.to_csv(raw_path, index=False)
    logger.info(f"Raw feature matrix saved → {raw_path}")

    matrix_clean = matrix_raw[matrix_raw["total_visits"] >= MIN_VISITS].copy()
    logger.info(
        f"Clean matrix (>= {MIN_VISITS} visits): {len(matrix_clean)} ports "
        f"(dropped {len(matrix_raw) - len(matrix_clean)} small ports)"
    )

    clean_path = os.path.join(OUTPUT_DIR, "port_features_clean.csv")
    matrix_clean.to_csv(clean_path, index=False)
    logger.info(f"Clean feature matrix saved → {clean_path}")

    ship_type_cols = [c for c in matrix_clean.columns if c.startswith("pct_")]
    ship_type_vec = matrix_clean[["un_locode", "port_name", "country_code", "total_visits"] + ship_type_cols]
    vec_path = os.path.join(OUTPUT_DIR, "ship_type_vectors.csv")
    ship_type_vec.to_csv(vec_path, index=False)
    logger.info(f"Ship type percentage vectors saved → {vec_path}")

    coverage = generate_coverage_report(matrix_clean)
    cov_path = os.path.join(OUTPUT_DIR, "feature_coverage_report.json")
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(coverage, f, indent=2)
    logger.info(f"Feature coverage report saved → {cov_path}")

    logger.info("=" * 70)
    logger.info("Feature Matrix Builder Complete!")
    logger.info(f"  Ports in clean matrix  : {len(matrix_clean)}")
    logger.info(f"  Total features         : {matrix_clean.shape[1]}")
    logger.info(f"  Total visits processed : {len(visits):,}")
    logger.info("=" * 70)

    return matrix_clean


if __name__ == "__main__":
    run_feature_matrix_builder()
