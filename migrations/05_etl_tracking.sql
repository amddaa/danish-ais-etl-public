-- Track processed ETL files to prevent duplicate loading
CREATE TABLE IF NOT EXISTS etl_processed_files (
    file_path TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    rows_processed BIGINT
);

COMMENT ON TABLE etl_processed_files IS 'Tracks which CSV files have been processed by ETL to prevent duplicates';
