CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS sqlpilot_kb AUTHORIZATION sqlpilot_owner;

CREATE TABLE IF NOT EXISTS sqlpilot_kb.schema_versions (
    source_id uuid NOT NULL,
    version varchar(64) NOT NULL,
    fingerprint varchar(64) NOT NULL,
    embedding_model varchar(128) NOT NULL,
    embedding_dimensions integer NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'building',
    table_count integer NOT NULL DEFAULT 0,
    column_count integer NOT NULL DEFAULT 0,
    document_count integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz,
    PRIMARY KEY (source_id, version)
);

CREATE TABLE IF NOT EXISTS sqlpilot_kb.schema_documents (
    id uuid PRIMARY KEY,
    tenant_id varchar(64) NOT NULL,
    source_id uuid NOT NULL,
    schema_version varchar(64) NOT NULL,
    object_type varchar(32) NOT NULL,
    object_key varchar(512) NOT NULL,
    schema_name varchar(128) NOT NULL,
    table_name varchar(255) NOT NULL,
    column_name varchar(255),
    business_name varchar(255),
    content text NOT NULL,
    aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1024) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    certification_status varchar(32) NOT NULL DEFAULT 'ai_inferred',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, schema_version, object_key)
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_scope
    ON sqlpilot_kb.schema_documents(tenant_id, source_id, schema_version, enabled);
CREATE INDEX IF NOT EXISTS idx_kb_documents_table
    ON sqlpilot_kb.schema_documents(source_id, schema_version, table_name);
CREATE INDEX IF NOT EXISTS idx_kb_documents_content_trgm
    ON sqlpilot_kb.schema_documents USING gin(content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_kb_documents_embedding_hnsw
    ON sqlpilot_kb.schema_documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

REVOKE ALL ON SCHEMA sqlpilot_kb FROM PUBLIC;
GRANT USAGE ON SCHEMA sqlpilot_kb TO sqlpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sqlpilot_kb TO sqlpilot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sqlpilot_owner IN SCHEMA sqlpilot_kb
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sqlpilot_app;
