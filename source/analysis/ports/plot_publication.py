
import os
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from source.analysis.ports.array_types import FloatArray, NdArray
from source.config.logger import setup_logging

logger = setup_logging(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "plots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

COLORS = {
    "blue": "#1f77b4",
    "red": "#d62728",
    "green": "#2ca02c",
    "orange": "#ff7f0e",
    "graphite": "#343a40",
    "knee_red": "#e63946",
}

CLUSTER_PALETTE = [
    "#3b82f6",  # Royal Blue
    "#10b981",  # Mint
    "#f59e0b",  # Orange
    "#8b5cf6",  # Purple
    "#ef4444",  # Red
    "#06b6d4",  # Cyan
    "#ec4899",  # Pink
    "#14b8a6",  # Teal
]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 100,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})


def _save_figure(fig: plt.Figure, name: str) -> None:
    png_path = os.path.join(OUTPUT_DIR, f"{name}.png")
    svg_path = os.path.join(OUTPUT_DIR, f"{name}.svg")
    fig.savefig(png_path, dpi=150, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info(f"Plot saved: {png_path} + {svg_path}")


def plot_multi_index_selection(
    results: dict,
    optimal_k: int,
    profile_label: str = "",
) -> None:
    """Dual-axis WCSS/Silhouette vs DBI/Gap with optimal-K marker."""
    k_vals = results["k_values"]

    # Normalize WCSS to [0, 1] for dual-axis comparability
    wcss = np.array(results["wcss"])
    wcss_norm = (wcss - wcss.min()) / (wcss.max() - wcss.min() + 1e-9)

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()

    ax1.plot(
        k_vals, wcss_norm, "o-",
        color=COLORS["blue"], label="WCSS (normalized)", linewidth=1.5,
    )
    ax1.plot(
        k_vals, results["silhouette"], "s-",
        color=COLORS["green"], label="Silhouette Score", linewidth=1.5,
    )
    ax1.set_xlabel("Number of Clusters (K)")
    ax1.set_ylabel("WCSS (norm.) / Silhouette Score", color=COLORS["blue"])
    ax1.tick_params(axis="y", labelcolor=COLORS["blue"])
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))

    ax2.plot(
        k_vals, results["davies_bouldin"], "^-",
        color=COLORS["red"], label="Davies-Bouldin Index", linewidth=1.5,
    )
    ax2.plot(
        k_vals, results["gap_values"], "d-",
        color=COLORS["orange"], label="Gap Statistic", linewidth=1.5,
    )
    ax2.set_ylabel("DBI / Gap Statistic", color=COLORS["red"])
    ax2.tick_params(axis="y", labelcolor=COLORS["red"])

    ax1.axvline(
        x=optimal_k, color="black", linestyle="--", linewidth=1.2,
        label=f"Optimal K = {optimal_k}",
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="upper right", framealpha=0.9, edgecolor="#e2e8f0",
    )

    fig.tight_layout()
    name = f"model_selection_{profile_label}" if profile_label else "model_selection"
    _save_figure(fig, name)


def plot_k_distance_elbow(
    k_distances: NdArray,
    optimal_eps: float,
    knee_index: int | None,
    profile_label: str = "",
) -> None:
    """Sorted k-NN distances with knee highlighted for DBSCAN eps."""
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        range(len(k_distances)), k_distances,
        color=COLORS["graphite"], linewidth=1.5,
    )

    if knee_index is not None:
        ax.scatter(
            [knee_index], [k_distances[knee_index]],
            color=COLORS["knee_red"], s=120, zorder=5, edgecolors="black",
            linewidths=0.8,
        )
        ax.annotate(
            f"eps = {optimal_eps:.2f}",
            xy=(knee_index, k_distances[knee_index]),
            xytext=(knee_index + len(k_distances) * 0.05, optimal_eps * 1.15),
            fontsize=10, fontweight="bold", color=COLORS["knee_red"],
            arrowprops=dict(
                arrowstyle="->", color=COLORS["knee_red"], lw=1.2,
            ),
        )

    ax.set_xlabel("Port Index (sorted by descending distance)")
    ax.set_ylabel("Distance to k-th Nearest Neighbor")

    fig.tight_layout()
    name = f"k_distance_elbow_{profile_label}" if profile_label else "k_distance_elbow"
    _save_figure(fig, name)


