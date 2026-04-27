-- =============================================================
-- SportConnect — PostgreSQL 16 : DDL Complet (sans PostGIS)
-- Pour environnement de développement local
-- =============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
-- PostGIS optional: CREATE EXTENSION IF NOT EXISTS "postgis";

-- =============================================================
-- Rôles (principe du moindre privilège)
-- =============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_readonly') THEN
        CREATE ROLE sc_readonly;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_app') THEN
        CREATE ROLE sc_app LOGIN PASSWORD 'changeme_dev';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_dba') THEN
        CREATE ROLE sc_dba LOGIN PASSWORD 'changeme_dev';
    END IF;
END $$;

-- =============================================================
-- TABLE : users
-- Données d'authentification (email chiffré AES-256)
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        NOT NULL,                    -- Chiffré via pgp_sym_encrypt
    email_hash      TEXT        NOT NULL UNIQUE,             -- SHA-256 pour recherche
    password_hash   TEXT        NOT NULL,                    -- bcrypt cost=12
    role            VARCHAR(20) NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'premium', 'coach', 'admin')),
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ NULL,                        -- Soft delete RGPD
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email_hash ON users(email_hash);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_deleted ON users(deleted_at) WHERE deleted_at IS NOT NULL;

-- Row-Level Security : chaque utilisateur ne lit que ses propres données
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_isolation ON users
    USING (id = current_setting('app.current_user_id', true)::UUID
           OR current_setting('app.role', true) IN ('admin', 'dba'));

-- =============================================================
-- TABLE : user_profiles
-- Profils publics (1:1 avec users)
-- =============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         UUID            PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    username        VARCHAR(50)     NOT NULL UNIQUE,
    display_name    VARCHAR(100),
    bio             TEXT            CHECK (length(bio) <= 500),
    city            VARCHAR(100),
    country         CHAR(2),
    latitude        DECIMAL(9, 6),                           -- Instead of GEOGRAPHY
    longitude       DECIMAL(9, 6),                           -- Instead of GEOGRAPHY
    followers_count INT             NOT NULL DEFAULT 0,
    following_count INT             NOT NULL DEFAULT 0,
    activities_count INT            NOT NULL DEFAULT 0,
    is_public       BOOLEAN         NOT NULL DEFAULT TRUE,
    avatar_url      TEXT,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_username_lower
    ON user_profiles(lower(username));                       -- Recherche insensible casse
CREATE INDEX IF NOT EXISTS idx_profiles_geolocation
    ON user_profiles(latitude, longitude);                   -- Index spatial simple
CREATE INDEX IF NOT EXISTS idx_profiles_public
    ON user_profiles(is_public) WHERE is_public = TRUE;

-- Trigger : mise à jour automatique de updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================
-- TABLE : follows
-- Relations de suivi (N:N entre users)
-- =============================================================
CREATE TABLE IF NOT EXISTS follows (
    follower_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    following_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (follower_id, following_id),
    CHECK (follower_id <> following_id)                      -- Interdit auto-follow
);

CREATE INDEX IF NOT EXISTS idx_follows_following ON follows(following_id);
CREATE INDEX IF NOT EXISTS idx_follows_follower  ON follows(follower_id);

-- Trigger : mise à jour dénormalisée des compteurs followers/following
CREATE OR REPLACE FUNCTION update_follow_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE user_profiles SET followers_count = followers_count + 1
            WHERE user_id = NEW.following_id;
        UPDATE user_profiles SET following_count = following_count + 1
            WHERE user_id = NEW.follower_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE user_profiles SET followers_count = GREATEST(0, followers_count - 1)
            WHERE user_id = OLD.following_id;
        UPDATE user_profiles SET following_count = GREATEST(0, following_count - 1)
            WHERE user_id = OLD.follower_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_follows_counts
    AFTER INSERT OR DELETE ON follows
    FOR EACH ROW EXECUTE FUNCTION update_follow_counts();

