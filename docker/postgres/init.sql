-- BWCorp Permission-aware RAG: Initial Schema
-- Auto-executed by postgres container on first startup.

-- ─────────────────────────────────────────────────────────────────
-- 1. Extensions
-- ─────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────────
-- 2. Documents table
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE documents (
    -- Core identifiers
    id              VARCHAR(20) PRIMARY KEY,                 -- e.g., 'DOC-001'
    title           TEXT NOT NULL,

    -- Classification
    category        VARCHAR(20) NOT NULL,                    -- hr, security, tech, ...
    sub_type        VARCHAR(50) NOT NULL,                    -- hr.policy, etc.
    sensitivity     VARCHAR(20) NOT NULL,                    -- public | internal | restricted | privileged
    language        VARCHAR(10) NOT NULL,                    -- ko | en | mixed

    -- Content
    body            TEXT NOT NULL,
    embedding       vector(1024),                            -- BGE-M3 dense vector

    -- Conditional permission attributes (NULL when not applicable)
    subject             VARCHAR(50),                          -- hr.personnel / finance.expense self-access
    project_id          VARCHAR(50),                          -- tech.project
    project_members     TEXT[],                               -- user_id list
    parties             TEXT[],                               -- legal.* case-based
    case_id             VARCHAR(50),                          -- legal.*
    stakeholders        TEXT[],                               -- security.incident named access
    severity            VARCHAR(10),                          -- security.incident
    executive_briefed   BOOLEAN,                              -- security.incident
    disclosure_level    VARCHAR(30),                          -- legal.litigation
    tags                TEXT[],                               -- cross-functional override hints

    -- Expected readers (test fixture verification)
    expected_readers    TEXT[] NOT NULL,

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────
-- 3. Vector index — HNSW for ANN search
-- ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_documents_embedding
    ON documents USING hnsw (embedding vector_cosine_ops);

-- ─────────────────────────────────────────────────────────────────
-- 4. GIN indexes — array-based ABAC filtering
-- ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_documents_project_members
    ON documents USING gin (project_members);

CREATE INDEX idx_documents_parties
    ON documents USING gin (parties);

CREATE INDEX idx_documents_stakeholders
    ON documents USING gin (stakeholders);

CREATE INDEX idx_documents_tags
    ON documents USING gin (tags);

CREATE INDEX idx_documents_expected_readers
    ON documents USING gin (expected_readers);

-- ─────────────────────────────────────────────────────────────────
-- 5. B-tree indexes — common filter columns
-- ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_documents_category    ON documents (category);
CREATE INDEX idx_documents_sub_type    ON documents (sub_type);
CREATE INDEX idx_documents_sensitivity ON documents (sensitivity);

-- Partial indexes (only rows where field is non-NULL)
CREATE INDEX idx_documents_subject
    ON documents (subject) WHERE subject IS NOT NULL;

CREATE INDEX idx_documents_project_id
    ON documents (project_id) WHERE project_id IS NOT NULL;

CREATE INDEX idx_documents_case_id
    ON documents (case_id) WHERE case_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────
-- 6. Audit log table (for Rule 5 in Stage 4)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE audit_log (
    id                      BIGSERIAL PRIMARY KEY,
    user_id                 VARCHAR(50) NOT NULL,
    user_role               VARCHAR(50) NOT NULL,
    query                   TEXT,
    retrieved_doc_ids       TEXT[],
    granted_doc_ids         TEXT[],
    denied_doc_ids          TEXT[],
    accessed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_engagement_id     VARCHAR(50),
    ip_address              INET,
    additional_metadata     JSONB
);

CREATE INDEX idx_audit_log_user_id      ON audit_log (user_id);
CREATE INDEX idx_audit_log_accessed_at  ON audit_log (accessed_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- 7. Update timestamp trigger
-- ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();