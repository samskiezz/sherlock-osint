CREATE SCHEMA IF NOT EXISTS erps;
CREATE TABLE erps.policies (
 token_hash TEXT PRIMARY KEY, workspace UUID NOT NULL, actor TEXT NOT NULL,
 purpose TEXT NOT NULL DEFAULT 'investigation', enabled BOOLEAN NOT NULL DEFAULT true,
 can_write BOOLEAN NOT NULL DEFAULT false, can_delete BOOLEAN NOT NULL DEFAULT false,
 properties TEXT[], visible_sources UUID[], kinds TEXT[]
);
CREATE TABLE erps.mentions (
 workspace UUID NOT NULL, id UUID NOT NULL, payload JSONB NOT NULL,
 sources UUID[] NOT NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace,id)
);
CREATE INDEX mentions_sources ON erps.mentions USING GIN(sources);
CREATE TABLE erps.constraints (
 workspace UUID NOT NULL, a UUID NOT NULL, b UUID NOT NULL, must_link BOOLEAN NOT NULL,
 PRIMARY KEY(workspace,a,b), CHECK(a<b)
);
CREATE TABLE erps.deleted_sources (
 workspace UUID NOT NULL, source UUID NOT NULL, deleted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace,source)
);
CREATE TABLE erps.entities (
 workspace UUID NOT NULL, id UUID NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
 payload JSONB NOT NULL, sources UUID[] NOT NULL,
 PRIMARY KEY(workspace,id)
);
CREATE INDEX entities_name ON erps.entities(workspace,name,id);
CREATE INDEX entities_sources ON erps.entities USING GIN(sources);
CREATE TABLE erps.entity_versions (
 workspace UUID NOT NULL, id UUID NOT NULL, payload JSONB NOT NULL,
 recorded_from TIMESTAMPTZ NOT NULL, recorded_to TIMESTAMPTZ,
 PRIMARY KEY(workspace,id,recorded_from)
);
CREATE INDEX entity_versions_asof ON erps.entity_versions(workspace,id,recorded_from,recorded_to);
CREATE TABLE erps.entity_mentions (
 workspace UUID NOT NULL, mention UUID NOT NULL, entity UUID NOT NULL,
 PRIMARY KEY(workspace,mention),
 FOREIGN KEY(workspace,mention) REFERENCES erps.mentions(workspace,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace,entity) REFERENCES erps.entities(workspace,id) ON DELETE CASCADE
);
CREATE TABLE erps.pair_decisions (
 workspace UUID NOT NULL, a UUID NOT NULL, b UUID NOT NULL, entity_a UUID NOT NULL,
 entity_b UUID NOT NULL, score DOUBLE PRECISION NOT NULL, decision TEXT NOT NULL,
 provenance JSONB NOT NULL, PRIMARY KEY(workspace,a,b)
);
CREATE TABLE erps.audit (
 workspace UUID NOT NULL, sequence BIGINT NOT NULL, previous_hash TEXT NOT NULL,
 hash TEXT NOT NULL, event JSONB NOT NULL,
 PRIMARY KEY(workspace,sequence)
);
CREATE FUNCTION erps.prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'ERPS audit is append-only'; END $$;
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON erps.audit
 FOR EACH ROW EXECUTE FUNCTION erps.prevent_audit_mutation();
