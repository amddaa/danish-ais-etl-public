import psycopg2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import json
import logging
from typing import Any

from source.config.logger import setup_logging
logger = setup_logging(__name__)



from source.config.db import get_db_connection

# Output Directory Configuration
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "port_visit_times")
os.makedirs(OUTPUT_DIR, exist_ok=True)



def fetch_port_visits():
    """
    Fetches all finalized port visits from the database.

    Join chain:
        port_visits (v)
        -> ports    (p)   -- WPI port (UN/LOCODE level); port_visits.port_id = ports.id
    """
    logger.info("Fetching port visits from PostgreSQL...")
    query = """
        SELECT
            v.id,
            v.mmsi,
            v.port_id,
            v.arrival_time,
            v.departure_time,
            v.stay_duration_hours,
            v.ship_type,
            -- WPI port-level fields
            p.name                                  AS port_name,
            COALESCE(p.un_locode, 'N/A')            AS un_locode,
            COALESCE(p.country_code, 'XX')          AS country_code,
            p.harbor_size,
            p.harbor_type,
            p.max_vessel_draft_m,
            ST_X(p.geom::geometry)                  AS port_lon,
            ST_Y(p.geom::geometry)                  AS port_lat
        FROM public.port_visits v
        JOIN public.ports p ON v.port_id = p.id
        WHERE v.stay_duration_hours IS NOT NULL
          AND v.stay_duration_hours >= 1.0;  -- Exclude technical noise < 1h
    """

    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn)
        logger.info(f"Successfully loaded {len(df)} port visits.")
        return df
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        raise
    finally:
        conn.close()

