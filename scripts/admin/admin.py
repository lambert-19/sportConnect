"""
SportConnect — Scripts d'administration et maintenance
Couvre : health checks, monitoring, rotation des partitions, nettoyage RGPD

Usage :
    python scripts/admin/admin.py health-check
    python scripts/admin/admin.py monitor
    python scripts/admin/admin.py add-partitions --year 2027
    python scripts/admin/admin.py cleanup-notifications
    python scripts/admin/admin.py check-replication
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field


import psycopg2
import psycopg2.extras
from pymongo import MongoClient
from neo4j import GraphDatabase
import redis
from elasticsearch import Elasticsearch
from influxdb_client import InfluxDBClient
from confluent_kafka.admin import AdminClient

# ── Variables d'environnement ──────────────────────────────────────────────────
PG_DSN        = os.getenv("PG_URL",          "postgresql://postgres:#ibrahimaNDAW19@localhost:5432/sportconnect")
MONGO_URI     = os.getenv("MONGO_URI",        "mongodb://sportal_admin:changeme_dev@localhost:27017/sportconnect?authSource=admin")
NEO4J_URI     = os.getenv("NEO4J_URI",        "bolt://localhost:7687")
NEO4J_CREDS   = (os.getenv("NEO4J_USER",     "neo4j"), os.getenv("NEO4J_PASSWORD", "changeme_dev"))
REDIS_URL     = os.getenv("REDIS_URL",        "redis://:changeme_dev@localhost:6379/0")
ES_HOST       = os.getenv("ES_HOSTS",         "http://localhost:9200")
INFLUX_URL    = os.getenv("INFLUXDB_URL",     "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN",   "dev-token-changeme")
INFLUX_ORG    = os.getenv("INFLUXDB_ORG",     "sportconnect")
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS",    "localhost:9092")
GRAFANA_URL   = os.getenv("GRAFANA_CLOUD_URL", "https://ibrahima19.grafana.net")

# Seuils d'alerte (section 4.2 du dossier)
THRESHOLDS = {
    "pg_replication_lag_warn_mb":   10,
    "pg_replication_lag_crit_mb":   100,
    "pg_connections_warn":          150,
    "pg_connections_crit":          180,
    "pg_connections_max":           200,
    "mongo_waiting_ops_warn":       100,
    "mongo_waiting_ops_crit":       500,
    "redis_hit_rate_warn":          0.85,
    "redis_hit_rate_crit":          0.70,
    "influx_write_latency_warn_ms": 50,
    "influx_write_latency_crit_ms": 200,
    "kafka_consumer_lag_warn":      10_000,
    "kafka_consumer_lag_crit":      100_000,
    "kafka_disk_warn_pct":          70,
    "kafka_disk_crit_pct":          85,
    "es_heap_warn_pct":             75,
    "es_heap_crit_pct":             90,
}


# ── Structures de résultat ─────────────────────────────────────────────────────
@dataclass
class ServiceStatus:
    name:    str
    ok:      bool
    message: str
    metrics: dict = field(default_factory=dict)
    alerts:  list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def check_postgres() -> ServiceStatus:
    metrics, alerts = {}, []
    try:
        conn = psycopg2.connect(PG_DSN, connect_timeout=5)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Connexions actives
            cur.execute("""
                SELECT count(*) AS active
                FROM pg_stat_activity
                WHERE state = 'active' AND datname = 'sportconnect';
            """)
            active = cur.fetchone()["active"]
            metrics["connections_active"] = active
            if active >= THRESHOLDS["pg_connections_crit"]:
                alerts.append(f"CRITICAL : connexions actives = {active}/{THRESHOLDS['pg_connections_max']}")
            elif active >= THRESHOLDS["pg_connections_warn"]:
                alerts.append(f"WARNING : connexions actives = {active}/{THRESHOLDS['pg_connections_max']}")

            # Lag de réplication (si réplica connecté)
            cur.execute("""
                SELECT COALESCE(
                    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) / 1048576.0,
                    0
                ) AS lag_mb
                FROM pg_stat_replication
                LIMIT 1;
            """)
            row = cur.fetchone()
            lag_mb = float(row["lag_mb"]) if row else 0.0
            metrics["replication_lag_mb"] = lag_mb
            if lag_mb >= THRESHOLDS["pg_replication_lag_crit_mb"]:
                alerts.append(f"CRITICAL : lag réplication = {lag_mb:.1f} Mo")
            elif lag_mb >= THRESHOLDS["pg_replication_lag_warn_mb"]:
                alerts.append(f"WARNING : lag réplication = {lag_mb:.1f} Mo")

            # Taille de la base
            cur.execute("SELECT pg_size_pretty(pg_database_size('sportconnect')) AS size;")
            metrics["db_size"] = cur.fetchone()["size"]

            # Tables les plus volumineuses
            cur.execute("""
                SELECT relname AS table_name,
                       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT 5;
            """)
            metrics["top_tables"] = [dict(r) for r in cur.fetchall()]

            # Requêtes lentes (pg_stat_statements)
            cur.execute("""
                SELECT query, calls, round(mean_exec_time::numeric, 1) AS avg_ms
                FROM pg_stat_statements
                WHERE mean_exec_time > 500
                  AND dbid = (SELECT oid FROM pg_database WHERE datname = 'sportconnect')
                ORDER BY mean_exec_time DESC
                LIMIT 5;
            """)
            slow = cur.fetchall()
            if slow:
                metrics["slow_queries"] = [dict(r) for r in slow]
                alerts.append(f"INFO : {len(slow)} requête(s) lente(s) détectée(s) (>500ms)")

        conn.close()
        return ServiceStatus("PostgreSQL", True, f"OK — {active} connexions actives", metrics, alerts)
    except Exception as e:
        return ServiceStatus("PostgreSQL", False, f"ERREUR : {e}", alerts=["CRITICAL : PostgreSQL inaccessible"])


def check_mongodb() -> ServiceStatus:
    metrics, alerts = {}, []
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client["sportconnect"]
        server_status = db.command("serverStatus")

        # Opérations en attente
        waiting = server_status.get("globalLock", {}).get("currentQueue", {}).get("total", 0)
        metrics["waiting_operations"] = waiting
        if waiting >= THRESHOLDS["mongo_waiting_ops_crit"]:
            alerts.append(f"CRITICAL : {waiting} opérations en attente")
        elif waiting >= THRESHOLDS["mongo_waiting_ops_warn"]:
            alerts.append(f"WARNING : {waiting} opérations en attente")

        # Connexions
        conns = server_status.get("connections", {})
        metrics["connections_current"] = conns.get("current", 0)
        metrics["connections_available"] = conns.get("available", 0)

        # Taille de la collection activities
        stats = db.command("collStats", "activities")
        metrics["activities_count"]    = stats.get("count", 0)
        metrics["activities_size_mb"]  = round(stats.get("storageSize", 0) / 1_048_576, 1)
        metrics["activities_indexes"]  = stats.get("nindexes", 0)

        client.close()
        return ServiceStatus("MongoDB", True, "OK", metrics, alerts)
    except Exception as e:
        return ServiceStatus("MongoDB", False, f"ERREUR : {e}", alerts=["CRITICAL : MongoDB inaccessible"])


def check_redis() -> ServiceStatus:
    metrics, alerts = {}, []
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
        info = r.info()

        # Cache hit rate
        hits   = info.get("keyspace_hits",   0)
        misses = info.get("keyspace_misses", 0)
        total  = hits + misses
        hit_rate = hits / total if total > 0 else 1.0
        metrics["cache_hit_rate"]  = round(hit_rate, 4)
        metrics["keys_total"]      = sum(v.get("keys", 0) for v in (r.info("keyspace") or {}).values() if isinstance(v, dict))
        metrics["memory_used_mb"]  = round(info.get("used_memory", 0) / 1_048_576, 1)
        metrics["memory_peak_mb"]  = round(info.get("used_memory_peak", 0) / 1_048_576, 1)
        metrics["connected_clients"] = info.get("connected_clients", 0)

        if hit_rate < THRESHOLDS["redis_hit_rate_crit"]:
            alerts.append(f"CRITICAL : cache hit rate = {hit_rate:.1%} (seuil {THRESHOLDS['redis_hit_rate_crit']:.0%})")
        elif hit_rate < THRESHOLDS["redis_hit_rate_warn"]:
            alerts.append(f"WARNING : cache hit rate = {hit_rate:.1%} (seuil {THRESHOLDS['redis_hit_rate_warn']:.0%})")

        return ServiceStatus("Redis", True, f"OK — hit rate {hit_rate:.1%}", metrics, alerts)
    except Exception as e:
        return ServiceStatus("Redis", False, f"ERREUR : {e}", alerts=["CRITICAL : Redis inaccessible"])


def check_elasticsearch() -> ServiceStatus:
    metrics, alerts = {}, []
    try:
        es = Elasticsearch([ES_HOST], request_timeout=5)
        health  = es.cluster.health()
        stats   = es.nodes.stats(metric="jvm,indices")

        cluster_status = health["status"]
        metrics["cluster_status"]   = cluster_status
        metrics["active_shards"]    = health["active_shards"]
        metrics["unassigned_shards"] = health["unassigned_shards"]

        # Heap JVM
        for node_id, node in stats["nodes"].items():
            heap_pct = node["jvm"]["mem"]["heap_used_percent"]
            metrics[f"heap_pct_{node_id[:8]}"] = heap_pct
            if heap_pct >= THRESHOLDS["es_heap_crit_pct"]:
                alerts.append(f"CRITICAL : heap JVM = {heap_pct}% sur nœud {node_id[:8]}")
            elif heap_pct >= THRESHOLDS["es_heap_warn_pct"]:
                alerts.append(f"WARNING : heap JVM = {heap_pct}% sur nœud {node_id[:8]}")

        if cluster_status == "red":
            alerts.append("CRITICAL : cluster Elasticsearch en état RED")
        elif cluster_status == "yellow":
            alerts.append("WARNING : cluster Elasticsearch en état YELLOW")

        return ServiceStatus("Elasticsearch", True, f"OK — cluster {cluster_status}", metrics, alerts)
    except Exception as e:
        return ServiceStatus("Elasticsearch", False, f"ERREUR : {e}", alerts=["CRITICAL : Elasticsearch inaccessible"])


def check_kafka() -> ServiceStatus:
    metrics, alerts = {}, []
    try:
        admin = AdminClient({"bootstrap.servers": KAFKA_BROKERS,
                             "socket.timeout.ms": 5000})
        cluster_meta = admin.list_topics(timeout=10)
        metrics["brokers"]       = len(cluster_meta.brokers)
        metrics["topics"]        = len(cluster_meta.topics)
        metrics["topic_names"]   = sorted(cluster_meta.topics.keys())
        return ServiceStatus("Kafka", True, f"OK — {metrics['brokers']} broker(s)", metrics, alerts)
    except Exception as e:
        return ServiceStatus("Kafka", False, f"ERREUR : {e}", alerts=["CRITICAL : Kafka inaccessible"])


def check_influxdb() -> ServiceStatus:
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        health = client.health()
        client.close()
        ok = health.status == "pass"
        msg = f"OK — {health.message}" if ok else f"DÉGRADÉ — {health.message}"
        return ServiceStatus("InfluxDB", ok, msg,
                             alerts=[] if ok else [f"WARNING : {health.message}"])
    except Exception as e:
        return ServiceStatus("InfluxDB", False, f"ERREUR : {e}", alerts=["CRITICAL : InfluxDB inaccessible"])


def check_neo4j() -> ServiceStatus:
    metrics = {}
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_CREDS,
                                      connection_timeout=5)
        with driver.session() as s:
            r = s.run("CALL dbms.components() YIELD name, versions RETURN name, versions")
            row = r.single()
            metrics["version"] = row["versions"][0] if row else "?"

            r = s.run("MATCH (n) RETURN count(n) AS nodes")
            metrics["total_nodes"] = r.single()["nodes"]

            r = s.run("MATCH ()-[r]->() RETURN count(r) AS rels")
            metrics["total_relationships"] = r.single()["rels"]
        driver.close()
        return ServiceStatus("Neo4j", True, f"OK — v{metrics['version']}", metrics)
    except Exception as e:
        return ServiceStatus("Neo4j", False, f"ERREUR : {e}", alerts=["CRITICAL : Neo4j inaccessible"])


# ══════════════════════════════════════════════════════════════════════════════
# ADMINISTRATION POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def add_quarterly_partitions(year: int):
    """
    Crée les partitions trimestrielles pour comments et audit_log
    sur l'année donnée. À exécuter en début d'année (script ou cron).
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    quarters = [
        ("q1", f"{year}-01-01", f"{year}-04-01"),
        ("q2", f"{year}-04-01", f"{year}-07-01"),
        ("q3", f"{year}-07-01", f"{year}-10-01"),
        ("q4", f"{year}-10-01", f"{year+1}-01-01"),
    ]
    with conn.cursor() as cur:
        for table in ("comments", "audit_log"):
            for q, start, end in quarters:
                partition_name = f"{table}_{year}_{q}"
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF {table}
                    FOR VALUES FROM ('{start}') TO ('{end}');
                """)
                print(f"  ✓ Partition {partition_name} ({start} → {end})")
    conn.close()
    print(f"\n✅ Partitions {year} créées avec succès")


def cleanup_old_notifications():
    """Supprime les notifications lues de plus de 30 jours (remplace pg_cron en dev)."""
    conn = psycopg2.connect(PG_DSN)
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM notifications
            WHERE is_read = TRUE
              AND created_at < NOW() - INTERVAL '30 days';
        """)
        deleted = cur.rowcount
        conn.commit()
    conn.close()
    print(f"✅ {deleted} notifications supprimées")


