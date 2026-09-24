"""Hopkins / Gap statistics and DBSCAN eps calibration via k-distance knee."""

import logging
import numpy as np
from sklearn.cluster import KMeans, DBSCAN
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import silhouette_score, davies_bouldin_score
from kneed import KneeLocator

from source.analysis.ports.array_types import FloatArray
from source.config.logger import setup_logging

logger = setup_logging(__name__)


def calculate_hopkins_statistic(
    X: FloatArray,
    sampling_ratio: float = 0.1,
    random_state: int = 42,
) -> float:
    n, d = X.shape
    m = max(1, int(n * sampling_ratio))

    rng = np.random.default_rng(random_state)

    min_val = X.min(axis=0)
    max_val = X.max(axis=0)
    X_synthetic = rng.uniform(low=min_val, high=max_val, size=(m, d))

    real_indices = rng.choice(n, size=m, replace=False)
    X_real = X[real_indices]

    algorithm = "kd_tree" if d < 20 else "auto"
    nn = NearestNeighbors(n_neighbors=2, algorithm=algorithm, n_jobs=-1).fit(
        np.asarray(X, dtype=np.float64)
    )

    u_dist, _ = nn.kneighbors(X_synthetic, n_neighbors=1)

    # n_neighbors=2: nearest neighbor of a real point is itself
    v_dist, _ = nn.kneighbors(X_real, n_neighbors=2)
    v_dist_other = v_dist[:, 1]

    sum_u = float(np.sum(u_dist))
    sum_v = float(np.sum(v_dist_other))

    if (sum_u + sum_v) == 0:
        return 0.5

    hopkins = sum_u / (sum_u + sum_v)
    logger.info(f"Hopkins statistic: {hopkins:.4f}")
    return float(hopkins)


def compute_gap_statistic(
    X: FloatArray,
    n_refs: int = 10,
    max_k: int = 8,
    random_state: int = 42,
) -> dict:
    """Gap statistic vs uniform refs; optimal_k is first K with Gap(K) >= Gap(K+1) - s_{K+1}."""
    rng = np.random.default_rng(random_state)
    k_values = list(range(2, max_k + 1))
    gaps = []
    sk_values = []

    min_vals = X.min(axis=0)
    max_vals = X.max(axis=0)

    for k in k_values:
        km_real = KMeans(
            n_clusters=k, init="k-means++", n_init=20, random_state=random_state
        )
        km_real.fit(np.asarray(X, dtype=np.float64))
        wcss_real = km_real.inertia_

        ref_inertias = np.zeros(n_refs)
        for b in range(n_refs):
            X_ref = rng.uniform(low=min_vals, high=max_vals, size=X.shape)
            km_ref = KMeans(
                n_clusters=k, init="k-means++", n_init=10, random_state=random_state
            )
            km_ref.fit(np.asarray(X_ref, dtype=np.float64))
            ref_inertias[b] = km_ref.inertia_

        log_wcss_real = np.log(wcss_real)
        log_wcss_refs = np.log(ref_inertias)

        gap = float(np.mean(log_wcss_refs) - log_wcss_real)
        sd_k = float(np.std(log_wcss_refs))
        s_k = sd_k * np.sqrt(1 + 1.0 / n_refs)

        gaps.append(gap)
        sk_values.append(float(s_k))

    optimal_k = k_values[-1]  # fallback
    for i in range(len(gaps) - 1):
        if gaps[i] >= gaps[i + 1] - sk_values[i + 1]:
            optimal_k = k_values[i]
            break

    logger.info(f"Gap statistic optimal K: {optimal_k}")

    return {
        "k_values": k_values,
        "gaps": gaps,
        "sk": sk_values,
        "optimal_k": optimal_k,
    }


def find_optimal_eps(X: FloatArray, min_samples: int) -> dict:
    """Calibrate DBSCAN eps from sorted k-distance elbow (Kneedle); k = min_samples - 1."""
    k = max(1, min_samples - 1)

    nn = NearestNeighbors(n_neighbors=k + 1, n_jobs=-1)
    nn.fit(np.asarray(X, dtype=np.float64))
    distances, _ = nn.kneighbors(np.asarray(X, dtype=np.float64))

    k_distances = np.sort(distances[:, -1])[::-1]

    x_indices = np.arange(len(k_distances))
    kneedle = KneeLocator(
        x_indices, k_distances, curve="convex", direction="decreasing"
    )

    knee_idx = kneedle.knee
    if knee_idx is None:
        optimal_eps = float(np.median(k_distances))
        logger.warning(
            f"Knee not found in k-distance curve. "
            f"Falling back to median: eps={optimal_eps:.4f}"
        )
    else:
        optimal_eps = float(k_distances[knee_idx])
        logger.info(f"K-distance knee at index {knee_idx}, eps={optimal_eps:.4f}")

    return {
        "optimal_eps": optimal_eps,
        "k_distances": k_distances,
        "knee_index": knee_idx,
    }
