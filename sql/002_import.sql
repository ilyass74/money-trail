CREATE TABLE IF NOT EXISTS meta.import_batches (
    batch_id UUID PRIMARY KEY,
    fingerprint CHAR(64) NOT NULL UNIQUE,
    dataset_label TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    company_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    control_on DATE NOT NULL,
    manifest JSONB NOT NULL,
    manifest_bytes BYTEA NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meta.import_attempts (
    attempt_id UUID PRIMARY KEY,
    dataset_label TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('started','success','skipped_duplicate','failed')),
    batch_id UUID REFERENCES meta.import_batches(batch_id),
    inserted_records INTEGER NOT NULL DEFAULT 0 CHECK (inserted_records >= 0),
    error_code TEXT
);
CREATE TABLE IF NOT EXISTS meta.import_files (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES meta.import_batches(batch_id),
    entity TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    source_bytes BYTEA NOT NULL,
    UNIQUE (batch_id, entity)
);
CREATE TABLE IF NOT EXISTS raw.source_records (
    record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id BIGINT NOT NULL REFERENCES meta.import_files(file_id),
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    company_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    UNIQUE (file_id, row_number),
    UNIQUE (file_id, company_id, source_system, source_id)
);
CREATE INDEX IF NOT EXISTS source_records_source_key
    ON raw.source_records (company_id, source_system, source_id);