def vacuum_analyze():
    """Lance un VACUUM ANALYZE sur les tables les plus actives."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    tables = ["users", "user_profiles", "follows", "likes", "notifications"]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"VACUUM ANALYZE {table};")
            print(f"  ✓ VACUUM ANALYZE {table}")
    conn.close()
    print("✅ VACUUM ANALYZE terminé")


def check_replication_lag():
    """Vérifie et affiche le lag de réplication PostgreSQL."""
    conn = psycopg2.connect(PG_DSN)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT client_addr,
                   state,
                   sent_lsn,
                   write_lsn,
                   flush_lsn,
                   replay_lsn,
                   pg_wal_lsn_diff(sent_lsn, replay_lsn) / 1048576.0 AS lag_mb,
                   sync_state
            FROM pg_stat_replication;
        """)
        replicas = cur.fetchall()

    if not replicas:
        print("ℹ️  Aucun réplica connecté (mode standalone)")
        return

    print(f"\n{'CLIENT':<20} {'STATE':<15} {'LAG (Mo)':<12} {'SYNC'}")
    print("-" * 60)
    for r in replicas:
        lag = float(r["lag_mb"] or 0)
        flag = "⚠️ WARN" if lag >= THRESHOLDS["pg_replication_lag_warn_mb"] else "✓"
        flag = "🔴 CRIT" if lag >= THRESHOLDS["pg_replication_lag_crit_mb"] else flag
        print(f"{str(r['client_addr']):<20} {r['state']:<15} {lag:<12.2f} {r['sync_state']} {flag}")
    conn.close()


