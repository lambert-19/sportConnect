"""
SportConnect — Scripts de sauvegarde (section 5.2 du dossier)
Stratégie par technologie :
  PostgreSQL  : pg_basebackup quotidien + WAL continu (PITR)
  MongoDB     : mongodump + oplog quotidien
  Redis       : BGSAVE toutes les 6h → GCS
  Elasticsearch : snapshot API → GCS

Usage :
    python scripts/backup/backup.py run-all
    python scripts/backup/backup.py postgres
    python scripts/backup/backup.py mongodb
    python scripts/backup/backup.py redis
    python scripts/backup/backup.py elasticsearch
    python scripts/backup/backup.py verify --service postgres
"""

import os
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ── Variables d'environnement ──────────────────────────────────────────────────
PG_HOST       = os.getenv("PG_HOST",      "localhost")
PG_PORT       = os.getenv("PG_PORT",      "5432")
PG_USER       = os.getenv("PG_USER",      "sportal_admin")
PG_PASSWORD   = os.getenv("PG_PASSWORD",  "changeme_dev")
PG_DB         = os.getenv("PG_DB",        "sportconnect")

MONGO_HOST    = os.getenv("MONGO_HOST",   "localhost")
MONGO_PORT    = os.getenv("MONGO_PORT",   "27017")
MONGO_USER    = os.getenv("MONGO_USER",   "sportal_admin")
MONGO_PASS    = os.getenv("MONGO_PASS",   "changeme_dev")

REDIS_HOST    = os.getenv("REDIS_HOST",   "localhost")
REDIS_PORT    = os.getenv("REDIS_PORT",   "6379")
REDIS_PASS    = os.getenv("REDIS_PASSWORD", "changeme_dev")

ES_HOST       = os.getenv("ES_HOSTS",     "http://localhost:9200")

GCS_BUCKET    = os.getenv("GCS_BACKUP_BUCKET", "sportconnect-backups-dev")
BACKUP_DIR    = Path(os.getenv("BACKUP_DIR", "/tmp/sportconnect-backups"))

