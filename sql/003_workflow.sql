CREATE TABLE app.investigation_cases (
    case_id UUID PRIMARY KEY,
    import_batch_id UUID NOT NULL REFERENCES meta.import_batches(batch_id),
    company_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    object_kind TEXT NOT NULL CHECK (object_kind IN ('invoice','settlement')),
    object_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    business_status TEXT NOT NULL,
    workflow_status TEXT NOT NULL DEFAULT 'open'
      CHECK (workflow_status IN ('open','in_review','awaiting_validation','approved','rejected','closed')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    evidence JSONB NOT NULL,
    created_by TEXT NOT NULL CHECK (length(trim(created_by))>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (import_batch_id,company_id,currency,object_kind,object_id,rule_version)
);
CREATE TABLE app.correction_proposals (
    proposal_id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES app.investigation_cases(case_id),
    proposal_number INTEGER NOT NULL CHECK (proposal_number>0),
    proposal_type TEXT NOT NULL CHECK (proposal_type IN ('source_data_review','allocation_review','accounting_review')),
    description TEXT NOT NULL CHECK (length(trim(description))>0),
    justification TEXT NOT NULL CHECK (length(trim(justification))>0),
    evidence_record_ids JSONB NOT NULL,
    proposed_by TEXT NOT NULL CHECK (length(trim(proposed_by))>0),
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decision TEXT CHECK (decision IN ('approved','rejected')),
    decided_by TEXT,
    decision_note TEXT,
    decided_at TIMESTAMPTZ,
    CHECK ((decision IS NULL AND decided_by IS NULL AND decision_note IS NULL AND decided_at IS NULL)
      OR (decision IS NOT NULL AND decided_by IS NOT NULL AND decision_note IS NOT NULL AND decided_at IS NOT NULL
          AND lower(trim(decided_by))<>lower(trim(proposed_by)) AND length(trim(decision_note))>0)),
    UNIQUE (case_id,proposal_number)
);
CREATE UNIQUE INDEX one_pending_proposal_per_case ON app.correction_proposals (case_id) WHERE decision IS NULL;
CREATE TABLE app.case_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES app.investigation_cases(case_id),
    revision INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    details JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (case_id,revision)
);
