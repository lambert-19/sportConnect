-- =============================================================
-- SportConnect — Test Data für Entwicklung
-- =============================================================

-- Insert admin user
INSERT INTO users (id, email, email_hash, password_hash, role, is_active)
VALUES (
    'f47ac10b-58cc-4372-a567-0e02b2c3d479'::UUID,
    pgp_sym_encrypt('admin@sportconnect.app', 'dev-encryption-key-change-in-production-32chars'),
    encode(sha256('admin@sportconnect.app'::bytea), 'hex'),
    crypt('password123', gen_salt('bf', 12)),
    'admin',
    TRUE
)
ON CONFLICT DO NOTHING;

-- Insert admin profile
INSERT INTO user_profiles (user_id, username, display_name, bio, is_public)
VALUES (
    'f47ac10b-58cc-4372-a567-0e02b2c3d479'::UUID,
    'admin_sportconnect',
    'SportConnect Admin',
    'System Administrator',
    TRUE
)
ON CONFLICT DO NOTHING;

-- Insert test user 1
INSERT INTO users (email, email_hash, password_hash, role, is_active)
VALUES (
    pgp_sym_encrypt('user1@sportconnect.app', 'dev-encryption-key-change-in-production-32chars'),
    encode(sha256('user1@sportconnect.app'::bytea), 'hex'),
    crypt('password123', gen_salt('bf', 12)),
    'user',
    TRUE
)
ON CONFLICT (email_hash) DO NOTHING;

-- Insert test user 2
INSERT INTO users (email, email_hash, password_hash, role, is_active)
VALUES (
    pgp_sym_encrypt('user2@sportconnect.app', 'dev-encryption-key-change-in-production-32chars'),
    encode(sha256('user2@sportconnect.app'::bytea), 'hex'),
    crypt('password123', gen_salt('bf', 12)),
    'user',
    TRUE
)
ON CONFLICT (email_hash) DO NOTHING;

-- Insert profiles for test users
WITH user_ids AS (
    SELECT id FROM users WHERE email_hash = encode(sha256('user1@sportconnect.app'::bytea), 'hex')
)
INSERT INTO user_profiles (user_id, username, display_name, bio, is_public)
SELECT id, 'runner_john', 'John Runner', 'Passionate about running', TRUE
FROM user_ids
ON CONFLICT DO NOTHING;

WITH user_ids AS (
    SELECT id FROM users WHERE email_hash = encode(sha256('user2@sportconnect.app'::bytea), 'hex')
)
INSERT INTO user_profiles (user_id, username, display_name, bio, is_public)
SELECT id, 'cyclist_sarah', 'Sarah Cyclist', 'Cycling enthusiast', TRUE
FROM user_ids
ON CONFLICT DO NOTHING;

SELECT 'Test data inserted successfully' as status;
SELECT COUNT(*) as user_count FROM users;
SELECT COUNT(*) as profile_count FROM user_profiles;