def rotate_pg_roles(new_app_password: str):
    """Rotation du mot de passe du rôle sc_app (à planifier trimestriellement)."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ALTER ROLE sc_app PASSWORD %s;", (new_app_password,))
    conn.close()
    print("✅ Mot de passe sc_app mis à jour — pensez à mettre à jour Secret Manager")


# ===================================================================
# AUDIT DE COHÉRENCE (CROSS-DATABASE)
# ===================================================================

def check_consistency_pg_neo4j():
    """Vérifie que tous les utilisateurs actifs de PG existent dans Neo4j."""
    print("\n─── Audit de cohérence PG <-> Neo4j ─────────────────────────────")
    conn = psycopg2.connect(PG_DSN)
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_CREDS)
    
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE is_active = TRUE AND deleted_at IS NULL")
        pg_ids = {row[0] for row in cur.fetchall()}
        
    with driver.session() as s:
        result = s.run("MATCH (u:User) RETURN u.id AS id")
        neo4j_ids = {r["id"] for r in result}
    
    missing_in_graph = pg_ids - neo4j_ids
    missing_in_pg    = neo4j_ids - pg_ids
    
    if not missing_in_graph and not missing_in_pg:
        print("✅ Cohérence parfaite : les utilisateurs sont synchronisés.")
    else:
        if missing_in_graph:
            print(f"⚠️  {len(missing_in_graph)} utilisateurs PG manquants dans Neo4j (ex: {list(missing_in_graph)[:3]}...)")
        if missing_in_pg:
            print(f"⚠️  {len(missing_in_pg)} nœuds Neo4j orphelins (ex: {list(missing_in_pg)[:3]}...)")
    
    conn.close()
    driver.close()


# ══════════════════════════════════════════════════════════════════════════════
# ADMINISTRATION MONGODB
# ══════════════════════════════════════════════════════════════════════════════

def mongo_compact_collection(collection_name: str = "activities"):
    """Lance un compact sur la collection (libère l'espace disque fragmenté)."""
    client = MongoClient(MONGO_URI)
    db = client["sportconnect"]
    result = db.command("compact", collection_name)
    client.close()
    print(f"✅ MongoDB compact '{collection_name}' : {result}")


def mongo_check_indexes():
    """Liste les index inutilisés pour optimisation."""
    client = MongoClient(MONGO_URI)
    db = client["sportconnect"]
    stats = db.command("indexStats", "activities") if False else None
    # Utilise $indexStats aggregation
    pipeline = [{"$indexStats": {}}]
    results = list(db["activities"].aggregate(pipeline))
    client.close()
    print(f"\n{'INDEX':<40} {'OPS':<10} {'DEPUIS'}")
    print("-" * 65)
    for r in results:
        ops  = r.get("accesses", {}).get("ops", 0)
        since = r.get("accesses", {}).get("since", "?")
        flag = "  ⚠️  peu utilisé" if ops < 10 else ""
        print(f"{r['name']:<40} {ops:<10} {str(since)[:19]}{flag}")


# ══════════════════════════════════════════════════════════════════════════════
# ADMINISTRATION ELASTICSEARCH
# ══════════════════════════════════════════════════════════════════════════════

def es_force_ilm_rollover(index: str = "activities"):
    """Force un rollover ILM (utile si l'index hot atteint les limites)."""
    es = Elasticsearch([ES_HOST])
    result = es.ilm.move_to_step(
        index=index,
        body={"current_step": {"phase": "hot", "action": "rollover", "name": "check-rollover-ready"},
              "next_step":    {"phase": "hot", "action": "rollover", "name": "attempt-rollover"}}
    )
    print(f"✅ ILM rollover forcé sur '{index}' : {result}")


def es_list_indices_sizes():
    """Affiche la taille de chaque index."""
    es = Elasticsearch([ES_HOST])
    stats = es.indices.stats(index="_all", metric="store")
    print(f"\n{'INDEX':<35} {'TAILLE':<12} {'DOCS'}")
    print("-" * 55)
    for name, data in sorted(stats["indices"].items()):
        size_mb = data["total"]["store"]["size_in_bytes"] / 1_048_576
        docs    = data["total"].get("docs", {}).get("count", 0)
        print(f"{name:<35} {size_mb:>8.1f} Mo  {docs:>10} docs")


# ══════════════════════════════════════════════════════════════════════════════
# ADMINISTRATION REDIS
# ══════════════════════════════════════════════════════════════════════════════

def redis_memory_report():
    """Rapport mémoire Redis : top clés par type."""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    info = r.info("memory")
    print(f"\nMémoire utilisée : {info['used_memory_human']}")
    print(f"Pic mémoire      : {info['used_memory_peak_human']}")
    print(f"Fragmentation    : {info.get('mem_fragmentation_ratio', '?')}")

    # Scan et classification des clés
    counts = {"session": 0, "feed": 0, "profile": 0, "leaderboard": 0, "likes": 0, "other": 0}
    for key in r.scan_iter("*", count=100):
        for prefix in counts:
            if key.startswith(prefix + ":"):
                counts[prefix] += 1
                break
        else:
            counts["other"] += 1

    print(f"\n{'TYPE':<20} {'CLÉS'}")
    print("-" * 30)
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"{k:<20} {v}")


