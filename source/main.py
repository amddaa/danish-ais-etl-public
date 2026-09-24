from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import ujson
import logging
from dataclasses import dataclass
import math
import os
import time
import signal
import atexit
from typing import Any, Iterable, List, Optional, Dict
import uuid
import pandas as pd
import numpy as np
import psutil
import psycopg2
from psycopg2.extras import execute_batch
import csv
import io
import sys
from source.models import AISColumnsCSV, VesselsColumns, AISPositionsColumns
import pandas as pd
import numpy as np
from source.mappings import CSV_TO_VESSELS, CSV_TO_POSITIONS

import sys
import os


from source.config.logger import setup_logging
logger = setup_logging(__name__, log_file="ais_etl.log", level=logging.DEBUG)
APP_NAME = "ais_etl_loader"

from source.config.db import get_db_connection

_ETL_CONN_OVERRIDES = {
    "connect_timeout": 5,
    "application_name": APP_NAME,
    "options": "-c statement_timeout=300000",  # 5 minutes
}

CSV_FILES = [
    r"C:\Users\Adam\Desktop\mgr\data\aisdata\csv\aisdk-2024-12-30.csv",
    r"C:\Users\Adam\Desktop\mgr\data\aisdata\csv\aisdk-2024-12-31.csv",
]
COPY_MAX_WORKERS = 1  # one connection cannot run concurrent COPY
MERGE_MAX_WORKERS = 1
PRODUCER_QUEUE_MAXSIZE = 1
SUB_CHUNK_SIZE = 50_000
LARGE_FILE_ROW_THRESHOLD = 1_000_000
LARGE_FILE_CHUNK_SIZE = 500_000
ETA_SAMPLE_MIN = 100
ETA_SAMPLE_MAX = 5000
ETA_SAMPLE_SEED = 42

_active_conn = None

