-- PostgreSQL Health Check for SportConnect

SELECT '===============================================' as check;
SELECT '  PostgreSQL Health Check — SportConnect' as status;
SELECT '===============================================' as check;

-- Version
SELECT 'PostgreSQL Version:' as category;
SELECT version() as info;

-- Database Statistics
SELECT '' as blank;
SELECT 'Database Objects:' as category;

SELECT 'Tables' as object_type, COUNT(*) as count
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
UNION ALL
SELECT 'Indexes', COUNT(*)
FROM pg_indexes
WHERE schemaname = 'public'
UNION ALL
SELECT 'Sequences', COUNT(*)
FROM information_schema.sequences
WHERE sequence_schema = 'public'
UNION ALL
SELECT 'Functions', COUNT(*)
FROM information_schema.routines
WHERE routine_schema = 'public';

-- Data Statistics
SELECT '' as blank;
SELECT 'Data Statistics:' as category;

SELECT 'Users' as table_name, COUNT(*) as row_count FROM users
UNION ALL
SELECT 'User Profiles', COUNT(*) FROM user_profiles
UNION ALL
SELECT 'Follows', COUNT(*) FROM follows
UNION ALL
SELECT 'Likes', COUNT(*) FROM likes
UNION ALL
SELECT 'Notifications', COUNT(*) FROM notifications
UNION ALL
SELECT 'Audit Logs', COUNT(*) FROM audit_log;

-- Roles
SELECT '' as blank;
SELECT 'Database Roles:' as category;

SELECT rolname as role_name,
       CASE WHEN rolsuper THEN 'Superuser'
            WHEN rolcanlogin THEN 'Login Role'
            ELSE 'Group Role'
       END as role_type
FROM pg_roles
WHERE rolname LIKE 'sc_%' OR rolname = 'postgres'
ORDER BY rolname;

-- Extensions
SELECT '' as blank;
SELECT 'Loaded Extensions:' as category;

SELECT extname as extension_name, extversion as version
FROM pg_extension
WHERE extname IN ('uuid-ossp', 'pgcrypto', 'pg_stat_statements')
ORDER BY extname;

-- Completion
SELECT '' as blank;
SELECT '✅ PostgreSQL Initialization Complete!' as status;
SELECT '===============================================' as check;