# ══════════════════════════════════════════════════════════════════════════════
# SAGA DROIT À L'OUBLI RGPD
# ══════════════════════════════════════════════════════════════════════════════

def execute_gdpr_delete(user_id: str, gdpr_ticket: str):
    """
    Exécute le Saga DeleteUserSaga (section 3.11 du dossier).
    7 étapes séquentielles avec journalisation de chaque étape.
    Les compensations en cas d'échec déclenchent une alerte manuelle.
    """
    print(f"\n=== Saga RGPD — Suppression utilisateur {user_id} (ticket {gdpr_ticket}) ===\n")
    completed_steps = []

    try:
        # Étape 1 — PostgreSQL : anonymisation
        conn = psycopg2.connect(PG_DSN)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET
                    email      = pgp_sym_encrypt(
                                     gen_random_uuid()::text,
                                     current_setting('app.encryption_key')),
                    email_hash = encode(sha256(gen_random_uuid()::text::bytea), 'hex'),
                    is_active  = FALSE,
                    deleted_at = NOW()
                WHERE id = %s;
            """, (user_id,))
            conn.commit()
        conn.close()
        completed_steps.append("postgresql_anonymize")
        print("  [1/7] ✓ PostgreSQL — email anonymisé, compte désactivé")

        # Étape 2 — MongoDB : suppression activités
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client["sportconnect"]
        for coll in ["activities", "notifications_push"]:
            result = db[coll].delete_many({"userId": user_id})
            print(f"  [2/7] ✓ MongoDB — {result.deleted_count} documents supprimés dans '{coll}'")
        mongo_client.close()
        completed_steps.append("mongodb_delete")

        # Étape 3 — Neo4j : DETACH DELETE
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_CREDS)
        with driver.session() as s:
            s.run("MATCH (u:User {id: $user_id}) DETACH DELETE u", user_id=user_id)
        driver.close()
        completed_steps.append("neo4j_delete")
        print("  [3/7] ✓ Neo4j — nœud User supprimé avec toutes ses relations")

        # Étape 4 — Redis : purge des clés
        r = redis.from_url(REDIS_URL, decode_responses=True)
        keys_deleted = 0
        for pattern in [f"session:*", f"feed:{user_id}", f"profile:*"]:
            for key in r.scan_iter(pattern):
                r.delete(key)
                keys_deleted += 1
        r.close()
        completed_steps.append("redis_purge")
        print(f"  [4/7] ✓ Redis — {keys_deleted} clés supprimées")

        # Étape 5 — Elasticsearch : delete_by_query
        es = Elasticsearch([ES_HOST])
        for index in ["activities", "users"]:
            es.delete_by_query(index=index, body={"query": {"term": {"userId": user_id}}})
        completed_steps.append("es_delete")
        print("  [5/7] ✓ Elasticsearch — documents supprimés")

        # Étape 6 — InfluxDB : suppression données capteurs
        influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        delete_api = influx_client.delete_api()
        start = "1970-01-01T00:00:00Z"
        stop  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for bucket in ["sensor_data", "sensor_1h", "sensor_daily"]:
            delete_api.delete(start, stop,
                              predicate=f'user_id="{user_id}"',
                              bucket=bucket, org=INFLUX_ORG)
        influx_client.close()
        completed_steps.append("influxdb_delete")
        print("  [6/7] ✓ InfluxDB — données capteurs supprimées dans les 3 buckets")

        # Étape 7 — Audit log PostgreSQL
        conn = psycopg2.connect(PG_DSN)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_log (user_id, action, details)
                VALUES (%s, 'gdpr_delete',
                        %s::jsonb);
            """, (user_id, json.dumps({
                "ticket":     gdpr_ticket,
                "steps":      completed_steps,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })))
            conn.commit()
        conn.close()
        print("  [7/7] ✓ audit_log — suppression RGPD journalisée")

        print(f"\n✅ Saga RGPD terminé avec succès — {len(completed_steps)} étapes complétées\n")

    except Exception as e:
        print(f"\n🔴 ÉCHEC à l'étape {len(completed_steps) + 1} : {e}")
        print(f"   Étapes complétées : {completed_steps}")
        print("   ⚠️  Intervention manuelle requise — déclencher alerte PagerDuty")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def cmd_health_check(args):
    """Lance les health checks sur tous les services."""
    print("\n" + "=" * 60)
    print("  SportConnect — Health Check")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 60)

    checks = [
        check_postgres,
        check_mongodb,
        check_redis,
        check_elasticsearch,
        check_kafka,
        check_influxdb,
        check_neo4j,
    ]
    all_ok = True
    for check_fn in checks:
        status = check_fn()
        icon   = "OK" if status.ok else "FAIL"
        print(f"\n{icon} {status.name:<20} {status.message}")
        for alert in status.alerts:
            level = "CRITICAL" if "CRITICAL" in alert else "WARNING" if "WARNING" in alert else "INFO"
            print(f"   {level}:  {alert}")
        if args.verbose and status.metrics:
            for k, v in status.metrics.items():
                if not isinstance(v, (list, dict)):
                    print(f"      {k}: {v}")
        if not status.ok:
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("  OK Tous les services sont operationnels")
    else:
        print("  FAIL Des services necessitent une intervention")
    print("=" * 60 + "\n")
    sys.exit(0 if all_ok else 1)