-- =============================================================
-- TABLE : comments (partitionnée par trimestre)
-- Référence croisée vers MongoDB via activity_id (ObjectId)
-- =============================================================
CREATE TABLE IF NOT EXISTS comments (
    id              BIGSERIAL   NOT NULL,
    activity_id     VARCHAR(24) NOT NULL,                    -- ObjectId MongoDB
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    content         TEXT        NOT NULL CHECK (length(content) BETWEEN 1 AND 1000),
    parent_id       BIGINT      REFERENCES comments(id) ON DELETE CASCADE,
    is_deleted      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Partitions trimestrielles (2025-2027)
CREATE TABLE IF NOT EXISTS comments_2025_q1
    PARTITION OF comments FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS comments_2025_q2
    PARTITION OF comments FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS comments_2025_q3
    PARTITION OF comments FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS comments_2025_q4
    PARTITION OF comments FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS comments_2026_q1
    PARTITION OF comments FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS comments_2026_q2
    PARTITION OF comments FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS comments_2026_q3
    PARTITION OF comments FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS comments_2026_q4
    PARTITION OF comments FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

CREATE INDEX IF NOT EXISTS idx_comments_activity
    ON comments(activity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_user
    ON comments(user_id) WHERE is_deleted = FALSE;

-- =============================================================
-- TABLE : likes
-- Un seul like par user par activité
-- =============================================================
CREATE TABLE IF NOT EXISTS likes (
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_id     VARCHAR(24) NOT NULL,                    -- ObjectId MongoDB
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, activity_id)
);

CREATE INDEX IF NOT EXISTS idx_likes_activity ON likes(activity_id);

-- =============================================================
-- TABLE : notifications
-- =============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id              BIGSERIAL   PRIMARY KEY,
    recipient_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender_id       UUID        REFERENCES users(id) ON DELETE SET NULL,
    type            VARCHAR(30) NOT NULL
                    CHECK (type IN ('like', 'comment', 'follow', 'mention', 'achievement')),
    entity_type     VARCHAR(20) NOT NULL,
    entity_id       VARCHAR(50) NOT NULL,
    is_read         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifs_recipient
    ON notifications(recipient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifs_unread
    ON notifications(recipient_id) WHERE is_read = FALSE;  -- Index partiel

-- =============================================================
-- TABLE : audit_log (partitionnée par trimestre — RGPD)
-- =============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL   NOT NULL,
    user_id         UUID,
    operator_id     UUID,
    action          VARCHAR(50) NOT NULL
                    CHECK (action IN ('login', 'data_export', 'gdpr_delete', 'schema_change', 'password_change')),
    ip_address      INET,
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS audit_log_2025_q1
    PARTITION OF audit_log FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS audit_log_2025_q2
    PARTITION OF audit_log FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS audit_log_2025_q3
    PARTITION OF audit_log FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS audit_log_2025_q4
    PARTITION OF audit_log FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS audit_log_2026_q1
    PARTITION OF audit_log FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS audit_log_2026_q2
    PARTITION OF audit_log FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS audit_log_2026_q3
    PARTITION OF audit_log FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS audit_log_2026_q4
    PARTITION OF audit_log FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

CREATE INDEX IF NOT EXISTS idx_audit_user
    ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action
    ON audit_log(action, created_at DESC);

-- =============================================================
-- Permissions finales
-- =============================================================
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sc_readonly;
GRANT SELECT, INSERT, UPDATE ON users, user_profiles, follows,
      comments, likes, notifications TO sc_app;
GRANT INSERT ON audit_log TO sc_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sc_dba;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sc_dba;

-- =============================================================
-- Données de test (développement uniquement)
-- =============================================================
DO $$
BEGIN
    IF current_setting('app.environment', true) = 'development' THEN
        INSERT INTO users (email, email_hash, password_hash, role)
        VALUES (
            pgp_sym_encrypt('admin@sportconnect.app', 'dev-key'),
            encode(sha256('admin@sportconnect.app'::bytea), 'hex'),
            crypt('password123', gen_salt('bf', 12)),
            'admin'
        ) ON CONFLICT DO NOTHING;
    END IF;
END $$;

