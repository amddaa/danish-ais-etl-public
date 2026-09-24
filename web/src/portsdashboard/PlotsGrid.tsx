function PlotCard({
  title,
  src,
  alt,
  caption,
  wide,
}: {
  title: string;
  src: string;
  alt: string;
  caption: string;
  wide?: boolean;
}) {
  return (
    <div className={"plot-card" + (wide ? " plot-card--wide" : "")}>
      <h3 className="plot-card__title">{title}</h3>
      <img className="plot-card__img" src={src} alt={alt} />
      <p className="plot-card__caption">{caption}</p>
    </div>
  );
}

export function PlotsGrid({ profile, basePath }: { profile: string; basePath: string }) {
  const img = (name: string) => `${basePath}${name}_${profile}.png`;

  return (
    <div id="plots-container" className="plots-grid">
      <div className="plots-grid__pair">
        <PlotCard
          title="Model Selection Metrics (K-Means)"
          src={img("model_selection")}
          alt="Model Selection"
          caption="Multi-index evaluation comparing WCSS, Silhouette score, Davies-Bouldin index, and Gap statistic across candidate cluster counts."
        />
        <PlotCard
          title="DBSCAN Epsilon Calibration"
          src={img("k_distance_elbow")}
          alt="K-Distance Elbow"
          caption="Sorted k-distance curve for Epsilon calibration. The detected knee point represents the optimal search radius eps."
        />
        <PlotCard
          title="UMAP Manifold Projection"
          src={img("umap_projection")}
          alt="UMAP Projection"
          caption="2D manifold projection using UMAP to verify cluster separation. Point sizes correspond to vessel visit frequency."
        />
        <PlotCard
          title="PCA Explained Variance"
          src={img("pca_scree")}
          alt="PCA Scree Plot"
          caption="Scree plot demonstrating the individual and cumulative explained variance ratio per principal component against the 85% target threshold."
        />
      </div>
      <PlotCard
        wide
        title="t-SNE Perplexity Tuning Grid"
        src={img("tsne_tuning")}
        alt="t-SNE Tuning Grid"
        caption="Comparison of t-SNE projections at multiple perplexity values to assess topological cluster stability."
      />
    </div>
  );
}
