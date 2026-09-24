import psycopg2
import pandas as pd
import numpy as np
import os
import json
import logging
import re
try:
    from thefuzz import fuzz  # pyrefly: ignore[missing-import]
except ImportError:
    logging.critical("thefuzz library is missing")
    raise
import matplotlib.pyplot as plt
import seaborn as sns

from source.config.logger import setup_logging
logger = setup_logging(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "destination_accuracy")
os.makedirs(OUTPUT_DIR, exist_ok=True)



from source.config.db import get_db_connection

# Fuzzy match threshold
MATCH_THRESHOLD = 80

GARBAGE_PATTERNS = [
    r'^N/?A$', r'^ORDER', r'FOR ORDER', r'TBA', r'^UNKNOWN',
    r'^\?+$', r'^NONE$', r'^NOT DEFINED', r'^W$', r'^-$'
]

COUNTRY_ABBR = {
    "DK": "DENMARK",
    "SE": "SWEDEN",
    "PL": "POLAND",
    "DE": "GERMANY",
    "NO": "NORWAY",
    "FI": "FINLAND",
    "EE": "ESTONIA",
    "LV": "LATVIA",
    "LT": "LITHUANIA",
    "RU": "RUSSIA",
    "NL": "NETHERLANDS",
    "BE": "BELGIUM",
    "GB": "UNITED KINGDOM",
    "UK": "UNITED KINGDOM"
}



def fetch_destination_data():
    logger.info("Fetching port visit destination data from PostgreSQL...")
    query = """
        SELECT
            v.id,
            v.declared_destination,
            p.name                  AS actual_port_name,
            p.name_alternate        AS actual_port_name_alt,
            p.un_locode             AS un_locode,
            v.ship_type
        FROM public.port_visits v
        JOIN public.ports p ON v.port_id = p.id
        WHERE v.declared_destination IS NOT NULL
          AND v.declared_destination != '';
    """
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn)
        logger.info(f"Loaded {len(df)} records with declared destinations.")
        return df
    finally:
        conn.close()

NORDIC_CHARS = {
    'Ø': 'O', 'Æ': 'AE', 'Å': 'AA', 'Ä': 'A', 'Ö': 'O', 'Ü': 'U', 'ß': 'SS',
    'É': 'E', 'È': 'E'
}

OPERATIONAL_PREFIXES = re.compile(
    r'^(OPERATING|GUARD VESSEL|FBC CONSTR\.?\s*VESSEL|FBC SURVEY VSL|FLC PORT TENDER|'
    r'FBC CONSTR\.?|SURVEY VSL|PORT TENDER|STORSTROMBELT ASSIST|'
    r'FERRYSERVICE|ROUTE|AT ANCHOR OFF)\s*',
    re.IGNORECASE
)

LOCODE_COMPACT_RE = re.compile(r'^([A-Z]{2})([A-Z0-9]{3})$')
LOCODE_SPACED_RE  = re.compile(r'^([A-Z]{2})\s+([A-Z0-9]{3})$')

ROUTE_SEP_RE = re.compile(r'\s*(<-->|<->|<>|->)\s*')


def normalize_locode(text):
    t = text.strip().upper()
    m = LOCODE_SPACED_RE.match(t)
    if m:
        return m.group(1) + m.group(2)
    return t


def extract_declared_candidates(raw):
    text = raw.strip().upper()

    # Strip operational prefixes (e.g. 'OPERATING SKAW' -> 'SKAW')
    text_stripped = OPERATIONAL_PREFIXES.sub('', text).strip()

    # Always keep full original as fuzzy fallback
    candidates = {text}
    if text_stripped != text:
        candidates.add(text_stripped)

    # Split on arrow separators; take last segment as destination
    arrow_parts = ROUTE_SEP_RE.split(text_stripped)
    arrow_parts = [p.strip() for p in arrow_parts if p and not ROUTE_SEP_RE.fullmatch(p.strip())]

    if len(arrow_parts) > 1:
        dest_part = arrow_parts[-1]
    else:
        dest_part = text_stripped

    # Strip trailing /... or =... suffixes (e.g. 'DKRNN /DUMPING AREA', 'DKCPH=KRIEGERS')
    dest_part = re.split(r'[/=]', dest_part)[0].strip()

    if dest_part:
        dest_norm = normalize_locode(dest_part)
        candidates.add(dest_part)
        candidates.add(dest_norm)

        # Dash-split LOCODEs; take last token (e.g. 'DKFDH-SEGOT' -> 'SEGOT')
        dash_parts = re.split(r'-(?=[A-Z]{2}[A-Z0-9]{2,3})', dest_norm)
        if len(dash_parts) > 1:
            last_dp = dash_parts[-1].strip()
            if last_dp:
                candidates.add(last_dp)
                candidates.add(normalize_locode(last_dp))

    return [c for c in candidates if c]


