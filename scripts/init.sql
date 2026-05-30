-- ============================================================
-- ARCA — Schema inicial PostgreSQL / Supabase
-- Ejecutar en orden. Compatible con Supabase SQL Editor.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- TENANTS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    plan        VARCHAR(50)  NOT NULL DEFAULT 'starter',
    country_code CHAR(2),
    currency    CHAR(3)      DEFAULT 'USD',
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- ------------------------------------------------------------
-- SUBJECTS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subjects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID REFERENCES tenants(id) ON DELETE SET NULL,
    name         VARCHAR(500) NOT NULL,
    industry     VARCHAR(100) NOT NULL,
    stage        VARCHAR(50),
    country_code CHAR(2),
    currency     CHAR(3)     DEFAULT 'USD',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subjects_tenant ON subjects(tenant_id);

-- ------------------------------------------------------------
-- SUBMISSIONS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS submissions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id              UUID NOT NULL REFERENCES subjects(id),
    submitted_by            UUID,
    data                    JSONB NOT NULL,
    data_version            INTEGER DEFAULT 1,
    status                  VARCHAR(50) DEFAULT 'pending',
    anti_manipulation_score NUMERIC(6,2),
    anti_manipulation_flags JSONB,
    submitted_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submissions_subject ON submissions(subject_id);

-- ------------------------------------------------------------
-- SIMULATIONS (inmutables una vez creadas)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS simulations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id       UUID NOT NULL REFERENCES subjects(id),
    submission_id    UUID NOT NULL REFERENCES submissions(id),
    engine_version   VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    n_simulations    INTEGER     DEFAULT 10000,
    seed             INTEGER,
    p_survival       NUMERIC(6,4),
    ife_score        NUMERIC(6,2),
    global_score     NUMERIC(6,2),
    cert_level       VARCHAR(20),
    score_by_dimension JSONB,
    vulnerability_map  JSONB,
    stress_results     JSONB,
    score_distribution JSONB,
    percentiles        JSONB,
    anti_manipulation  JSONB,
    cert_hash        VARCHAR(64),
    duration_ms      INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_simulations_subject   ON simulations(subject_id);
CREATE INDEX IF NOT EXISTS idx_simulations_cert_level ON simulations(cert_level);

-- ------------------------------------------------------------
-- CERTIFICATIONS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS certifications (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id    UUID NOT NULL REFERENCES simulations(id),
    subject_id       UUID NOT NULL REFERENCES subjects(id),
    level            VARCHAR(20) NOT NULL,
    score            NUMERIC(6,2) NOT NULL,
    p_survival       NUMERIC(6,4) NOT NULL,
    valid_from       DATE NOT NULL,
    valid_until      DATE,
    certificate_hash VARCHAR(64),
    public_url       VARCHAR(500),
    issued_at        TIMESTAMPTZ DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ,
    revoke_reason    TEXT
);

CREATE INDEX IF NOT EXISTS idx_certs_subject ON certifications(subject_id);
CREATE INDEX IF NOT EXISTS idx_certs_hash    ON certifications(certificate_hash);

-- ------------------------------------------------------------
-- BENCHMARKS SECTORIALES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS industry_benchmarks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    industry      VARCHAR(100) NOT NULL,
    stage         VARCHAR(50),
    country_code  CHAR(2),
    variable_name VARCHAR(100) NOT NULL,
    percentile_5  NUMERIC,
    percentile_25 NUMERIC,
    median        NUMERIC,
    percentile_75 NUMERIC,
    percentile_95 NUMERIC,
    mean          NUMERIC,
    std_dev       NUMERIC,
    sample_size   INTEGER,
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(industry, stage, country_code, variable_name)
);

-- ------------------------------------------------------------
-- AUDIT LOG (append-only — no UPDATE, no DELETE)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   UUID,
    user_id     UUID,
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id   UUID,
    old_value   JSONB,
    new_value   JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger que previene UPDATE y DELETE en audit_log
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only — UPDATE and DELETE are not allowed';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log;
CREATE TRIGGER audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY (activar en Supabase)
-- ------------------------------------------------------------
ALTER TABLE subjects     ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE certifications ENABLE ROW LEVEL SECURITY;

-- Política básica: cada tenant ve solo sus subjects
-- En Supabase, auth.uid() viene del JWT del usuario autenticado
-- Ajustar según estructura de auth elegida

-- Certifications son públicas (para verificación)
CREATE POLICY "certifications_public_read"
    ON certifications FOR SELECT
    USING (true);

-- subjects solo visibles para su tenant
-- (descomentar cuando tengas auth configurada en Supabase)
-- CREATE POLICY "subjects_tenant_isolation"
--     ON subjects FOR ALL
--     USING (tenant_id = auth.uid());

-- ------------------------------------------------------------
-- DATOS INICIALES: tenant de desarrollo
-- ------------------------------------------------------------
INSERT INTO tenants (id, name, plan, country_code)
VALUES ('00000000-0000-0000-0000-000000000001', 'ARCA Dev', 'enterprise', 'CO')
ON CONFLICT DO NOTHING;
