"""
SportConnect — PostgreSQL Setup für lokale Entwicklung
Usage: python scripts/postgres/postgres_init.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

def main():
    print("\n" + "=" * 60)
    print("  PostgreSQL Setup — SportConnect (Lokale Entwicklung)")
    print("=" * 60)
    
    pg_user = os.getenv("PG_USER", "postgres")
    pg_host = "localhost"
    pg_db = "sportconnect"
    
    print(f"\n📋 Schritte zur manuellen Initialisierung:")
    print(f"\n1. Öffne einen PostgreSQL-Client (pgAdmin, psql, DBeaver, etc.)")
    print(f"   Verbindungsdetails:")
    print(f"   - Host: {pg_host}")
    print(f"   - Benutzername: {pg_user}")
    print(f"   - Datenbank: {pg_db}")
    
    print(f"\n2. Führe die SQL-Schema-Datei aus:")
    schema_file = Path(__file__).parent.parent / "sql" / "02_schema_local.sql"
    print(f"   psql -U {pg_user} -h {pg_host} -d {pg_db} -f {schema_file.relative_to(Path.cwd())}")
    
    print(f"\n3. Erstelle die notwendigen Rollen:")
    print(f"""
    CREATE ROLE sc_readonly;
    CREATE ROLE sc_app LOGIN PASSWORD 'changeme_dev';
    CREATE ROLE sc_dba LOGIN PASSWORD 'changeme_dev' SUPERUSER;
    """)
    
    print(f"\n4. Geben Sie den Rollen Berechtigungen:")
    print(f"""
    GRANT CONNECT ON DATABASE {pg_db} TO sc_readonly;
    GRANT USAGE ON SCHEMA public TO sc_readonly;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO sc_readonly;
    """)
    
    print(f"\n5. Fügen Sie Test-Daten ein (optional):")
    print(f"""
    INSERT INTO users (email, email_hash, password_hash, role, is_active)
    VALUES (
        pgp_sym_encrypt('admin@sportconnect.app', 'dev-encryption-key-change-in-production-32chars'),
        encode(sha256('admin@sportconnect.app'::bytea), 'hex'),
        crypt('password123', gen_salt('bf', 12)),
        'admin',
        TRUE
    );
    """)
    
    print("\n✅ PostgreSQL ist nun bereit zur Verwendung!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()