def clean_string(text):
    if not isinstance(text, str):
        return ""
    text = text.upper()

    for k, v in NORDIC_CHARS.items():
        text = text.replace(k, v)

    for abbr, full_name in COUNTRY_ABBR.items():
        text = re.sub(rf'\b{abbr}\b', full_name, text)

    port_words = [
        r'\bHAVN\b', r'\bHAMN\b', r'\bPORT\b', r'\bMARINA\b',
        r'\bHARBOUR\b', r'\bHARBOR\b', r'\bTERMINAL\b', r'\bRO PA\b',
        r'\bRO RO\b', r'\bFERRY\b', r'\bLYSTBADEHAVN\b'
    ]
    for pw in port_words:
        text = re.sub(pw, '', text)

    text = re.sub(r'[^A-Z0-9\s]', ' ', text)

    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_garbage(text):
    text_clean = re.sub(r'[^A-Z]', '', text.upper())
    if not text_clean:
        return True

    raw_upper = text.upper().strip()
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, raw_upper):
            return True
    return False

def _try_match_candidate(candidate, un_locode, cleaned_actual, cleaned_alt):
    cand = candidate.strip()
    if not cand:
        return False

    locode_norm = normalize_locode(un_locode) if un_locode else ''
    if locode_norm and cand == locode_norm:
        return True
    if un_locode and cand == un_locode.upper():
        return True

    if un_locode and len(un_locode) == 5:
        city_code = un_locode[2:].upper()
        if city_code and cand == city_code:
            return True

    cleaned_cand = clean_string(cand)
    if not cleaned_cand:
        return False

    score = max(
        fuzz.token_sort_ratio(cleaned_cand, cleaned_actual),
        fuzz.token_set_ratio(cleaned_cand, cleaned_actual)
    )
    if score >= MATCH_THRESHOLD:
        return True

    if cleaned_alt:
        alt_score = max(
            fuzz.token_sort_ratio(cleaned_cand, cleaned_alt),
            fuzz.token_set_ratio(cleaned_cand, cleaned_alt)
        )
        if alt_score >= MATCH_THRESHOLD:
            return True

    return False


def evaluate_match(row):
    declared   = str(row['declared_destination']).strip()
    actual     = str(row['actual_port_name']).strip()
    un_locode  = str(row.get('un_locode',          '') or '').strip().upper()
    actual_alt = str(row.get('actual_port_name_alt','') or '').strip()

    if not declared:
        return "GARBAGE"
    if is_garbage(declared):
        return "GARBAGE"

    cleaned_actual = clean_string(actual)
    cleaned_alt    = clean_string(actual_alt) if actual_alt else ''

    candidates = extract_declared_candidates(declared)

    if not any(c.strip() for c in candidates):
        return "GARBAGE"

    for cand in candidates:
        if _try_match_candidate(cand.upper(), un_locode, cleaned_actual, cleaned_alt):
            return "MATCH"

    return "MISMATCH"

def process_accuracy(df):
    logger.info("Cleaning strings and classifying results (this may take a moment due to fuzzy matching)...")

    df['match_status']    = df.apply(evaluate_match, axis=1)
    df['cleaned_declared'] = df['declared_destination'].apply(clean_string)
    df['cleaned_actual']   = df['actual_port_name'].apply(clean_string)

    return df

