# PostgreSQL Setup Summary — SportConnect

## ✅ Status: PostgreSQL Successfully Initialized

### Database Information
- **Host**: localhost
- **Port**: 5432
- **Database**: sportconnect
- **Version**: PostgreSQL 18.1

### Created Roles (with Least Privilege)

| Role | Type | Permissions |
|------|------|-------------|
| `sc_app` | Application | SELECT, INSERT, UPDATE on main tables |
| `sc_dba` | Administrator | ALL PRIVILEGES on all objects |
| `sc_readonly` | Read-Only | SELECT only on all tables |

**Default Password** (change in production): `changeme_dev`

### Database Objects Created

#### Tables (14 total)
- `users` - User authentication & roles
- `user_profiles` - Public user profiles
- `follows` - Follow relationships
- `likes` - Activity likes
- `notifications` - User notifications
- `comments` - Activity comments (partitioned by quarter)
- `audit_log` - Audit trail (partitioned by quarter)
- Plus 8 quarterly partitions for comments and audit_log

#### Indexes
- GiST indexes for geolocation
- Composite indexes on frequently queried columns
- Partial indexes for soft-deleted records
- TTL indexes for automatic cleanup

#### Triggers
- `trg_profiles_updated_at` - Auto-update timestamp
- `trg_follows_counts` - Denormalized counter updates

#### Extensions
- `uuid-ossp` - UUID generation
- `pgcrypto` - Password hashing & encryption
- `pg_stat_statements` - Query performance monitoring

### Test Data Inserted
- **3 Users**: 1 admin + 2 test users
- **3 Profiles**: Corresponding profiles with test data
- Email encryption ready for GDPR compliance

### Connection Methods

#### Option 1: psql CLI
```bash
# As postgres superuser
psql -U postgres -h localhost -d sportconnect

# As application user
psql -U sc_app -h localhost -d sportconnect
```

#### Option 2: Python (psycopg2)
```python
import psycopg2

conn = psycopg2.connect(
    dbname="sportconnect",
    user="sc_app",
    password="changeme_dev",
    host="localhost",
    port=5432
)
```

#### Option 3: GUI Tools
- pgAdmin 4


### .env Configuration
```dotenv
PG_URL=postgresql://sc_app:changeme_dev@localhost:5432/sportconnect
PG_USER=sc_app
PG_PASS=changeme_dev
APP_ENCRYPTION_KEY=dev-encryption-key-change-in-production-32chars
```

### Security Checklist

- [ ] Change `sc_app` password from default
- [ ] Change `sc_dba` password from default
- [ ] Update `APP_ENCRYPTION_KEY` to a secure 32+ character string
- [ ] Whitelist specific IPs for production connections
- [ ] Enable SSL/TLS for network connections
- [ ] Regular backups configured
- [ ] Enable audit logging for sensitive operations

### Useful SQL Queries

```sql
-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check role permissions
SELECT * FROM information_schema.role_table_grants 
WHERE grantee = 'sc_app';

-- View query performance
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Check active connections
SELECT datname, usename, count(*) 
FROM pg_stat_activity 
GROUP BY datname, usename;
```


### Related Files
- Schema: `scripts/sql/02_schema_local.sql`
- Roles: `scripts/sql/03_roles_permissions.sql`
- Test Data: `scripts/sql/04_test_data.sql`
- Original Schema: `scripts/sql/01_schema.sql` (with PostGIS for production)
- Setup Guide: `scripts/postgres/setup_guide.py`

