"""
SportConnect — Script d'initialisation principale
Lance tous les scripts de setup dans le bon ordre.

Usage :
    python scripts/init_all.py                  # Initialise tout
    python scripts/init_all.py --skip-docker    # Sans démarrer Docker
    python scripts/init_all.py --only postgres  # Un seul service
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# Load .env from project root — must be before any os.getenv() calls
load_dotenv(dotenv_path=BASE_DIR.parent / ".env")


def wait_for_service(name: str, check_fn, max_retries: int = 30, delay: int = 3):
    """Attend qu'un service soit prêt (polling)."""
    print(f"  [WAIT] Attente de {name}...", end="", flush=True)
    for i in range(max_retries):
        try:
            check_fn()
            print(f" [OK] prêt ({(i+1)*delay}s)")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(delay)
    print(f"\n  [FAIL] {name} non disponible après {max_retries * delay}s")
    return False


def start_docker():
    print("\n[1/8] Démarrage de la stack Docker...")
    result = subprocess.run(
        ["docker", "compose", "-f", str(BASE_DIR.parent / "docker" / "docker-compose.yml"), "up", "-d"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] Docker Compose échoué :\n{result.stderr}")
        sys.exit(1)
    print("  [OK] Conteneurs démarrés")
    time.sleep(5)  # Laisse le temps aux services de s'initialiser


def init_postgres():
    print("\n[2/8] Initialisation PostgreSQL...")
    # Le DDL est exécuté automatiquement par docker-entrypoint-initdb.d
    # Ce check confirme que la base est accessible et le schéma présent
    import psycopg2
    pg_dsn = os.getenv("PG_URL", "postgresql://sportal_admin:changeme_dev@localhost:5432/sportconnect")

    ok = wait_for_service("PostgreSQL", lambda: psycopg2.connect(pg_dsn, connect_timeout=3).close())
    if not ok:
        sys.exit(1)

    conn = psycopg2.connect(pg_dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
        table_count = cur.fetchone()[0]
    conn.close()
    print(f"  [OK] Schéma PostgreSQL : {table_count} table(s) trouvée(s)")


def init_mongodb():
    print("\n[3/8] Initialisation MongoDB...")
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI")

    ok = wait_for_service("MongoDB", lambda: MongoClient(mongo_uri, serverSelectionTimeoutMS=3000).admin.command("ping"))
    if not ok:
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "mongodb" / "mongodb_setup.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] MongoDB setup échoué :\n{result.stderr}")
        sys.exit(1)
    print(result.stdout.strip())


def init_neo4j():
    print("\n[4/8] Initialisation Neo4j...")
    from neo4j import GraphDatabase
    neo4j_uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER",     "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASS",     "changeme_dev")

    ok = wait_for_service("Neo4j", lambda: GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass)).verify_connectivity())
    if not ok:
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "neo4j" / "neo4j_setup.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] Neo4j setup échoué :\n{result.stderr}")
        sys.exit(1)
    print(result.stdout.strip())


def init_influxdb():
    print("\n[5/8] Initialisation InfluxDB...")
    from influxdb_client import InfluxDBClient
    influx_url   = os.getenv("INFLUXDB_URL",   "http://localhost:8086")
    influx_token = os.getenv("INFLUXDB_TOKEN", "dev-token-changeme")
    influx_org   = os.getenv("INFLUXDB_ORG",   "sportconnect")

    ok = wait_for_service("InfluxDB", lambda: InfluxDBClient(url=influx_url, token=influx_token, org=influx_org).health())
    if not ok:
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "influxdb" / "influxdb_setup.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] InfluxDB setup échoué :\n{result.stderr}")
        sys.exit(1)
    print(result.stdout.strip())


def init_elasticsearch():
    print("\n[6/8] Initialisation Elasticsearch...")
    import requests
    es_host = os.getenv("ES_HOSTS", "http://localhost:9200")

    ok = wait_for_service("Elasticsearch", lambda: requests.get(f"{es_host}/_cluster/health", timeout=3).raise_for_status())
    if not ok:
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "elasticsearch" / "elasticsearch_setup.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] Elasticsearch setup échoué :\n{result.stderr}")
        sys.exit(1)
    print(result.stdout.strip())


def init_kafka():
    print("\n[7/8] Initialisation Kafka...")
    from confluent_kafka.admin import AdminClient
    brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")

    ok = wait_for_service("Kafka", lambda: AdminClient({"bootstrap.servers": brokers, "socket.timeout.ms": 3000}).list_topics(timeout=3))
    if not ok:
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "kafka" / "kafka_setup.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [FAIL] Kafka setup échoué :\n{result.stderr}")
        sys.exit(1)
    print(result.stdout.strip())


def run_health_check():
    print("\n[8/8] Health check final...")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "admin" / "admin.py"), "health-check"],
        capture_output=False
    )
    return result.returncode == 0


STEPS = {
    "docker":        start_docker,
    "postgres":      init_postgres,
    "mongodb":       init_mongodb,
    "neo4j":         init_neo4j,
    "influxdb":      init_influxdb,
    "elasticsearch": init_elasticsearch,
    "kafka":         init_kafka,
    "health":        run_health_check,
}


def main():
    parser = argparse.ArgumentParser(description="SportConnect — Init all services")
    parser.add_argument("--skip-docker", action="store_true", help="Ne pas démarrer Docker Compose")
    parser.add_argument("--only",        choices=list(STEPS.keys()), help="N'initialise qu'un service")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  SportConnect — Initialisation de l'environnement")
    print("=" * 60)

    if args.only:
        STEPS[args.only]()
    else:
        for name, fn in STEPS.items():
            if args.skip_docker and name == "docker":
                continue
            fn()

    print("\n" + "=" * 60)
    print("  [OK] Environnement SportConnect prêt !")
    print("     PostgreSQL    : localhost:5432")
    print("     MongoDB       : Atlas (voir MONGO_URI dans .env)")
    print("     Neo4j         : localhost:7687  (browser: http://localhost:7474)")
    print("     Elasticsearch : http://localhost:9200")
    print("     Kafka         : localhost:9092")
    print("     Grafana       : http://localhost:3000")
    print("  [WARN] InfluxDB / Redis : non définis dans docker-compose.yml")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()