def generate_statistics(df):
    logger.info("Aggregating statistics...")

    total_records = len(df)
    match_counts  = df['match_status'].value_counts()

    overall_stats = {
        "total_evaluated": total_records,
        "matches":    int(match_counts.get("MATCH",    0)),
        "mismatches": int(match_counts.get("MISMATCH", 0)),
        "garbage":    int(match_counts.get("GARBAGE",  0)),
        "match_rate_pct": float((match_counts.get("MATCH", 0) / total_records) * 100) if total_records else 0.0
    }

    by_ship_type = {}
    for stype, group in df.groupby('ship_type'):
        if not stype or not str(stype).strip():
            continue

        st_counts = group['match_status'].value_counts()
        st_total  = len(group)
        if st_total > 50:
            matches = int(st_counts.get("MATCH", 0))
            by_ship_type[str(stype)] = {
                "total":      st_total,
                "matches":    matches,
                "mismatches": int(st_counts.get("MISMATCH", 0)),
                "garbage":    int(st_counts.get("GARBAGE",  0)),
                "match_rate_pct": float((matches / st_total) * 100)
            }

    by_ship_type = dict(sorted(by_ship_type.items(), key=lambda item: item[1]['match_rate_pct'], reverse=True))

    garbage_df  = df[df['match_status'] == "GARBAGE"].copy()
    top_garbage = garbage_df['declared_destination'].value_counts().head(50).to_dict()

    match_df = df[df['match_status'] == "MATCH"].copy()
    match_df['match_pair'] = (
        "DECLARED: '" + match_df['declared_destination'] +
        "' -> ACTUAL: '" + match_df['actual_port_name'] +
        "' [" + match_df['un_locode'].fillna('?') + "]"
    )
    top_matches = match_df['match_pair'].value_counts().head(50).to_dict()

    mismatch_df = df[df['match_status'] == "MISMATCH"].copy()
    mismatch_df['err_pair'] = (
        "DECLARED: '" + mismatch_df['declared_destination'] +
        "' -> ACTUAL: '" + mismatch_df['actual_port_name'] +
        "' [" + mismatch_df['un_locode'].fillna('?') + "]"
    )
    top_mismatches = mismatch_df['err_pair'].value_counts().head(50).to_dict()

    by_locode = {}
    locode_group = df.groupby('un_locode', dropna=False)
    for locode, g in locode_group:
        lkey = str(locode) if pd.notna(locode) else "N/A"
        lc   = g['match_status'].value_counts()
        lt   = len(g)
        if lt < 10:
            continue
        by_locode[lkey] = {
            "port_name":      str(g['actual_port_name'].iloc[0]),
            "total":          lt,
            "matches":        int(lc.get("MATCH",    0)),
            "mismatches":     int(lc.get("MISMATCH", 0)),
            "garbage":        int(lc.get("GARBAGE",  0)),
            "match_rate_pct": float(lc.get("MATCH", 0) / lt * 100),
        }
    by_locode = dict(sorted(by_locode.items(), key=lambda x: x[1]['match_rate_pct'], reverse=True))

    stats = {
        "overall": overall_stats,
        "by_ship_type": by_ship_type,
        "by_un_locode": by_locode,
        "top_matches_count_50":    {str(k): int(v) for k, v in top_matches.items()},
        "top_mismatches_count_50": {str(k): int(v) for k, v in top_mismatches.items()},
        "top_garbage_strings_50":  {str(k): int(v) for k, v in top_garbage.items()},
    }

    out_file = os.path.join(OUTPUT_DIR, "destination_accuracy_stats.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=4)

    logger.info(f"Statistics dumped to {out_file}")
    return stats, df

def plot_heatmap(df):
    logger.info("Generating Heatmap for Top Mismatches...")

    mismatch_df = df[df['match_status'] == "MISMATCH"].copy()
    if mismatch_df.empty:
        logger.warning("No mismatches found, skipping heatmap.")
        return

    mismatch_df['port_label'] = mismatch_df.apply(
        lambda r: r['un_locode'] if (pd.notna(r['un_locode']) and str(r['un_locode']) not in ('', 'N/A', 'nan'))
                  else r['actual_port_name'],
        axis=1
    )

    top_ports    = mismatch_df['port_label'].value_counts().nlargest(15).index
    filtered_df  = mismatch_df[mismatch_df['port_label'].isin(top_ports)]

    top_declared = filtered_df['cleaned_declared'].value_counts().nlargest(15).index
    filtered_df  = filtered_df[filtered_df['cleaned_declared'].isin(top_declared)]

    if filtered_df.empty:
        return

    matrix = filtered_df.groupby(["port_label", "cleaned_declared"]).size().unstack(fill_value=0)

    plt.figure(figsize=(14, 10))
    sns.heatmap(matrix, annot=True, fmt="d", cmap="YlOrRd", linewidths=.5)
    plt.title("Confusion Matrix: Declared Destination vs Actual Arrival Port (Top Mismatches)", fontsize=16, fontweight='bold')
    plt.xlabel("Declared Destination (Cleaned)", fontsize=12)
    plt.ylabel("Actual Port (UN/LOCODE)", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    plot_path = os.path.join(OUTPUT_DIR, "plot_destination_mismatches_heatmap.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    logger.info(f"Heatmap saved to {plot_path}")

def plot_match_rates(stats):
    logger.info("Generating Barplot for Match Rates...")

    ship_types = list(stats['by_ship_type'].keys())
    rates      = [stats['by_ship_type'][st]['match_rate_pct'] for st in ship_types]

    if not ship_types:
        return

    plt.figure(figsize=(12, 6))
    ax = sns.barplot(x=rates, y=ship_types, palette="viridis", hue=ship_types, legend=False)

    for i, v in enumerate(rates):
        ax.text(v + 0.5, i, f"{v:.1f}%", color='black', va='center')

    plt.title("AIS Destination Accuracy (Match Rate) by Ship Type", fontsize=14, fontweight='bold')
    plt.xlabel("Match Rate (%)", fontsize=12)
    plt.ylabel("Ship Type", fontsize=12)
    plt.xlim(0, 100)
    plt.tight_layout()

    plot_path = os.path.join(OUTPUT_DIR, "plot_destination_accuracy_by_shiptype.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    logger.info(f"Barplot saved to {plot_path}")

def run_module_2():
    logger.info("Starting Module 2: Destination vs Reality...")
    try:
        df = fetch_destination_data()
        if df.empty:
            logger.warning("No data found for destination analysis.")
            return

        df = process_accuracy(df)
        stats, processed_df = generate_statistics(df)

        plot_heatmap(processed_df)
        plot_match_rates(stats)

        logger.info("Module 2 finished successfully!")
    except Exception as e:
        logger.error(f"Fatal error in Module 2: {e}")
        raise

if __name__ == "__main__":
    run_module_2()
