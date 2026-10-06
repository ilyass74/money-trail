-- Les calculs candidats ne deviennent visibles qu'avec leurs preuves complètes.
CREATE TABLE meta.publication_runs (
    run_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('building','published','failed')),
    actor TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    schema_prefix TEXT NOT NULL UNIQUE CHECK (schema_prefix ~ '^mtpub_[0-9a-f]{32}_$'),
    input_batch_ids JSONB NOT NULL,
    code_sha256 CHAR(64) NOT NULL,
    failure_phase TEXT,
    error_code TEXT,
    failed_checks JSONB NOT NULL DEFAULT '[]',
    run_results_bytes BYTEA,
    run_results_sha256 CHAR(64),
    manifest_bytes BYTEA,
    manifest_sha256 CHAR(64),
    cleanup_status TEXT NOT NULL DEFAULT 'pending' CHECK (cleanup_status IN ('pending','complete','failed')),
    CHECK ((status = 'building' AND finished_at IS NULL) OR
           (status <> 'building' AND finished_at IS NOT NULL))
);

CREATE TABLE app.result_publications (
    publication_id UUID PRIMARY KEY REFERENCES meta.publication_runs(run_id),
    version BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    code_sha256 CHAR(64) NOT NULL,
    build_evidence JSONB NOT NULL,
    snapshot_count INTEGER NOT NULL CHECK (snapshot_count > 0),
    dossier_count INTEGER NOT NULL CHECK (dossier_count > 0)
);

CREATE TABLE app.published_snapshots (
    publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id),
    batch_id UUID NOT NULL REFERENCES meta.import_batches(batch_id),
    company_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    control_on DATE NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    dossier_count INTEGER NOT NULL CHECK (dossier_count > 0),
    PRIMARY KEY (publication_id,batch_id)
);

CREATE TABLE app.published_dossiers (
    publication_id UUID NOT NULL,
    batch_id UUID NOT NULL,
    object_kind TEXT NOT NULL CHECK (object_kind IN ('invoice','settlement')),
    object_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    dossier JSONB NOT NULL,
    dossier_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY (publication_id,batch_id,object_kind,object_id,rule_version),
    FOREIGN KEY (publication_id,batch_id) REFERENCES app.published_snapshots(publication_id,batch_id)
);

CREATE TABLE app.publication_head (
    singleton SMALLINT PRIMARY KEY CHECK (singleton = 1),
    publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id)
);

-- Garde contre les modifications accidentelles, pas contre le superutilisateur local.
CREATE FUNCTION app.reject_published_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Une publication validee est conservee sans modification';
END;
$$;
CREATE TRIGGER immutable_publication BEFORE UPDATE OR DELETE ON app.result_publications
    FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TRIGGER immutable_published_snapshot BEFORE UPDATE OR DELETE ON app.published_snapshots
    FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TRIGGER immutable_published_dossier BEFORE UPDATE OR DELETE ON app.published_dossiers
    FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
