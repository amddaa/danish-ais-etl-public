import os
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

from source.analysis.ports.preprocessing import (
    robust_imputation,
    build_profile_preprocessor,
)
from source.analysis.ports.clustering_engine import (
    calculate_hopkins_statistic,
)
from source.analysis.ports.model_selection import (
    run_multi_index_k_selection,
    run_dbscan_benchmark,
    generate_cross_tabulation,
    generate_cluster_names,
)
from source.analysis.ports.plot_publication import (
    plot_multi_index_selection,
    plot_k_distance_elbow,
    plot_umap_projection,
    plot_tsne_tuning,
    plot_explained_variance,
)

from source.config.logger import setup_logging
from source.analysis.web_data import WEB_DATA_DIR, dump_json, sanitize
from source.schemas.port_dashboard import PortDashboardOutput

logger = setup_logging(__name__)

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "output", "port_feature_matrix")
CLEAN_CSV = os.path.join(DATA_DIR, "port_features_clean.csv")

PROFILES = {
    "fleet_mix": {
        "label": "Fleet Mix",
        "icon": "ship",
        "cols": ["pct_cargo", "pct_tanker", "pct_passenger", "pct_fishing", "pct_hsc", "pct_sailing", "pct_tug", "pct_dredging", "pct_towing", "pct_pilot", "pct_sar", "pct_other"],
        "desc": "Similarity based on the distribution of vessel types visiting the port."
    },
    "operations": {
        "label": "Operations",
        "icon": "clock",
        "cols": ["median_stay_h", "stay_iqr_h", "pct_short_stay", "pct_long_stay", "repeat_visitor_ratio", "avg_visits_per_vessel"],
        "desc": "Focus on stay patterns, handling efficiency, and vessel loyalty."
    },
    "scale": {
        "label": "Vessel Scale",
        "icon": "maximize",
        "cols": ["mean_length_m", "median_length_m", "mean_draught_m", "median_draught_m"],
        "desc": "Similarity in the physical dimensions (size and depth) of visiting vessels."
    },
    "infrastructure": {
        "label": "Infrastructure",
        "icon": "anchor",
        "cols": ["harbor_size_int", "shelter_afforded_int", "channel_depth_m", "anchorage_depth_m", "cargo_pier_depth_m"],
        "desc": "Comparison based on WPI physical characteristics and capacity."
    },
    "temporal": {
        "label": "Temporal Patterns",
        "icon": "calendar",
        "cols": ["night_visit_ratio", "weekend_visit_ratio", "peak_hour_entropy", "seasonal_cv"],
        "desc": "Similarity based on stay patterns, temporal distributions (night/weekend), and seasonality."
    },
    "connectivity": {
        "label": "Connectivity",
        "icon": "globe",
        "cols": ["destination_diversity", "intra_country_ratio", "total_visits", "unique_vessels", "visits_per_week"],
        "desc": "Similarity based on trade network flow diversity, domestic ratio, and vessel throughput."
    }
}