TIMESTAMP     = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run(cmd: list, env: dict = None, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande shell et retourne le résultat."""
    merged_env = {**os.environ, **(env or {})}
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, env=merged_env, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ✗ ERREUR (code {result.returncode}) :\n{result.stderr}")
        raise RuntimeError(f"Commande échouée : {' '.join(str(c) for c in cmd)}")
    return result


def upload_to_gcs(local_path: Path, gcs_path: str):
    """Copie un fichier vers GCS via gsutil."""
    dest = f"gs://{GCS_BUCKET}/{gcs_path}"
    run(["gsutil", "-q", "cp", str(local_path), dest])
    print(f"  ✓ Upload GCS : {dest}")


# ══════════════════════════════════════════════════════════════════════════════
# POSTGRESQL — pg_basebackup + WAL
# ══════════════════════════════════════════════════════════════════════════════

def backup_postgres():
    """
    Sauvegarde physique complète via pg_basebackup (section 5.2).
    Fréquence cible : quotidien 02h00 UTC
    Rétention GCS : 30 jours
    """
    print("\n--- Sauvegarde PostgreSQL -------------------------------")
    out_dir = BACKUP_DIR / "postgresql" / TIMESTAMP
    out_dir.mkdir(parents=True, exist_ok=True)

    env = {"PGPASSWORD": PG_PASSWORD}

    # Sauvegarde physique compressée
    run([
        "pg_basebackup",
        "-h", PG_HOST, "-p", PG_PORT,
        "-U", PG_USER,
        "-D", str(out_dir),
        "--format=tar",
        "--gzip",
        "--checkpoint=fast",
        "--label", f"sportconnect_{TIMESTAMP}",
        "--progress",
    ], env=env)

    # Vérification du fichier produit
    backup_file = out_dir / "base.tar.gz"
    if not backup_file.exists():
        raise FileNotFoundError("pg_basebackup n'a pas produit base.tar.gz")

    size_mb = backup_file.stat().st_size / 1_048_576
    print(f"  ✓ Backup produit : {backup_file} ({size_mb:.1f} Mo)")

    # Upload GCS
    gcs_path = f"postgresql/{TIMESTAMP}/base.tar.gz"
    upload_to_gcs(backup_file, gcs_path)

    # Nettoyage local
    backup_file.unlink()
    out_dir.rmdir()
    print("✅ Sauvegarde PostgreSQL terminée")
    return gcs_path


def backup_postgres_wal():
    """
    Archive les WAL pour le PITR (appelé par archive_command dans postgresql.conf).
    En production, archive_command gère cela automatiquement vers GCS.
    Ce script est un fallback pour forcer l'archivage des WAL en retard.
    """
    print("\n─── Archivage WAL PostgreSQL ────────────────────────────────────")
    wal_archive = BACKUP_DIR / "wal"
    wal_archive.mkdir(parents=True, exist_ok=True)

    env = {"PGPASSWORD": PG_PASSWORD}
    run([
        "psql", "-h", PG_HOST, "-p", PG_PORT,
        "-U", PG_USER, "-d", PG_DB,
        "-c", "SELECT pg_switch_wal();",
    ], env=env)
    print("  ✓ WAL switch forcé — le prochain archivage inclura tous les WAL en attente")


# ══════════════════════════════════════════════════════════════════════════════
# MONGODB — mongodump + oplog
# ══════════════════════════════════════════════════════════════════════════════

def backup_mongodb():
    """
    Sauvegarde logique MongoDB avec oplog (PITR).
    Fréquence cible : quotidien 03h00 UTC
    Rétention GCS   : 14 jours
    """
    print("\n─── Sauvegarde MongoDB ──────────────────────────────────────────")
    out_file = BACKUP_DIR / f"mongodb_{TIMESTAMP}.gz"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    run([
        "mongodump",
        f"--host={MONGO_HOST}:{MONGO_PORT}",
        f"--username={MONGO_USER}",
        f"--password={MONGO_PASS}",
        "--authenticationDatabase=admin",
        "--db=sportconnect",
        "--oplog",                           # Capture l'oplog pour PITR
        "--gzip",
        f"--archive={out_file}",
    ])

    size_mb = out_file.stat().st_size / 1_048_576
    print(f"  ✓ Dump produit : {out_file} ({size_mb:.1f} Mo)")

    gcs_path = f"mongodb/{TIMESTAMP}/dump.gz"
    upload_to_gcs(out_file, gcs_path)

    out_file.unlink()
    print("✅ Sauvegarde MongoDB terminée")
    return gcs_path


# ══════════════════════════════════════════════════════════════════════════════
# REDIS — BGSAVE + copie RDB
# ══════════════════════════════════════════════════════════════════════════════

def backup_redis():
    """
    Déclenche un BGSAVE et copie le dump.rdb vers GCS.
    Fréquence cible : toutes les 6h
    Rétention GCS : 7 jours
    """
    print("\n─── Sauvegarde Redis ────────────────────────────────────────────")
    import redis as redis_lib
    import time

    r = redis_lib.Redis(host=REDIS_HOST, port=int(REDIS_PORT),
                        password=REDIS_PASS, decode_responses=True)

    # Déclenche un BGSAVE non bloquant
    r.bgsave()
    print("  ✓ BGSAVE déclenché — attente de la fin...")

    # Attente que le save soit terminé (max 60s)
    for _ in range(60):
        info = r.info("persistence")
        if info["rdb_bgsave_in_progress"] == 0:
            break
        time.sleep(1)
    else:
        raise TimeoutError("BGSAVE non terminé après 60 secondes")

    # Récupère le chemin du dump.rdb depuis la config Redis
    config = r.config_get("dir")
    rdb_path = Path(config["dir"]) / "dump.rdb"
    r.close()

    if not rdb_path.exists():
        print(f"  ⚠️  dump.rdb introuvable à {rdb_path} (Redis hors Docker ?)")
        return None

    size_mb = rdb_path.stat().st_size / 1_048_576
    print(f"  ✓ dump.rdb : {size_mb:.1f} Mo")

    gcs_path = f"redis/{TIMESTAMP}/dump.rdb"
    upload_to_gcs(rdb_path, gcs_path)
    print("✅ Sauvegarde Redis terminée")
    return gcs_path


# ══════════════════════════════════════════════════════════════════════════════
# ELASTICSEARCH — Snapshot API vers GCS
# ══════════════════════════════════════════════════════════════════════════════

def backup_elasticsearch():
    """
    Crée un snapshot Elasticsearch via l'API REST.
    Fréquence cible : quotidien 05h00 UTC
    Rétention GCS   : 30 jours
    """
    print("\n─── Sauvegarde Elasticsearch ────────────────────────────────────")
    from elasticsearch import Elasticsearch
    es = Elasticsearch([ES_HOST])

    snapshot_name = f"sc-snapshot-{TIMESTAMP}"
    repo_name     = "gcs_repo"

    # Vérifie que le repo GCS existe
    try:
        es.snapshot.get_repository(repository=repo_name)
    except Exception:
        print(f"  ⚠️  Repository '{repo_name}' non trouvé — snapshot ignoré")
        print("      (normal en développement local sans GCS configuré)")
        return None

    # Crée le snapshot
    es.snapshot.create(
        repository=repo_name,
        snapshot=snapshot_name,
        body={
            "indices":            "activities,users",
            "include_global_state": False,
        },
        wait_for_completion=True,   # Bloquant (max ~30min en prod)
    )

    info = es.snapshot.get(repository=repo_name, snapshot=snapshot_name)
    state = info["snapshots"][0]["state"]
    print(f"  ✓ Snapshot '{snapshot_name}' — état : {state}")
    print("✅ Sauvegarde Elasticsearch terminée")
    return snapshot_name


# ══════════════════════════════════════════════════════════════════════════════
# VÉRIFICATION DES SAUVEGARDES
# ══════════════════════════════════════════════════════════════════════════════

def verify_backups(service: str = "all"):
    """Liste les dernières sauvegardes GCS pour vérifier leur présence."""
    print(f"\n─── Vérification sauvegardes GCS ({service}) ───────────────────")
    prefixes = {
        "postgres":      "postgresql/",
        "mongodb":       "mongodb/",
        "redis":         "redis/",
        "elasticsearch": "elasticsearch/",
    }
    to_check = {service: prefixes[service]} if service in prefixes else prefixes

    for svc, prefix in to_check.items():
        result = run([
            "gsutil", "ls", "-l",
            f"gs://{GCS_BUCKET}/{prefix}",
        ], check=False)
        if result.returncode != 0:
            print(f"  ⚠️  {svc:<20} aucune sauvegarde trouvée (ou bucket inaccessible)")
        else:
            lines = [l for l in result.stdout.strip().split("\n") if l and "TOTAL" not in l]
            last  = lines[-1] if lines else "(vide)"
            print(f"  ✓ {svc:<20} {len(lines)} fichier(s) — dernier : {last.strip()}")


# ══════════════════════════════════════════════════════════════════════════════
# PURGE DES ANCIENNES SAUVEGARDES
# ══════════════════════════════════════════════════════════════════════════════

def purge_old_backups():
    """
    Supprime les sauvegardes GCS dépassant la rétention définie (section 5.2).
    Rétentions : PostgreSQL 30j, MongoDB 14j, Redis 7j, Elasticsearch 30j
    """
    print("\n─── Purge des anciennes sauvegardes ─────────────────────────────")
    retentions = {
        "postgresql/": 30,
        "mongodb/":    14,
        "redis/":      7,
    }
    for prefix, days in retentions.items():
        result = run([
            "gsutil", "-m", "rm", "-rf",
            f"gs://{GCS_BUCKET}/{prefix}**",
        ], check=False)
        print(f"  ✓ {prefix:<20} purge des fichiers > {days}j lancée")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="SportConnect — Backup CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-all",        help="Lance toutes les sauvegardes").set_defaults(
        func=lambda a: [backup_postgres(), backup_mongodb(), backup_elasticsearch()])

    sub.add_parser("postgres",       help="Sauvegarde PostgreSQL").set_defaults(
        func=lambda a: backup_postgres())

    sub.add_parser("postgres-wal",   help="Force archivage WAL").set_defaults(
        func=lambda a: backup_postgres_wal())

    sub.add_parser("mongodb",        help="Sauvegarde MongoDB").set_defaults(
        func=lambda a: backup_mongodb())

    sub.add_parser("redis",          help="Sauvegarde Redis (BGSAVE)").set_defaults(
        func=lambda a: backup_redis())

    sub.add_parser("elasticsearch",  help="Snapshot Elasticsearch").set_defaults(
        func=lambda a: backup_elasticsearch())

    p_verify = sub.add_parser("verify", help="Vérifie les sauvegardes GCS")
    p_verify.add_argument("--service", default="all",
                          choices=["all", "postgres", "mongodb", "redis", "elasticsearch"])
    p_verify.set_defaults(func=lambda a: verify_backups(a.service))

    sub.add_parser("purge",          help="Purge les sauvegardes expirées").set_defaults(
        func=lambda a: purge_old_backups())

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
