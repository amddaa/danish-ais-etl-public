"""Multi-index K selection, DBSCAN benchmark, and cluster naming."""

import logging
import re
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score, davies_bouldin_score

from source.analysis.ports.array_types import FloatArray, NdArray
from source.config.logger import setup_logging
from source.analysis.ports.clustering_engine import (
    compute_gap_statistic,
    find_optimal_eps,
)

logger = setup_logging(__name__)


def run_multi_index_k_selection(
    X: FloatArray,
    k_range: range = range(2, 9),
    n_init: int = 20,
    random_state: int = 42,
) -> dict:
    """Evaluate WCSS, Silhouette, DBI, and Gap across K; return consensus optimal_k."""
    k_values = list(k_range)
    wcss_scores = []
    sil_scores = []
    dbi_scores = []

    logger.info(f"Running multi-index K selection for K={k_values[0]}..{k_values[-1]}...")

    for k in k_values:
        km = KMeans(
            n_clusters=k, init="k-means++", n_init=n_init, random_state=random_state
        )
        labels = km.fit_predict(np.asarray(X, dtype=np.float64))

        wcss_scores.append(float(km.inertia_))

        if len(set(labels)) > 1:
            sil_scores.append(float(silhouette_score(X, labels)))
            dbi_scores.append(float(davies_bouldin_score(X, labels)))
        else:
            sil_scores.append(-1.0)
            dbi_scores.append(float("inf"))

        logger.debug(
            f"  K={k}: WCSS={wcss_scores[-1]:.2f}, "
            f"Sil={sil_scores[-1]:.3f}, DBI={dbi_scores[-1]:.3f}"
        )

    gap_result = compute_gap_statistic(
        X, n_refs=10, max_k=k_values[-1], random_state=random_state
    )

    # Consensus optimal K: majority vote; Silhouette breaks ties
    best_sil_k = k_values[int(np.argmax(sil_scores))]
    best_dbi_k = k_values[int(np.argmin(dbi_scores))]
    best_gap_k = gap_result["optimal_k"]

    candidates = [best_sil_k, best_dbi_k, best_gap_k]
    vote_counts = Counter(candidates)
    
    if vote_counts.most_common(1)[0][1] == 1:
        optimal_k = best_sil_k
        rationale = (
            f"Silhouette recommends K={best_sil_k}, "
            f"DBI recommends K={best_dbi_k}, "
            f"Gap recommends K={best_gap_k}. "
            f"Tie-breaker (Silhouette preference): K={optimal_k}"
        )
    else:
        optimal_k = vote_counts.most_common(1)[0][0]
        rationale = (
            f"Silhouette recommends K={best_sil_k}, "
            f"DBI recommends K={best_dbi_k}, "
            f"Gap recommends K={best_gap_k}. "
            f"Consensus (majority vote): K={optimal_k}"
        )
        
    logger.info(f"Model selection complete. {rationale}")

    return {
        "k_values": k_values,
        "wcss": wcss_scores,
        "silhouette": sil_scores,
        "davies_bouldin": dbi_scores,
        "gap_values": gap_result["gaps"],
        "gap_sk": gap_result["sk"],
        "optimal_k": optimal_k,
        "selection_rationale": rationale,
    }


def run_dbscan_benchmark(
    X: FloatArray,
    min_samples: int | None = None,
) -> dict:
    """DBSCAN with auto eps; default min_samples = D + 1."""
    if min_samples is None:
        min_samples = int(X.shape[1] + 1)
        logger.info(f"Auto min_samples = D+1 = {min_samples}")

    ms: int = min_samples
    eps_result = find_optimal_eps(X, ms)
    eps = eps_result["optimal_eps"]

    db = DBSCAN(eps=eps, min_samples=ms)
    labels = db.fit_predict(np.asarray(X, dtype=np.float64))

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())

    sil = None
    if n_clusters > 1 and n_noise < len(labels):
        non_noise_mask = labels != -1
        if len(set(labels[non_noise_mask])) > 1:
            sil = float(silhouette_score(X[non_noise_mask], labels[non_noise_mask]))

    logger.info(
        f"DBSCAN: {n_clusters} clusters, {n_noise} noise points "
        f"(eps={eps:.4f}, min_samples={ms})"
    )

    return {
        "labels": labels,
        "n_clusters": n_clusters,
        "n_noise": n_noise,
        "eps": eps,
        "min_samples": ms,
        "silhouette": sil,
        "k_distances": eps_result["k_distances"],
        "knee_index": eps_result["knee_index"],
    }


def generate_cross_tabulation(
    km_labels: NdArray,
    db_labels: NdArray,
    port_identifiers: list[str],
) -> dict:
    """Compare K-Means vs DBSCAN; flag ports DBSCAN marks as noise."""
    compare_df = pd.DataFrame({
        "port": port_identifiers,
        "kmeans": km_labels,
        "dbscan": db_labels,
    })

    ct = pd.crosstab(
        compare_df["kmeans"],
        compare_df["dbscan"],
        margins=True,
        margins_name="Total",
    )

    noise_ports = compare_df[compare_df["dbscan"] == -1].to_dict("records")

    forced = compare_df[
        (compare_df["dbscan"] == -1) & (compare_df["kmeans"] >= 0)
    ].to_dict("records")

    logger.info(
        f"Cross-tabulation: {len(noise_ports)} DBSCAN noise ports, "
        f"{len(forced)} forced K-Means assignments"
    )

    return {
        "crosstab": ct,
        "noise_ports": noise_ports,
        "forced_assignments": forced,
    }


def generate_cluster_names(
    X_raw: FloatArray,
    X_scaled: FloatArray,
    labels: NdArray,
    feature_names: list[str],
) -> dict[int, str]:
    """Name each cluster from its largest absolute z-score feature deviation."""
    unique_labels = sorted(set(labels))
    overall_means = np.nanmean(X_raw, axis=0)
    cluster_names = {}

    for cluster_id in unique_labels:
        if cluster_id == -1:
            cluster_names[-1] = "Noise / Anomalies"
            continue

        mask = labels == cluster_id
        cluster_z_means = X_scaled[mask].mean(axis=0)
        max_dev_idx = int(np.abs(cluster_z_means).argmax())
        max_dev_val = cluster_z_means[max_dev_idx]

        cluster_raw_mean = float(np.nanmean(X_raw[mask, max_dev_idx]))
        overall_raw_mean = float(overall_means[max_dev_idx])

        raw_feat_name = feature_names[max_dev_idx]
        feat_name = re.sub(r'^pct_', '', raw_feat_name)
        feat_name = re.sub(r'_[mh]$', '', feat_name)
        feat_name = re.sub(r'_int$', '', feat_name)
        feat_name = feat_name.replace('_', ' ').title()

        prefix = "High" if max_dev_val > 0 else "Low"
        cluster_names[cluster_id] = (
            f"C{cluster_id + 1}: {prefix} {feat_name} "
            f"({cluster_raw_mean:.1f} vs avg {overall_raw_mean:.1f})"
        )

    return cluster_names