FEATURE_DOCS = {
    "pct_cargo": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Cargo ship visits / Total Visits) * 100.",
    "pct_tanker": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Tanker visits / Total Visits) * 100.",
    "pct_passenger": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Passenger/Ferry visits / Total Visits) * 100.",
    "pct_fishing": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Fishing vessel visits / Total Visits) * 100.",
    "pct_hsc": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (High Speed Craft visits / Total Visits) * 100.",
    "pct_sailing": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Sailing/Leisure visits / Total Visits) * 100.",
    "pct_tug": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Tug vessel visits / Total Visits) * 100.",
    "pct_dredging": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Dredging ops visits / Total Visits) * 100.",
    "pct_towing": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Towing vessel visits / Total Visits) * 100.",
    "pct_pilot": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Pilot vessel visits / Total Visits) * 100.",
    "pct_sar": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Search & Rescue visits / Total Visits) * 100.",
    "pct_other": "<b>Source:</b> <code>port_visits</code> table (`ship_type`).<br><b>Calc:</b> (Unclassified visits / Total Visits) * 100.",
    
    "median_stay_h": "<b>Source:</b> <code>port_visits</code> table (`stay_duration_hours`).<br><b>Calc:</b> Median duration (hours) between first and last AIS ping within the port polygon for a continuous visit.",
    "stay_iqr_h": "<b>Source:</b> <code>port_visits</code> table (`stay_duration_hours`).<br><b>Calc:</b> Interquartile range (75th - 25th percentile) of stay durations. Indicates variability.",
    "pct_short_stay": "<b>Source:</b> <code>port_visits</code> table (`stay_duration_hours`).<br><b>Calc:</b> Percentage of visits lasting < 4 hours.",
    "pct_long_stay": "<b>Source:</b> <code>port_visits</code> table (`stay_duration_hours`).<br><b>Calc:</b> Percentage of visits lasting > 48 hours.",
    "repeat_visitor_ratio": "<b>Source:</b> <code>port_visits</code> table (`mmsi`).<br><b>Calc:</b> (Vessels with >1 visit) / (Total unique vessels).",
    "avg_visits_per_vessel": "<b>Source:</b> <code>port_visits</code> table (`mmsi`).<br><b>Calc:</b> (Total visits) / (Total unique vessels).",
    
    "mean_length_m": "<b>Source:</b> <code>port_visits</code> table (`length_m`).<br><b>Calc:</b> Average length of unique visiting vessels.",
    "median_length_m": "<b>Source:</b> <code>port_visits</code> table (`length_m`).<br><b>Calc:</b> Median length of unique visiting vessels.",
    "mean_draught_m": "<b>Source:</b> <code>port_visits</code> table (`draught_m`).<br><b>Calc:</b> Average reported draught of visiting vessels.",
    "median_draught_m": "<b>Source:</b> <code>port_visits</code> table (`draught_m`).<br><b>Calc:</b> Median reported draught of visiting vessels.",
    
    "harbor_size_int": "<b>Source:</b> <code>ports</code> table (`harbor_size`).<br><b>Calc:</b> Encoded categorical size (1: Very Small, 4: Large).",
    "shelter_afforded_int": "<b>Source:</b> <code>shelter_afforded</code> column.<br><b>Calc:</b> Encoded shelter quality (1: Poor, 4: Excellent).",
    "channel_depth_m": "<b>Source:</b> <code>ports</code> table (`channel_depth_m`).<br><b>Calc:</b> Max depth (m) in main entrance channel.",
    "anchorage_depth_m": "<b>Source:</b> <code>ports</code> table (`anchorage_depth_m`).<br><b>Calc:</b> Depth (m) of the primary anchorage area.",
    "cargo_pier_depth_m": "<b>Source:</b> <code>ports</code> table (`cargo_pier_depth_m`).<br><b>Calc:</b> Max depth (m) at cargo piers.",

    "night_visit_ratio": "<b>Source:</b> <code>port_visits</code> table (`arrival_time`).<br><b>Calc:</b> Percentage of visits arriving between 22:00 and 06:00.",
    "weekend_visit_ratio": "<b>Source:</b> <code>port_visits</code> table (`arrival_time`).<br><b>Calc:</b> Percentage of visits arriving on Saturday or Sunday.",
    "peak_hour_entropy": "<b>Source:</b> <code>port_visits</code> table (`arrival_time`).<br><b>Calc:</b> Shannon entropy of arrival hours (0-23). Higher values indicate a more uniform distribution of arrivals throughout the day.",
    "seasonal_cv": "<b>Source:</b> <code>port_visits</code> table (`arrival_time`).<br><b>Calc:</b> Coefficient of variation (standard deviation / mean) of monthly visit counts. Measures seasonality.",
    "destination_diversity": "<b>Source:</b> <code>port_visits</code> table (`declared_destination`).<br><b>Calc:</b> Shannon entropy of declared destination port strings. Measures the diversity of connected routes.",
    "intra_country_ratio": "<b>Source:</b> <code>port_visits</code> table (`declared_destination`).<br><b>Calc:</b> Percentage of voyages where the destination is within the same country. Measures domestic vs. international focus.",
    "total_visits": "<b>Source:</b> <code>port_visits</code> table.<br><b>Calc:</b> Total number of recorded vessel visits.",
    "unique_vessels": "<b>Source:</b> <code>port_visits</code> table (`mmsi`).<br><b>Calc:</b> Total number of unique vessels visiting the port.",
    "visits_per_week": "<b>Source:</b> <code>port_visits</code> table.<br><b>Calc:</b> Average number of visits per week."
}

