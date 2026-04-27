-- Create roles
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_app') THEN
        CREATE ROLE sc_app LOGIN PASSWORD 'changeme_dev';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_dba') THEN
        CREATE ROLE sc_dba LOGIN PASSWORD 'changeme_dev' SUPERUSER;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sc_readonly') THEN
        CREATE ROLE sc_readonly;
    END IF;
END $$;

-- Grant database permissions
GRANT CONNECT ON DATABASE sportconnect TO sc_app;
GRANT CONNECT ON DATABASE sportconnect TO sc_readonly;
GRANT CONNECT ON DATABASE sportconnect TO sc_dba;

-- Grant schema permissions
GRANT USAGE ON SCHEMA public TO sc_app;
GRANT USAGE ON SCHEMA public TO sc_readonly;
GRANT USAGE ON SCHEMA public TO sc_dba;

-- Grant table permissions to sc_app
GRANT SELECT, INSERT, UPDATE ON users TO sc_app;
GRANT SELECT, INSERT, UPDATE ON user_profiles TO sc_app;
GRANT SELECT, INSERT, UPDATE ON follows TO sc_app;
GRANT SELECT, INSERT, UPDATE ON comments TO sc_app;
GRANT SELECT, INSERT, UPDATE ON likes TO sc_app;
GRANT SELECT, INSERT, UPDATE ON notifications TO sc_app;
GRANT INSERT ON audit_log TO sc_app;

-- Grant sequence permissions to sc_app
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sc_app;

-- Grant all to sc_readonly
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sc_readonly;

-- Grant all to sc_dba
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sc_dba;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sc_dba;