def cleanup_stale_connections():
    """Kill any stale connections from previous ETL runs."""
    try:
        conn = get_db_connection(**{**_ETL_CONN_OVERRIDES, "application_name": "ais_etl_cleanup"})
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE application_name = %s 
                AND pid != pg_backend_pid()
            """, (APP_NAME,))
            terminated = cur.rowcount
            if terminated > 0:
                logger.warning("🧹 Terminated %d stale ETL connections", terminated)
        conn.close()
    except Exception as e:
        logger.warning("Could not cleanup stale connections: %s", e)

def cleanup_on_exit():
    """Cleanup function called on normal exit or Ctrl+C."""
    global _active_conn
    if _active_conn:
        try:
            _active_conn.close()
            logger.info("🔌 Database connection closed gracefully")
        except:
            pass
        _active_conn = None

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    logger.warning("⚠️ Received interrupt signal, cleaning up...")
    cleanup_on_exit()
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

def is_file_processed(conn, file_path: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM etl_processed_files WHERE file_path = %s", (file_path,))
        return cur.fetchone() is not None

def mark_file_processed(conn, file_path: str, rows: int):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO etl_processed_files (file_path, rows_processed) VALUES (%s, %s)",
            (file_path, rows)
        )
        conn.commit()

_format_cache = {}

def auto_parse_datetime(series: pd.Series, name: str, utc: bool = True) -> pd.Series:
    s_orig = series.astype("string")
    n_total = len(s_orig)
    if logger:
        logger.debug(f"Auto-parsing datetime column: {name}")

    if np.issubdtype(np.dtype(str(series.dtype)), np.datetime64):
        if logger:
            logger.debug(f"{name} already datetime dtype")
        series_any: Any = series
        return series_any.dt.tz_localize("UTC") if utc else series

    s = s_orig.replace(["", "NaN", "nan", "None", "NULL", "null", "0", "0000-00-00 00:00:00"], np.nan)

    mask_num = s.str.fullmatch(r"\d+").fillna(False)
    parsed_num = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    if mask_num.any():
        nums = s[mask_num].astype(float)
        unit = "ms" if nums.astype(str).str.len().median() > 10 else "s"
        parsed_num.loc[mask_num] = pd.to_datetime(nums, unit=unit, utc=utc, errors="coerce")
        if logger:
            logger.debug(f"{name}: {mask_num.sum()} numeric epoch values parsed as {unit}")

    # Compact YYYYMMDD[HHMMSS]
    mask_compact = s.str.match(r"^\d{8,14}$").fillna(False)
    parsed_compact = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    if mask_compact.any():
        fmt = "%Y%m%d%H%M%S" if s[mask_compact].str.len().max() > 8 else "%Y%m%d"
        parsed_compact.loc[mask_compact] = pd.to_datetime(s[mask_compact], format=fmt, utc=utc, errors="coerce")
        if logger:
            logger.debug(f"{name}: {mask_compact.sum()} compact values parsed with {fmt}")

    mask_text = (~mask_num) & (~mask_compact) & s.notna()
    parsed_text = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")

    if mask_text.any():
        chunk_size = LARGE_FILE_CHUNK_SIZE if n_total > LARGE_FILE_ROW_THRESHOLD else n_total
        idx = mask_text[mask_text].index

        for i in range(0, len(idx), chunk_size):
            sub_idx = idx[i:i + chunk_size]
            sub_series = s.loc[sub_idx]

            # Prefer dayfirst when ambiguous (Danish AIS uses DD/MM/YYYY)
            if name not in _format_cache:
                sample = sub_series.sample(
                    n=min(ETA_SAMPLE_MAX, max(ETA_SAMPLE_MIN, len(sub_series))),
                    random_state=ETA_SAMPLE_SEED,
                )
                parsed_day = pd.to_datetime(sample, errors="coerce", utc=utc, dayfirst=True)
                parsed_not = pd.to_datetime(sample, errors="coerce", utc=utc, dayfirst=False)

                def conf(p):
                    ok = p.notna().mean()
                    if ok == 0: return 0
                    plausible = p.dt.year.between(1970, 2100).mean()
                    return ok * plausible

                c_d, c_nd = conf(parsed_day), conf(parsed_not)
                dayfirst = True if c_d >= c_nd else False  # prefer dayfirst if more parses correctly
                fmt = None
                _format_cache[name] = (fmt, dayfirst)
                if logger:
                    if abs(c_d - c_nd) < 0.05:
                        logger.debug(f"{name} ambiguous format (dayfirst diff <5%)")
                    else:
                        logger.debug(f"{name} detected dayfirst={dayfirst} (conf {c_d:.2f} vs {c_nd:.2f})")
            else:
                fmt, dayfirst = _format_cache[name]

            parsed_chunk = pd.to_datetime(sub_series, utc=utc, errors="coerce", dayfirst=dayfirst, format=fmt)
            parsed_text.loc[sub_idx] = parsed_chunk
            if logger:
                logger.debug(f"{name}: parsed {len(sub_idx)} rows")

    parsed = parsed_num.combine_first(parsed_compact).combine_first(parsed_text)

    n_bad = parsed.isna().sum()
    if n_bad > 0 and logger:
        top_bad = s_orig[parsed.isna()].value_counts(dropna=False).head(5)
        logger.warning(f"{name}: {n_bad} unparsed values. Top 5:")
        for i, (val, count) in enumerate(top_bad.items(), 1):
            logger.warning(f"   {i}. '{val}' ({count}×)")

    if logger:
        parsed_mask = parsed.notna()
        ambiguous = pd.DataFrame({"original": s_orig[parsed_mask], "parsed": parsed[parsed_mask]})
        ambiguous = ambiguous[ambiguous["original"].str.match(r"\d{2,4}[-/]\d{1,2}[-/]\d{1,4}", na=False)]
        if not ambiguous.empty:
            top_ambiguous = ambiguous.head(5)
            logger.warning(f"{name}: Top 5 parsed but potentially ambiguous cases:")
            for n, (_, row) in enumerate(top_ambiguous.iterrows(), 1):
                logger.warning(f"   {n}. original='{row['original']}', parsed='{row['parsed']}'")

    return parsed

def clean_ais_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    clean_start = time.perf_counter()
    logger.info("Cleaning AIS dataframe (%d rows, %d cols)", df.shape[0], df.shape[1])
    cols = AISColumnsCSV()
    dtype_map = cols.dtype_map()
    df = df.copy()

    num_cols = [c for c, t in dtype_map.items() if "float" in t or "int" in t]
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
    logger.debug("Replaced commas with dots in numeric columns")

    ts_col = cols.TIMESTAMP
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(
            df[ts_col], format="%d/%m/%Y %H:%M:%S", utc=True, errors="coerce"
        )
        logger.debug("Parsed TIMESTAMP column with fixed format")

    eta_col = cols.ETA
    if eta_col in df.columns:
        eta_start = time.perf_counter()
        # Use dayfirst=True since Danish AIS uses DD/MM/YYYY format
        df[eta_col] = pd.to_datetime(df[eta_col], dayfirst=True, utc=True, errors="coerce")
        logger.info("ETA parsing (dayfirst=True): %.2fs", time.perf_counter() - eta_start)

    for col, dtype in dtype_map.items():
        if col not in df.columns:
            continue
        if dtype == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        elif dtype == "Int64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    string_cols = [c for c in df.columns if c not in dtype_map]
    for col in string_cols:
        df[col] = df[col].astype("string").str.strip()

    logger.info("Cleaned dataframe (%d rows, %d columns) in %.2fs", len(df), len(df.columns), time.perf_counter() - clean_start)
    return df

def load_ais_csv(
    path: str,
    usecols: Optional[Iterable] = None,
    encoding: str = "utf-8",
    sep: str = ",",
    nrows: Optional[int] = None,
    progress_interval: int = 1_000_000,
) -> Iterable[pd.DataFrame]:
    logger.info("Reading CSV: %s", path)
    reader = pd.read_csv(
        path,
        sep=sep,
        header=0,
        encoding=encoding,
        dtype=str,
        nrows=nrows,
        engine="c",
        on_bad_lines="warn",
        chunksize=progress_interval
    )

    try:
        for chunk in reader:
            # chunk['raw_payload'] = chunk.to_json(orient='records', lines=True).splitlines()
            logger.info("Read chunk of %d rows...", len(chunk))
            yield clean_ais_dataframe(chunk)

    except Exception as e:
        logger.error("Error while reading CSV in chunks: %s", e)
        raise

    logger.info("Finished reading CSV chunks.")



def _process_copy_chunk(df_chunk: pd.DataFrame, table_name: str, columns: List[str]):
    """COPY one chunk into staging (for ProcessPoolExecutor)."""
    conn_local = None
    try:
        conn_local = get_db_connection(**_ETL_CONN_OVERRIDES)
        cur = conn_local.cursor()
        buf = io.StringIO()
        df_chunk[columns].to_csv(buf, index=False, header=False, sep="\t", na_rep="\\N", date_format="%Y-%m-%d %H:%M:%S")
        buf.seek(0)
        cur.copy_expert(f"COPY {table_name} ({','.join(columns)}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N');", buf)
        conn_local.commit()
        return len(df_chunk)
    except Exception as e:
        logger.error(f"Error in _process_copy_chunk (PID {os.getpid()}): {e}")
        if conn_local:
            conn_local.rollback()
        raise
    finally:
        if conn_local:
            conn_local.close()


def prepare_chunk_only(df: pd.DataFrame):
    """Clean + dedup vessels/positions; drop source DF early to free RAM."""
    process = psutil.Process()
    logger.info("Starting chunk prep (CPU): %d rows", len(df))
    
    df = df.replace({pd.NA: None, np.nan: None}).copy()
    
    vessels_cols_csv = list(CSV_TO_VESSELS.values())
    for col in vessels_cols_csv:
        if col not in df.columns:
            df[col] = None
    vessels_df = df[vessels_cols_csv].rename(columns={v: k for k, v in CSV_TO_VESSELS.items()})
    if AISColumnsCSV.TIMESTAMP in df.columns and AISColumnsCSV.MMSI in df.columns:
        first_seen = df.groupby(AISColumnsCSV.MMSI)[AISColumnsCSV.TIMESTAMP].min()
        last_seen = df.groupby(AISColumnsCSV.MMSI)[AISColumnsCSV.TIMESTAMP].max()
        vessels_df[VesselsColumns.FIRST_SEEN_AT] = df[AISColumnsCSV.MMSI].map(first_seen)
        vessels_df[VesselsColumns.LAST_SEEN_AT] = df[AISColumnsCSV.MMSI].map(last_seen)
    vessels_df = vessels_df.drop_duplicates(subset=[VesselsColumns.MMSI], keep='first')

    positions_cols_csv = list(CSV_TO_POSITIONS.values())
    for col in positions_cols_csv:
        if col not in df.columns:
            df[col] = None
    positions_df = df[positions_cols_csv].rename(columns={v: k for k, v in CSV_TO_POSITIONS.items()})
    
    del df # Release memory
    
    positions_df = positions_df.drop_duplicates(subset=[AISPositionsColumns.MMSI, AISPositionsColumns.TIMESTAMP], keep='first')
    lon, lat = positions_df[AISPositionsColumns.LONGITUDE], positions_df[AISPositionsColumns.LATITUDE]
    point_wkt = "POINT(" + lon.astype(str) + " " + lat.astype(str) + ")"

    positions_df[AISPositionsColumns.POSITION_GEOG] = point_wkt.where(lon.notna() & lat.notna())
    positions_df[AISPositionsColumns.CREATED_AT] = pd.Timestamp.now()
    
    logger.info("Chunk prep complete (CPU). Memory: %.2f MB", process.memory_info().rss / (1024*1024))
    return vessels_df, positions_df

def copy_prepared_data(conn, vessels_df, positions_df):
    """COPY prepared frames into staging (background-thread IO)."""
    start_time = time.perf_counter()
    
    def copy_dataframe(conn, df_full: pd.DataFrame, table_name: str, columns: List[str]):
        if df_full.empty: return 0
        total_rows = len(df_full)
        total_copied = 0
        for start_idx in range(0, total_rows, SUB_CHUNK_SIZE):
            end_idx = min(start_idx + SUB_CHUNK_SIZE, total_rows)
            df_batch = df_full.iloc[start_idx:end_idx]
            buf = io.StringIO()
            df_batch[columns].to_csv(buf, index=False, header=False, sep="\t", na_rep="\\N", date_format="%Y-%m-%d %H:%M:%S")
            buf.seek(0)
            with conn.cursor() as cur:
                cur.copy_expert(f"COPY {table_name} ({','.join(columns)}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N');", buf)
            total_copied += len(df_batch)
        conn.commit()
        return total_copied

    v_rows = copy_dataframe(conn, vessels_df, "stg_vessels", VesselsColumns().all())
    p_rows = copy_dataframe(conn, positions_df, "stg_positions", AISPositionsColumns().all())
    
    duration = time.perf_counter() - start_time
    logger.info("Background COPY complete: %d rows (%.2fs)", v_rows + p_rows, duration)
    return v_rows, p_rows, duration

def merge_staging(conn: psycopg2.extensions.connection):
    """Merge TEMP staging into vessels / ais_positions."""
    merge_start = time.perf_counter()
    with conn.cursor() as cur:
        vessel_cols = VesselsColumns().all()
        key_col = VesselsColumns.MMSI

        update_cols = [col for col in vessel_cols if col != key_col and col != VesselsColumns.FIRST_SEEN_AT]

        set_clause = ",\n".join(f"{col} = COALESCE(EXCLUDED.{col}, vessels.{col})" for col in update_cols)
        if VesselsColumns.LAST_SEEN_AT in update_cols:
            set_clause = set_clause.replace(
                f"{VesselsColumns.LAST_SEEN_AT} = COALESCE(EXCLUDED.{VesselsColumns.LAST_SEEN_AT}, vessels.{VesselsColumns.LAST_SEEN_AT})",
                f"{VesselsColumns.LAST_SEEN_AT} = EXCLUDED.{VesselsColumns.LAST_SEEN_AT}"
            )

        logger.debug("Merging stg_vessels...")
        cur.execute(f"""
            INSERT INTO vessels ({','.join(vessel_cols)})
            SELECT DISTINCT ON ({key_col}) {','.join(vessel_cols)} 
            FROM stg_vessels
            ORDER BY {key_col}, {VesselsColumns.LAST_SEEN_AT} DESC
            ON CONFLICT ({key_col}) DO UPDATE
            SET {set_clause}
        """)
        
        logger.debug("Merging stg_positions (Optimized Anti-Join)...")
        cur.execute("SELECT min(timestamp), max(timestamp) FROM stg_positions")
        ts_row = cur.fetchone()
        if ts_row is None:
            min_ts, max_ts = None, None
        else:
            min_ts, max_ts = ts_row

        if min_ts and max_ts:
            # Decompress overlapping Timescale chunks before insert
            try:
                cur.execute("""
                    SELECT decompress_chunk(c.show_chunks) 
                    FROM show_chunks('ais_positions', newer_than => %s, older_than => %s) AS c(show_chunks)
                    WHERE (
                        SELECT is_compressed 
                        FROM timescaledb_information.chunks 
                        WHERE chunk_schema || '.' || chunk_name = c.show_chunks::text
                    ) = true;
                """, (min_ts, max_ts))
                decompressed = cur.fetchall()
                if decompressed:
                    logger.info(f"Decompressed {len(decompressed)} chunks for time range {min_ts} to {max_ts}")
            except Exception as e:
                # Might fail if no chunks are compressed or if on an older TimescaleDB version
                logger.debug(f"Chunk decompression check skipped/failed: {e}")

            # Anti-join with explicit time bounds so Postgres prunes hypertable chunks
            cur.execute(f"""
                INSERT INTO ais_positions ({','.join(AISPositionsColumns().all())})
                SELECT DISTINCT ON (mmsi, timestamp) {','.join(f's.{col}' for col in AISPositionsColumns().all())} 
                FROM stg_positions s
                WHERE NOT EXISTS (
                    SELECT 1 FROM ais_positions p
                    WHERE p.mmsi = s.mmsi 
                      AND p.timestamp = s.timestamp
                      AND p.timestamp >= %s AND p.timestamp <= %s
                )
                ORDER BY mmsi, timestamp, s.created_at DESC
            """, (min_ts, max_ts))
        
        conn.commit()

        logger.debug("Truncating staging tables...")
        cur.execute("TRUNCATE TABLE stg_vessels;")
        cur.execute("TRUNCATE TABLE stg_positions;")
        conn.commit()
        logger.debug("Staging tables truncated.")

    merge_time = time.perf_counter() - merge_start
    logger.info("Merge phase done (%.2fs)", merge_time)
    return merge_time

def run_merge_in_background(conn, url, file_vessels_rows, file_positions_rows, total_copy_time, file_start, total_rows):
    """Executes the database merge in a background thread while main thread processes the next file."""
    try:
        logger.info(f"[BACKGROUND] Starting final merge for {url} ({total_rows} source rows)")
        merge_time = merge_staging(conn)

        total_time = time.perf_counter() - file_start
        logger.info("[BACKGROUND] File ETL Summary ------------------------------")
        logger.info("Total source rows: %d", total_rows) 
        logger.info("Total time: %.2fs", total_time)
        logger.info(" - Vessels rows copied: %d", file_vessels_rows)
        logger.info(" - Positions rows copied: %d", file_positions_rows)
        logger.info(" - Cumulative COPY phase: %.2fs", total_copy_time)
        logger.info(" - Bulk Merge phase: %.2fs", merge_time)
        logger.info("---------------------------------------------------------------")

        mark_file_processed(conn, url, total_rows)
        
        logger.info(f"=== [BACKGROUND] File Processing Complete: {url} ===")
    except Exception as e:
        logger.error(f"[BACKGROUND] ETL failed for {url} during merge phase: {e}", exc_info=True)
    finally:
        # Background thread owns this connection and must close it
        if conn:
            conn.close()
            logger.info(f"Database connection closed for {url} (Background Thread)")


def process_single_file(url: str, merge_executor):
    logger.info("=== Processing file: %s ===", url)
    conn = None 
    try:
        conn = get_db_connection(**_ETL_CONN_OVERRIDES)
        
        if is_file_processed(conn, url):
            logger.info("File already processed, skipping: %s", url)
            conn.close()
            return True
        
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout;")
            timeout_setting = cur.fetchone()[0]
            logger.info(f"DB Config verified: statement_timeout={timeout_setting}")

            cur.execute("SET synchronous_commit = off;")
            cur.execute("SET maintenance_work_mem = '2GB';")
            cur.execute("SET work_mem = '256MB';")
            
            # TEMP staging tables isolate parallel file workers
            cur.execute(f"""CREATE TEMP TABLE IF NOT EXISTS stg_vessels (
                {','.join([f"{col} {dtype}" for col, dtype in VesselsColumns().pg_dtype_map().items()])}
            );""")
            cur.execute(f"""CREATE TEMP TABLE IF NOT EXISTS stg_positions (
                {','.join([f"{col} {dtype}" for col, dtype in AISPositionsColumns().pg_dtype_map().items()])}
            );""")
        conn.commit()
        logger.info("Connected to PostgreSQL database (synch_commit=off, TEMP staging tables ensured)")

        total_rows = 0
        file_vessels_rows = 0
        file_positions_rows = 0
        total_copy_time = 0

        chunk_idx = 0
        gen = load_ais_csv(url)
        file_start = time.perf_counter()
        
        # max_workers=1: a single connection cannot run concurrent COPY
        from concurrent.futures import ThreadPoolExecutor
        
        from queue import Queue
        from threading import Thread
        
        data_queue: Queue[tuple[pd.DataFrame, pd.DataFrame] | None | Exception] = Queue(
            maxsize=PRODUCER_QUEUE_MAXSIZE
        )
        
        def producer_worker():
            try:
                gen = load_ais_csv(url)
                for raw_df in gen:
                    v_df, p_df = prepare_chunk_only(raw_df)
                    data_queue.put((v_df, p_df))
                data_queue.put(None) # Sentinel for end of file
            except Exception as e:
                logger.error(f"Producer error for {url}: {e}")
                data_queue.put(e)

        Thread(target=producer_worker, daemon=True).start()

        chunk_idx = 0
        file_start = time.perf_counter()
        
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=COPY_MAX_WORKERS) as copy_executor:
            last_copy_future = None
            
            while True:
                item = data_queue.get()
                
                if item is None: # End of file
                    break
                if isinstance(item, Exception):
                    raise item
                
                chunk_idx += 1
                v_df, p_df = item
                total_rows += (len(v_df) + len(p_df)) # Approximate rows from clean data
                
                if last_copy_future:
                    v_rows, p_rows, c_time = last_copy_future.result()
                    file_vessels_rows += v_rows
                    file_positions_rows += p_rows
                    total_copy_time += c_time
                
                logger.info(f"--- Submitting Chunk {chunk_idx} for COPY (Prefetched) ---")
                last_copy_future = copy_executor.submit(copy_prepared_data, conn, v_df, p_df)
                
                import gc
                gc.collect()

            if last_copy_future:
                v_rows, p_rows, c_time = last_copy_future.result()
                file_vessels_rows += v_rows
                file_positions_rows += p_rows
                total_copy_time += c_time

        total_source_rows = file_vessels_rows + file_positions_rows
        logger.info(f"Passing connection to background thread for MERGE of {url}")
        merge_executor.submit(run_merge_in_background, conn, url, file_vessels_rows, file_positions_rows, total_copy_time, file_start, total_source_rows)
        conn = None

        return True

    except Exception as e:
        logger.error("ETL failed for %s during CSV/COPY phase: %s", url, e, exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logger.info(f"Database connection closed for {url} (Error during COPY)")

def main():
    global _active_conn
    logger.info("Starting AIS ETL job...")

    cleanup_stale_connections()

    logger.info("Pipeline processing mode (Background thread for DB merges)")

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MERGE_MAX_WORKERS) as merge_executor:
        for url in CSV_FILES:
            success = process_single_file(url, merge_executor)
            if not success:
                logger.error(f"Processing failed for {url}. Stopping further execution.")
                break

    logger.info("All files processed successfully!")


if __name__ == "__main__":
    main()