SHIP_LABELS = {
    "pct_cargo": "Cargo", "pct_tanker": "Tanker", "pct_passenger": "Passenger",
    "pct_fishing": "Fishing", "pct_hsc": "HSC", "pct_sailing": "Sailing",
    "pct_tug": "Tug", "pct_dredging": "Dredging", "pct_towing": "Towing",
    "pct_pilot": "Pilot", "pct_sar": "SAR", "pct_other": "Other"
}

PCA_VARIANCE_THRESHOLD = 0.85  # Retain 85% of cumulative variance
KMEANS_N_INIT = 20

df = pd.read_csv(CLEAN_CSV).sort_values("total_visits", ascending=False)
results = {}
cross_tab_results = {}

logger.info(f"Loaded {len(df)} ports from {CLEAN_CSV}")

for p_id, p_info in PROFILES.items():
    logger.info(f"Processing profile: {p_id} ({p_info['label']})")
    cols = [c for c in p_info["cols"] if c in df.columns]

    df_imputed = robust_imputation(df, cols)
    data_slice = df_imputed[cols].copy()

    preprocessor = build_profile_preprocessor(p_id, cols)
    X_scaled = np.asarray(preprocessor.fit_transform(data_slice.values), dtype=np.float64)

    hopkins_h = calculate_hopkins_statistic(X_scaled)

    pca = PCA(n_components=PCA_VARIANCE_THRESHOLD)
    X_pca = np.asarray(pca.fit_transform(X_scaled), dtype=np.float64)
    n_pca_components = X_pca.shape[1]
    logger.info(
        f"  PCA: {n_pca_components} components explain "
        f"{sum(pca.explained_variance_ratio_) * 100:.1f}% variance"
    )

    # 3-component PCA for dashboard viz coords (clustering uses variance-threshold PCA above)
    pca_viz = PCA(n_components=min(3, X_scaled.shape[1]))
    coords = np.asarray(pca_viz.fit_transform(X_scaled), dtype=np.float64)

    plot_explained_variance(pca.explained_variance_ratio_, PCA_VARIANCE_THRESHOLD, p_id)

    # Correlation on raw (unscaled) features
    corr_matrix = data_slice.corr().round(3)

    selection = run_multi_index_k_selection(X_pca, n_init=KMEANS_N_INIT)
    best_k = selection["optimal_k"]

    # K-Means on PCA components, not full X_scaled
    kmeans = KMeans(
        n_clusters=best_k, init="k-means++",
        n_init=KMEANS_N_INIT, random_state=42,
    )
    cluster_labels = np.asarray(
        kmeans.fit_predict(np.asarray(X_pca, dtype=np.float64)),
        dtype=np.intp,
    )

    plot_multi_index_selection(selection, best_k, p_id)

    dbscan_result = run_dbscan_benchmark(X_pca)
    dbscan_labels = np.asarray(dbscan_result["labels"], dtype=np.intp)
    k_distances = np.asarray(dbscan_result["k_distances"], dtype=np.float64)

    plot_k_distance_elbow(
        k_distances, dbscan_result["eps"],
        dbscan_result["knee_index"], p_id,
    )

    port_names_ids = (df["un_locode"].astype(str) + " - " + df["port_name"].astype(str)).tolist()
    cross_tab = generate_cross_tabulation(cluster_labels, dbscan_labels, port_names_ids)
    cross_tab_results[p_id] = cross_tab

    cluster_names = generate_cluster_names(
        np.asarray(data_slice.values, dtype=np.float64), X_scaled, cluster_labels, cols,
    )
    cluster_names_str = {str(k): v for k, v in cluster_names.items()}

    from sklearn.metrics import silhouette_score, davies_bouldin_score
    best_sil = float(silhouette_score(X_pca, cluster_labels)) if len(set(cluster_labels.tolist())) > 1 else -1.0
    best_dbi = float(davies_bouldin_score(X_pca, cluster_labels)) if len(set(cluster_labels.tolist())) > 1 else float("inf")

    plot_umap_projection(
        X_scaled,
        cluster_labels,
        df["un_locode"].tolist(),
        np.asarray(df["total_visits"].values, dtype=np.float64),
        cluster_names,
        p_id,
    )

    plot_tsne_tuning(X_scaled, cluster_labels, profile_label=p_id)

    results[p_id] = {
        "coords": coords.round(4).tolist(),
        "variance": (pca_viz.explained_variance_ratio_ * 100).round(1).tolist(),
        "variance_clustering_total": round(float(sum(pca.explained_variance_ratio_) * 100), 1),
        "corr": {
            "z": corr_matrix.values.tolist(),
            "x": corr_matrix.columns.tolist(),
            "y": corr_matrix.index.tolist(),
        },
        "clusters": cluster_labels.tolist(),
        "cluster_names": cluster_names_str,
        "optimal_k": best_k,
        "silhouette_score": round(best_sil, 3),
        "davies_bouldin": round(best_dbi, 3),
        "hopkins": round(hopkins_h, 4),
        "n_pca_components": n_pca_components,
        "selection_rationale": selection["selection_rationale"],
        "dbscan_n_clusters": dbscan_result["n_clusters"],
        "dbscan_n_noise": dbscan_result["n_noise"],
        "forced_assignments": cross_tab["forced_assignments"],
    }

    logger.info(
        f"  Profile '{p_id}' complete: K={best_k}, "
        f"Sil={best_sil:.3f}, DBI={best_dbi:.3f}, "
        f"Hopkins={hopkins_h:.4f}"
    )