def plot_umap_projection(
    X_scaled: FloatArray,
    labels: NdArray,
    port_names: list[str],
    total_visits: NdArray,
    cluster_names: dict[int, str],
    profile_label: str = "",
    random_state: int = 42,
) -> None:
    """2D UMAP colored by cluster; marker size ~ log1p(total_visits)."""
    try:
        import umap
    except ImportError:
        logger.error("umap-learn not installed. Install via: pip install umap-learn")
        return

    n_samples = X_scaled.shape[0]
    n_neighbors = min(15, max(2, n_samples - 1))

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.1,
        random_state=random_state,
    )
    X_umap = np.asarray(
        reducer.fit_transform(np.asarray(X_scaled, dtype=np.float64)),
        dtype=np.float64,
    )

    fig, ax = plt.subplots(figsize=(10, 7))

    unique_labels = sorted(set(labels))
    sizes = np.log1p(total_visits) * 15

    for i, cluster_id in enumerate(unique_labels):
        mask = labels == cluster_id
        color = CLUSTER_PALETTE[i % len(CLUSTER_PALETTE)] if cluster_id >= 0 else "#94a3b8"
        name = cluster_names.get(cluster_id, f"Cluster {cluster_id}")

        ax.scatter(
            X_umap[mask, 0], X_umap[mask, 1],
            s=sizes[mask], c=color, alpha=0.8,
            edgecolors="black", linewidths=0.5,
            label=name,
        )

    ax.set_xlabel("UMAP Component 1")
    ax.set_ylabel("UMAP Component 2")
    ax.legend(
        bbox_to_anchor=(1.02, 1), loc="upper left",
        framealpha=0.9, edgecolor="#e2e8f0",
    )

    fig.tight_layout()
    name = f"umap_projection_{profile_label}" if profile_label else "umap_projection"
    _save_figure(fig, name)


def plot_tsne_tuning(
    X_scaled: FloatArray,
    labels: NdArray,
    perplexities: list[int] | None = None,
    profile_label: str = "",
) -> None:
    """2x2 t-SNE grid over perplexity values (skips p >= n_samples)."""
    from sklearn.manifold import TSNE

    if perplexities is None:
        perplexities = [5, 15, 30, 50]

    n_samples = X_scaled.shape[0]
    perplexities = [p for p in perplexities if p < n_samples]

    if len(perplexities) == 0:
        logger.warning("No valid perplexities for t-SNE (sample size too small).")
        return

    while len(perplexities) < 4:
        perplexities.append(perplexities[-1])

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.ravel()

    unique_labels = sorted(set(labels))

    for i, perp in enumerate(perplexities[:4]):
        tsne = TSNE(
            n_components=2, perplexity=perp, random_state=42,
            init="pca", learning_rate="auto",
        )
        X_tsne = np.asarray(
            tsne.fit_transform(np.asarray(X_scaled, dtype=np.float64)),
            dtype=np.float64,
        )

        ax = axes[i]
        for j, cluster_id in enumerate(unique_labels):
            mask = labels == cluster_id
            color = CLUSTER_PALETTE[j % len(CLUSTER_PALETTE)] if cluster_id >= 0 else "#94a3b8"
            ax.scatter(
                X_tsne[mask, 0], X_tsne[mask, 1],
                c=color, alpha=0.8, edgecolors="k", linewidths=0.3,
                s=30,
            )
        ax.set_title(f"Perplexity = {perp}", fontsize=10, fontweight="bold")
        ax.set_xlabel("t-SNE Dim. 1")
        ax.set_ylabel("t-SNE Dim. 2")

    fig.tight_layout()
    name = f"tsne_tuning_{profile_label}" if profile_label else "tsne_tuning"
    _save_figure(fig, name)


def plot_explained_variance(
    explained_variance_ratio: NdArray,
    variance_threshold: float = 0.85,
    profile_label: str = "",
) -> None:
    """PCA scree plot with cumulative variance and threshold line."""
    n_components = len(explained_variance_ratio)
    cumulative = np.cumsum(explained_variance_ratio)
    x = range(1, n_components + 1)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(
        x, explained_variance_ratio * 100,
        color=COLORS["blue"], alpha=0.6, label="Individual",
    )

    ax.plot(
        x, cumulative * 100, "o-",
        color=COLORS["red"], linewidth=1.5, label="Cumulative",
    )

    ax.axhline(
        y=variance_threshold * 100, color=COLORS["graphite"],
        linestyle="--", linewidth=1.0,
        label=f"Threshold ({variance_threshold * 100:.0f}%)",
    )

    ax.set_xlabel("Principal Component")
    ax.set_ylabel("Explained Variance (%)")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(loc="center right", framealpha=0.9)
    ax.set_ylim(0, 105)

    fig.tight_layout()
    name = f"pca_scree_{profile_label}" if profile_label else "pca_scree"
    _save_figure(fig, name)
