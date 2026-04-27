#!/usr/bin/env python3
"""
SportConnect — PostgreSQL Setup für lokale Entwicklung
Schritt-für-Schritt Anleitung
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

def main():
    print("\n" + "=" * 70)
    print("  📊 PostgreSQL Setup — SportConnect (Lokale Entwicklung)")
    print("=" * 70)
    
    pg_host = "localhost"
    pg_port = 5432
    pg_user = os.getenv("PG_USER", "postgres")
    pg_db = "sportconnect"
    
    script_dir = Path(__file__).parent.parent / "sql"
    
    print(f"\n✅ Ihr PostgreSQL-Status:")
    print(f"   🔌 Host: {pg_host}")
    print(f"   👤 Benutzer: {pg_user}")
    print(f"   🗄️  Datenbank: {pg_db}")
    
    print(f"\n📋 Führen Sie folgende Befehle in PowerShell aus:\n")
    
    print(f"# 1. Schema-Datei laden (lokal, ohne PostGIS)")
    schema_cmd = f'psql -U {pg_user} -h {pg_host} -d {pg_db} -f "{script_dir}/02_schema_local.sql"'
    print(f"   {schema_cmd}\n")
    
    print(f"# 2. Rollen und Berechtigungen erstellen")
    roles_cmd = f'psql -U {pg_user} -h {pg_host} -d {pg_db} -f "{script_dir}/03_roles_permissions.sql"'
    print(f"   {roles_cmd}\n")
    
    print(f"# 3. Datenbank-Status überprüfen")
    status_cmd = f'psql -U {pg_user} -h {pg_host} -d {pg_db} -c "\\dt; \\du"'
    print(f"   {status_cmd}\n")
    
    print("=" * 70)
    print("\n💡 Tipps:")
    print("   • Wenn Passwort-Fehler auftreten, legen Sie eine .pgpass-Datei an")
    print("   • Dateipfade mit Spaces: psql -f \"C:\\\\My Path\\\\script.sql\"")
    print("   • Windows-User können auch pgAdmin oder DBeaver verwenden")
    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    main()