ship_colors = {"Cargo": "#3b82f6", "Tanker": "#ef4444", "Passenger": "#10b981", "Fishing": "#f59e0b", "HSC": "#8b5cf6", "Sailing": "#ec4899", "Tug": "#14b8a6", "Dredging": "#f97316", "Other": "#64748b"}
ports_meta = []

for _, row in df.iterrows():
    raw_feats = {}
    for p_id, p_info in PROFILES.items():
        for col in p_info["cols"]:
            if col in row:
                val = row[col]
                if pd.isna(val):
                    raw_feats[col] = None
                else:
                    raw_feats[col] = round(float(val), 2)
                    if col.startswith("pct_"):
                        raw_feats[f"{col}_count"] = int(round(val / 100.0 * row["total_visits"]))
    ports_meta.append({
        "id": row["un_locode"], "name": row["port_name"], "country": row["country_code"], "dominant": row["dominant_ship_type"],
        "visits": int(row["total_visits"]), "color": ship_colors.get(row["dominant_ship_type"], "#94a3b8"),
        "raw_features": raw_feats,
        "lat": float(row["latitude"]) if not pd.isna(row["latitude"]) else 0.0,
        "lon": float(row["longitude"]) if not pd.isna(row["longitude"]) else 0.0
    })


payload = PortDashboardOutput.model_validate(sanitize({
    "ports": ports_meta,
    "pcaData": results,
    "profiles": PROFILES,
    "featureDocs": FEATURE_DOCS,
}))
dump_json(WEB_DATA_DIR / "port_dashboard.json", payload.model_dump(mode="json"))
logger.info("Clustering-enabled dashboard JSON saved -> %s", WEB_DATA_DIR / "port_dashboard.json")