def cmd_add_partitions(args):
    add_quarterly_partitions(args.year)


def cmd_cleanup_notifications(args):
    cleanup_old_notifications()


def cmd_check_replication(args):
    check_replication_lag()


def cmd_vacuum(args):
    vacuum_analyze()


def cmd_gdpr_delete(args):
    execute_gdpr_delete(args.user_id, args.ticket)


def cmd_redis_report(args):
    redis_memory_report()


def cmd_mongo_indexes(args):
    mongo_check_indexes()


def cmd_es_indices(args):
    es_list_indices_sizes()


def main():
    parser = argparse.ArgumentParser(description="SportConnect — Admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health-check",           help="Vérifie tous les services")
    p_health.add_argument("--verbose", "-v", action="store_true")
    p_health.set_defaults(func=cmd_health_check)

    p_consist = sub.add_parser("check-consistency",     help="Audit cohérence PG vs Neo4j")
    p_consist.set_defaults(func=lambda a: check_consistency_pg_neo4j())

    p_parts = sub.add_parser("add-partitions",          help="Crée les partitions PG pour une année")
    p_parts.add_argument("--year", type=int, default=datetime.now().year + 1)
    p_parts.set_defaults(func=cmd_add_partitions)

    p_clean = sub.add_parser("cleanup-notifications",   help="Purge les notifications lues > 30j")
    p_clean.set_defaults(func=cmd_cleanup_notifications)

    p_repl = sub.add_parser("check-replication",        help="Vérifie le lag réplication PG")
    p_repl.set_defaults(func=cmd_check_replication)

    p_vac = sub.add_parser("vacuum",                    help="VACUUM ANALYZE PostgreSQL")
    p_vac.set_defaults(func=cmd_vacuum)

    p_gdpr = sub.add_parser("gdpr-delete",              help="Suppression RGPD complète (Saga)")
    p_gdpr.add_argument("--user-id", required=True)
    p_gdpr.add_argument("--ticket",  required=True)
    p_gdpr.set_defaults(func=cmd_gdpr_delete)

    p_redis = sub.add_parser("redis-report",            help="Rapport mémoire Redis")
    p_redis.set_defaults(func=cmd_redis_report)

    p_mongo = sub.add_parser("mongo-indexes",           help="Audit des index MongoDB")
    p_mongo.set_defaults(func=cmd_mongo_indexes)

    p_es = sub.add_parser("es-indices",                 help="Taille des index Elasticsearch")
    p_es.set_defaults(func=cmd_es_indices)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
