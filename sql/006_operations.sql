CREATE TABLE app.rule_comparisons (
 comparison_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 old_publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id),
 new_publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id),
 batch_id UUID NOT NULL,
 object_kind TEXT NOT NULL,
 object_id TEXT NOT NULL,
 comparison JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(old_publication_id,new_publication_id,batch_id,object_kind,object_id)
);
CREATE TRIGGER immutable_rule_comparison BEFORE UPDATE OR DELETE ON app.rule_comparisons
 FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TABLE app.case_successions (
 previous_case_id UUID NOT NULL REFERENCES app.investigation_cases(case_id),
 successor_case_id UUID NOT NULL UNIQUE REFERENCES app.investigation_cases(case_id),
 publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id),
 reason TEXT NOT NULL CHECK(reason IN ('source_changed','rule_changed','source_and_rule_changed')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(previous_case_id,successor_case_id),
 CHECK(previous_case_id<>successor_case_id)
);
CREATE INDEX cases_scope_latest ON app.investigation_cases(company_id,currency,object_kind,object_id,created_at DESC);
CREATE INDEX dossiers_status ON app.published_dossiers(publication_id,batch_id,((dossier->'result'->>'status')),object_kind,object_id);
CREATE TABLE meta.source_extractions (
 extraction_id UUID PRIMARY KEY,
 source TEXT NOT NULL,
 company_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('started','success','failed')),
 started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 finished_at TIMESTAMPTZ,
 source_as_of TIMESTAMPTZ,
 row_count BIGINT,
 error_code TEXT,
 payload JSONB,
 payload_sha256 CHAR(64),
 CHECK(status='started' OR finished_at IS NOT NULL)
);
CREATE TABLE meta.quarantined_rows (
 extraction_id UUID NOT NULL REFERENCES meta.source_extractions(extraction_id),
 entity TEXT NOT NULL,
 row_number BIGINT NOT NULL,
 payload JSONB NOT NULL,
 reason TEXT NOT NULL,
 PRIMARY KEY(extraction_id,entity,row_number)
);
CREATE TABLE meta.rule_policies (
 version TEXT PRIMARY KEY,
 policy JSONB NOT NULL,
 registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO meta.rule_policies(version,policy) VALUES('v1','{"version":"v1","invoice_tolerance":"0.00","settlement_tolerance":"0.00"}');
CREATE TRIGGER immutable_rule_policy BEFORE UPDATE OR DELETE ON meta.rule_policies
 FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TABLE app.published_status_counts (
 publication_id UUID NOT NULL,
 batch_id UUID NOT NULL,
 object_kind TEXT NOT NULL,
 status TEXT NOT NULL,
 dossier_count BIGINT NOT NULL CHECK(dossier_count>0),
 PRIMARY KEY(publication_id,batch_id,object_kind,status),
 FOREIGN KEY(publication_id,batch_id) REFERENCES app.published_snapshots(publication_id,batch_id)
);
INSERT INTO app.published_status_counts(publication_id,batch_id,object_kind,status,dossier_count)
 SELECT publication_id,batch_id,object_kind,dossier->'result'->>'status',count(*) FROM app.published_dossiers GROUP BY 1,2,3,4;
CREATE TRIGGER immutable_published_counts BEFORE UPDATE OR DELETE ON app.published_status_counts
 FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