def compute_statistics(df):
    """
    Computes global and per-category statistics for all port stay durations.
    Groups results cleanly into a structured JSON artifact.
    """
    logger.info("Computing stay duration statistics...")

    def get_stats_for_group(group_df):
        return {
            "total_visits": len(group_df),
            "mean_hours": float(group_df['stay_duration_hours'].mean()),
            "median_hours": float(group_df['stay_duration_hours'].median()),
            "std_dev_hours": float(group_df['stay_duration_hours'].std()),
            "min_hours": float(group_df['stay_duration_hours'].min()),
            "max_hours": float(group_df['stay_duration_hours'].max()),
            "percentiles": {
                "25th": float(group_df['stay_duration_hours'].quantile(0.25)),
                "50th": float(group_df['stay_duration_hours'].quantile(0.50)),
                "75th": float(group_df['stay_duration_hours'].quantile(0.75)),
                "90th": float(group_df['stay_duration_hours'].quantile(0.90)),
                "95th": float(group_df['stay_duration_hours'].quantile(0.95)),
                "99th": float(group_df['stay_duration_hours'].quantile(0.99))
            }
        }

    stats = {
        "global": get_stats_for_group(df),
        "by_ship_type": {}
    }

    # Calculate for each meaningful ship_type (ignoring very rare occurrences)
    df_clean = df.dropna(subset=['ship_type']).copy()
    for ship_type, group in df_clean.groupby('ship_type'):
        if ship_type.strip() and len(group) > 100:
            stats["by_ship_type"][ship_type] = get_stats_for_group(group)

    output_file = os.path.join(OUTPUT_DIR, "global_duration_statistics.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=4)

    logger.info(f"Detailed statistics saved to {output_file}")
    return stats

def perform_binning(df):
    """
    Segments continuous duration data into categorical time bins (bucketing).
    Highlights the crucial 24h, 48h marks for rule evaluation with high granularity on small ranges.
    """
    logger.info("Performing statistical binning (bucketing)...")

    # Custom high-granularity bins for smaller timeframes (hours)
    bins = [0, 2, 4, 6, 8, 12, 18, 24, 36, 48, 72, 168, float('inf')]
    labels = [
        "< 2h", "2-4h", "4-6h", "6-8h", "8-12h",
        "12-18h", "18-24h", "24-36h", "36-48h",
        "48-72h", "3-7 Days", "> 7 Days"
    ]

    df['duration_bin'] = pd.cut(df['stay_duration_hours'], bins=bins, labels=labels, right=False)

    # Calculate counts per bin globally
    bin_counts = df['duration_bin'].value_counts().sort_index().reset_index()
    bin_counts.columns = ['Time_Range', 'Visit_Count']
    bin_counts['Percentage'] = (bin_counts['Visit_Count'] / len(df) * 100).round(2)

    output_file = os.path.join(OUTPUT_DIR, "binned_durations.csv")
    bin_counts.to_csv(output_file, index=False)
    logger.info(f"Binned statistics saved to {output_file}")

    return bin_counts

def plot_histograms(df, bin_counts):
    """
    Generates professional plots to visualize the distribution of stay lengths
    and identify any cutoff behaviors (e.g., 24h rule validation).
    """
    logger.info("Generating plot visualizations...")
    sns.set_theme(style="whitegrid", context="paper")

    # 1. Bar Chart: Binned Distribution
    plt.figure(figsize=(10, 6))
    sns.barplot(data=bin_counts, x='Time_Range', y='Visit_Count', hue='Time_Range', palette="viridis", legend=False)
    plt.title("Distribution of Port Stay Durations by Time Range", fontsize=14, fontweight='bold')
    plt.xlabel("Time Range", fontsize=12)
    plt.ylabel("Number of Visits", fontsize=12)

    # Add percentage labels on top of bars
    for idx, row in bin_counts.iterrows():
        plt.text(idx, row['Visit_Count'] + (bin_counts['Visit_Count'].max() * 0.01),
                 f"{row['Percentage']}%", color='black', ha="center", fontsize=10)

    binned_plot_path = os.path.join(OUTPUT_DIR, "plot_binned_distribution.png")
    plt.tight_layout()
    plt.savefig(binned_plot_path, dpi=300)
    plt.close()

    # 2. Histogram: Zoomed in on 0 to 72 hours (High Resolution)
    zoomed_df = df[df['stay_duration_hours'] <= 72.0]

    plt.figure(figsize=(12, 6))
    sns.histplot(zoomed_df['stay_duration_hours'], bins=72, kde=True, color="#2E86AB")
    plt.axvline(x=24, color='red', linestyle='--', linewidth=2, label="24h Mark")
    plt.axvline(x=48, color='orange', linestyle='--', linewidth=2, label="48h Mark")

    plt.title("High-Resolution Histogram of Port Stays (0 - 72 Hours)", fontsize=14, fontweight='bold')
    plt.xlabel("Stay Duration (Hours)", fontsize=12)
    plt.ylabel("Number of Visits", fontsize=12)
    plt.legend()

    zoomed_plot_path = os.path.join(OUTPUT_DIR, "plot_0_to_72h_histogram.png")
    plt.tight_layout()
    plt.savefig(zoomed_plot_path, dpi=300)
    plt.close()

    logger.info(f"Global plots saved successfully.")

def plot_histograms_by_shiptype(df):
    """
    Generates plots of stay durations broken down by ship type.
    Shows all ship types on boxplots, but groups tails into 'Other' for density plots.
    """
    logger.info("Generating plots per ship category...")

    # Clean data: drop None or empty ship types
    df_clean = df.dropna(subset=['ship_type']).copy()
    df_clean = df_clean[df_clean['ship_type'].str.strip() != ""]

    if df_clean.empty:
        logger.warning("No ship types found in data to plot per-category.")
        return

    # Get all ship types ordered by frequency
    ordered_ship_types = df_clean['ship_type'].value_counts().index.tolist()

    # Plot 1: Boxplot of stay durations (All Ship Types)
    fig_height = max(8, len(ordered_ship_types) * 0.5)
    plt.figure(figsize=(12, fig_height))

    zoomed_box = df_clean[df_clean['stay_duration_hours'] <= 168.0]

    ax = sns.boxplot(data=zoomed_box, x='stay_duration_hours', y='ship_type', hue='ship_type',
                order=ordered_ship_types, palette="Set2", legend=False, showfliers=False)

    plt.xlim(0, None)
    plt.title("Distribution of Port Stays by Ship Category (Up to 7 Days, Outliers Removed)", fontsize=14, fontweight='bold')
    plt.xlabel("Stay Duration (Hours)", fontsize=12)
    plt.ylabel("Ship Type", fontsize=12)

    boxplot_path = os.path.join(OUTPUT_DIR, "plot_duration_boxplot_by_shiptype.png")
    plt.tight_layout()
    plt.savefig(boxplot_path, dpi=300)
    plt.close()

    # Plot 2: Density Overlay (0 - 72h) separated by Ship Type (Top 5 + Other)
    top_5 = ordered_ship_types[:5]
    df_clean['ship_type_grouped'] = df_clean['ship_type'].apply(lambda x: x if x in top_5 else "Other")

    group_order = top_5 + ["Other"] if "Other" in df_clean['ship_type_grouped'].values else top_5

    plt.figure(figsize=(14, 8))
    zoomed_hist = df_clean[df_clean['stay_duration_hours'] <= 72.0]

    sns.kdeplot(data=zoomed_hist, x='stay_duration_hours', hue='ship_type_grouped',
                hue_order=group_order, fill=True, common_norm=False, palette="Set2", alpha=0.5)
    plt.axvline(x=24, color='red', linestyle='--', linewidth=2, label="24h Mark")
    plt.axvline(x=48, color='orange', linestyle='--', linewidth=2, label="48h Mark")

    plt.title("Density of Port Stays (0 - 72 Hours) per Ship Category", fontsize=14, fontweight='bold')
    plt.xlabel("Stay Duration (Hours)", fontsize=12)
    plt.ylabel("Density", fontsize=12)

    hist_path = os.path.join(OUTPUT_DIR, "plot_0_to_72h_density_by_shiptype.png")
    plt.tight_layout()
    plt.savefig(hist_path, dpi=300)
    plt.close()

    logger.info("Ship category plots saved successfully.")

def compute_port_specific_statistics(df):
    """
    Computes per-port numerical statistics grouped at the WPI port level.
    Groups by un_locode where available, falls back to port_id.
    The stat key is always the UN/LOCODE of the city/port (e.g. 'PLGDY').
    """
    logger.info("Computing per-port statistics (UN/LOCODE level)...")

    port_stats: dict[str, dict[str, Any]] = {}

    # Primary grouping key: un_locode (city/port level).
    # Visits without a locode are grouped under their port_id as fallback.
    df = df.copy()
    df['group_key'] = df.apply(
        lambda r: r['un_locode'] if (pd.notna(r['un_locode']) and r['un_locode'] != 'N/A') else f"PORT_{r['port_id']}",
        axis=1
    )

    for group_key, group_df in df.groupby('group_key'):
        port_name    = group_df['port_name'].iloc[0]
        un_locode    = group_df['un_locode'].iloc[0]
        country_code = group_df['country_code'].iloc[0]
        harbor_size  = group_df['harbor_size'].iloc[0]  if 'harbor_size'  in group_df.columns else None
        harbor_type  = group_df['harbor_type'].iloc[0]  if 'harbor_type'  in group_df.columns else None
        max_draft    = group_df['max_vessel_draft_m'].iloc[0] if 'max_vessel_draft_m' in group_df.columns else None
        port_lon     = group_df['port_lon'].iloc[0]
        port_lat     = group_df['port_lat'].iloc[0]

        lon = float(port_lon) if pd.notna(port_lon) else None
        lat = float(port_lat) if pd.notna(port_lat) else None

        total = len(group_df)
        if total == 0:
            continue

        mean_h   = group_df['stay_duration_hours'].mean()
        median_h = group_df['stay_duration_hours'].median()

        by_ship = {}
        for stype, sgroup in group_df.groupby('ship_type'):
            if stype and str(stype).strip():
                by_ship[str(stype)] = {
                    "total_visits": len(sgroup),
                    "mean_hours":   float(sgroup['stay_duration_hours'].mean()),
                    "median_hours": float(sgroup['stay_duration_hours'].median()),
                }

        port_stats[str(group_key)] = {
            "un_locode":    str(un_locode),
            "port_name":    str(port_name),
            "country_code": str(country_code),
            "harbor_size":  str(harbor_size) if harbor_size else None,
            "harbor_type":  str(harbor_type) if harbor_type else None,
            "max_vessel_draft_m": float(max_draft) if pd.notna(max_draft) else None,
            "coordinates":  {"longitude": lon, "latitude": lat},
            "overall_statistics": {
                "total_visits": total,
                "mean_hours":   float(mean_h),
                "median_hours": float(median_h),
            },
            "by_ship_type": by_ship,
        }

    # Sort ports by total_visits descending
    port_stats_sorted = dict(
        sorted(port_stats.items(), key=lambda x: int(x[1]['overall_statistics']['total_visits']), reverse=True)
    )

    output_file = os.path.join(OUTPUT_DIR, "port_specific_statistics.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(port_stats_sorted, f, indent=4)

    logger.info(f"Port specific statistics saved to {output_file}")
    return port_stats_sorted

def run_analysis():
    logger.info("Starting Port Stay Duration Analysis (Module 1)...")

    try:
        # 1. Fetch
        visits_df = fetch_port_visits()
        if visits_df.empty:
            logger.warning("No visits data found. Have you successfully run port_visit_extractor.py?")
            return

        # 2. Global Statistics
        compute_statistics(visits_df)
        compute_port_specific_statistics(visits_df)

        # 3. Binning
        binned_stats = perform_binning(visits_df)

        # 4. Visualizations
        plot_histograms(visits_df, binned_stats)
        plot_histograms_by_shiptype(visits_df)

        logger.info("Analysis complete! All artifacts dumped properly.")

    except Exception as e:
        logger.error(f"Analysis encountered a fatal execution error: {e}")
        raise

if __name__ == "__main__":
    run_analysis()
