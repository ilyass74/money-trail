ALTER TABLE app.investigation_cases ADD COLUMN assigned_to UUID REFERENCES app.local_users(user_id);
ALTER TABLE app.investigation_cases DROP CONSTRAINT investigation_cases_workflow_status_check;
ALTER TABLE app.investigation_cases ADD CHECK(workflow_status IN ('open','in_review','awaiting_validation','approved','rejected','closed','resolved','accepted_with_justification'));
CREATE TABLE app.external_action_evidence (
 action_id UUID PRIMARY KEY,
 case_id UUID NOT NULL REFERENCES app.investigation_cases(case_id),
 proposal_id UUID NOT NULL REFERENCES app.correction_proposals(proposal_id),
 external_reference TEXT NOT NULL,
 filename TEXT NOT NULL,
 evidence_bytes BYTEA NOT NULL,
 evidence_sha256 CHAR(64) NOT NULL,
 recorded_by TEXT NOT NULL,
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_external_action BEFORE UPDATE OR DELETE ON app.external_action_evidence
 FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TABLE app.case_resolutions (
 case_id UUID PRIMARY KEY REFERENCES app.investigation_cases(case_id),
 action_id UUID NOT NULL REFERENCES app.external_action_evidence(action_id),
 publication_id UUID NOT NULL REFERENCES app.result_publications(publication_id),
 result JSONB NOT NULL,
 confirmed_by TEXT NOT NULL,
 confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_resolution BEFORE UPDATE OR DELETE ON app.case_resolutions
 FOR EACH ROW EXECUTE FUNCTION app.reject_published_mutation();
CREATE TABLE app.external_identities (
 issuer TEXT NOT NULL,
 subject TEXT NOT NULL,
 user_id UUID NOT NULL REFERENCES app.local_users(user_id),
 PRIMARY KEY(issuer,subject)
);
