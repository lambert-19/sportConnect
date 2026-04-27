"""
SportConnect — PostgreSQL 16+ : Initialisation des rôles et données de test
Usage : python scripts/postgres/postgres_setup.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

PG_URL = os.getenv("PG_URL", "postgresql://postgres:@localhost:5432/sportconnect")

def get_connection():
    """Établit une connexion PostgreSQL."""
    try:
        print(f"  Connexion à : {PG_URL.split('@')[-1] if '@' in PG_URL else 'localhost'}")
        conn = psycopg2.connect(PG_URL, connect_timeout=5)
        print("OK Connexion PostgreSQL etablie")
        return conn
    except psycopg2.OperationalError as e:
        print(f"\nERREUR DE CONNEXION POSTGRESQL")
        print(f"   Message: {str(e)}")
        print(f"\nVERIFIEZ QUE:")
        print(f"   1. PostgreSQL est en cours d'execution")
        print(f"   2. La base 'sportconnect' existe")
        print(f"   3. Les identifiants dans PG_URL sont corrects")
        sys.exit(1)


def setup_roles(conn):
    """Configure les rôles PostgreSQL avec les bonnes permissions."""
    cursor = conn.cursor()
    
    print("\n[RÔLES] Configuration des rôles applicatifs...")
    
    # sc_readonly : lecture seule
    try:
        cursor.execute("CREATE ROLE sc_readonly;")
        print("  ✓ Rôle 'sc_readonly' créé")
    except psycopg2.errors.DuplicateObject:
        print("  ~ Rôle 'sc_readonly' existe déjà")
    
    # sc_app : lecture/écriture applicative
    try:
        cursor.execute(sql.SQL("CREATE ROLE sc_app LOGIN PASSWORD %s;"), 
                      (os.getenv("MONGO_PASS"),))
        print("  ✓ Rôle 'sc_app' créé avec LOGIN")
    except psycopg2.errors.DuplicateObject:
        print("  ~ Rôle 'sc_app' existe déjà")
    
    # sc_dba : administrateur
    try:
        cursor.execute(sql.SQL("CREATE ROLE sc_dba LOGIN PASSWORD %s SUPERUSER;"),
                      (os.getenv("MONGO_PASS"),))
        print("  ✓ Rôle 'sc_dba' créé avec SUPERUSER")
    except psycopg2.errors.DuplicateObject:
        print("  ~ Rôle 'sc_dba' existe déjà")
    
    # Permissions pour sc_readonly
    cursor.execute("GRANT CONNECT ON DATABASE sportconnect TO sc_readonly;")
    cursor.execute("GRANT USAGE ON SCHEMA public TO sc_readonly;")
    cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO sc_readonly;")
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sc_readonly;")
    print("  ✓ Permissions sc_readonly définies")
    
    # Permissions pour sc_app
    cursor.execute("GRANT CONNECT ON DATABASE sportconnect TO sc_app;")
    cursor.execute("GRANT USAGE ON SCHEMA public TO sc_app;")
    cursor.execute("GRANT SELECT, INSERT, UPDATE ON users, user_profiles, follows, comments, likes, notifications TO sc_app;")
    cursor.execute("GRANT INSERT ON audit_log TO sc_app;")
    cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sc_app;")
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO sc_app;")
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sc_app;")
    print("  ✓ Permissions sc_app définies")
    
    # Permissions pour sc_dba
    cursor.execute("GRANT ALL PRIVILEGES ON DATABASE sportconnect TO sc_dba;")
    cursor.execute("GRANT ALL PRIVILEGES ON SCHEMA public TO sc_dba;")
    cursor.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sc_dba;")
    cursor.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sc_dba;")
    cursor.execute("GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO sc_dba;")
    print("  ✓ Permissions sc_dba (superuser) définies")
    
    conn.commit()


def verify_schema(conn):
    """Vérifie que le schéma PostgreSQL est correctement initialisé."""
    cursor = conn.cursor()
    
    print("\n[SCHÉMA] Vérification des tables...")
    
    # Lister les tables créées
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    
    expected_tables = {
        'users', 'user_profiles', 'follows', 'comments', 
        'likes', 'notifications', 'audit_log'
    }
    
    if not tables:
        print("  ✗ Aucune table trouvée. Le schéma n'a pas été initialisé.")
        print("  💡 Vérifiez que le fichier scripts/sql/01_schema.sql a été exécuté")
        return False
    
    created_tables = {table[0] for table in tables}
    print(f"  ✓ {len(tables)} table(s) détectée(s)")
    
    # Vérifier les tables principales
    main_tables = expected_tables.intersection(created_tables)
    if main_tables:
        print(f"  ✓ Tables principales : {', '.join(sorted(main_tables))}")
    
    # Vérifier les extensions
    cursor.execute("""
        SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pgcrypto', 'postgis')
    """)
    extensions = {ext[0] for ext in cursor.fetchall()}
    
    if extensions:
        print(f"\n[EXTENSIONS] Extensions chargées : {', '.join(sorted(extensions))}")
    
    return True


def insert_test_data(conn):
    """Insère des données de test (développement uniquement)."""
    cursor = conn.cursor()
    
    print("\n[DONNÉES DE TEST] Insertion des utilisateurs de développement...")
    
    from hashlib import sha256
    
    # Admin user
    admin_email = "admin@sportconnect.app"
    admin_email_hash = sha256(admin_email.encode()).hexdigest()
    
    # Vérifier si l'utilisateur admin existe déjà
    cursor.execute("SELECT id FROM users WHERE email_hash = %s", (admin_email_hash,))
    if cursor.fetchone():
        print("  ~ Utilisateur admin existe déjà")
        return
    
    # Insérer l'admin
    cursor.execute(sql.SQL("""
        INSERT INTO users (email, email_hash, password_hash, role, is_active)
        VALUES (
            pgp_sym_encrypt(%s, %s),
            %s,
            crypt(%s, gen_salt('bf', 12)),
            'admin',
            TRUE
        )
        RETURNING id
    """), (
        admin_email,
        os.getenv("APP_ENCRYPTION_KEY", "dev-encryption-key-change-in-production-32chars"),
        admin_email_hash,
        "password123"
    ))
    
    admin_id = cursor.fetchone()[0]
    print(f"  ✓ Utilisateur admin créé : {admin_id}")
    
    # Créer le profil pour l'admin
    cursor.execute(sql.SQL("""
        INSERT INTO user_profiles (user_id, username, display_name, bio, is_public)
        VALUES (%s, %s, %s, %s, TRUE)
    """), (
        admin_id,
        "admin_sportconnect",
        "SportConnect Admin",
        "Administrateur du système SportConnect"
    ))
    print("  ✓ Profil admin créé")
    
    conn.commit()


def run_health_check(conn):
    """Effectue un health check du PostgreSQL."""
    cursor = conn.cursor()
    
    print("\n[HEALTH CHECK] Tests de fonctionnalité...")
    
    # Test JSON/JSONB support
    try:
        cursor.execute("SELECT '{\"test\": true}'::jsonb;")
        print("  ✓ Support JSONB : OK")
    except:
        print("  ✗ Support JSONB : ÉCHEC")
    
    # Test UUID support
    try:
        cursor.execute("SELECT gen_random_uuid();")
        print("  ✓ Support UUID : OK")
    except:
        print("  ✗ Support UUID : ÉCHEC")
    
    # Test pgcrypto
    try:
        cursor.execute("SELECT crypt('test', gen_salt('bf'));")
        print("  ✓ Support pgcrypto (bcrypt) : OK")
    except:
        print("  ✗ Support pgcrypto : ÉCHEC")
    
    # Test PostGIS
    try:
        cursor.execute("SELECT ST_AsText(ST_Point(0, 0));")
        print("  ✓ Support PostGIS : OK")
    except:
        print("  ✗ Support PostGIS : ÉCHEC")
    
    # Comptage des enregistrements
    cursor.execute("SELECT COUNT(*) FROM users;")
    user_count = cursor.fetchone()[0]
    print(f"\n  📊 Utilisateurs dans la base : {user_count}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  PostgreSQL Setup — SportConnect")
    print("=" * 60)
    
    conn = get_connection()
    
    try:
        setup_roles(conn)
        if verify_schema(conn):
            insert_test_data(conn)
            run_health_check(conn)
            print("\n✅ PostgreSQL initialisé avec succès\n")
        else:
            print("\n⚠️  Le schéma n'est pas complet. Merci de vérifier.")
    except Exception as e:
        print(f"\n❌ Erreur lors de l'initialisation : {e}")
        sys.exit(1)
    finally:
        conn.close()

