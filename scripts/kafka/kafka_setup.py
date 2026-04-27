"""
SportConnect — Kafka : Création des topics et configuration
Usage : python scripts/kafka/kafka_setup.py
"""

import os
from confluent_kafka.admin import AdminClient, NewTopic, KafkaError

def get_kafka_brokers():
    # Try loading from .env if not set in os.environ
    if not os.getenv("KAFKA_BROKERS"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
    return os.getenv("KAFKA_BROKERS", "localhost:9092")

KAFKA_BROKERS = get_kafka_brokers()

# Topics SportConnect selon dossier section 4.3
TOPICS = [
    {
        "name":              "sensor-raw",
        "num_partitions":    12,
        "replication_factor": 1,    # 3 en prod (MSK)
        "config": {
            "retention.ms":         str(24 * 3600 * 1000),   # 24h
            "cleanup.policy":       "delete",
            "compression.type":     "snappy",
            "max.message.bytes":    str(1024 * 1024),         # 1Mo max
        },
        "description": "Données brutes GPS + FC — 500M pts/j — consommateurs: Telegraf, Redis fallback",
    },
    {
        "name":              "activity-events",
        "num_partitions":    6,
        "replication_factor": 1,
        "config": {
            "retention.ms":         str(7 * 24 * 3600 * 1000),  # 7 jours
            "cleanup.policy":       "delete",
            "compression.type":     "gzip",
        },
        "description": "Événements publication activité — consommateurs: Neo4j, ES, Notification",
    },
    {
        "name":              "notification-events",
        "num_partitions":    3,
        "replication_factor": 1,
        "config": {
            "retention.ms":         str(3 * 24 * 3600 * 1000),  # 3 jours
            "cleanup.policy":       "delete",
            "compression.type":     "gzip",
        },
        "description": "Notifications push — consommateurs: Push Service, WebSocket Gateway",
    },
    {
        "name":              "gdpr-delete-events",
        "num_partitions":    1,
        "replication_factor": 1,
        "config": {
            "retention.ms":         str(30 * 24 * 3600 * 1000), # 30 jours
            "cleanup.policy":       "delete",
        },
        "description": "Saga droit à l'oubli RGPD — consommateur: Saga Orchestrator",
    },
]


def get_admin():
    conf = {"bootstrap.servers": KAFKA_BROKERS}
    print(f"Connecting to Kafka at: {KAFKA_BROKERS}")
    
    admin = AdminClient(conf)
    
    # Try to fetch metadata to verify connection
    try:
        # We just want to check connectivity, not list all topics immediately if it fails
        # list_topics calls metadata() internally
        metadata = admin.list_topics(timeout=10)
        print(f"✓ Connexion Kafka établie — {len(metadata.brokers)} broker(s) found")
        return admin
    except Exception as e:
        print(f"❌ Impossible de se connecter à Kafka ({KAFKA_BROKERS}) : {e}")
        # Check if running in Docker might be an issue or if the broker is down
        print("💡 Vérifiez que le conteneur Kafka est bien démarré : docker ps")
        exit(1)


def create_topics(admin):
    try:
        # Fetch existing topics to avoid recreation errors
        metadata = admin.list_topics(timeout=10)
        existing = set(metadata.topics.keys())
    except Exception as e:
        print(f"⚠ Erreur lors de la récupération des topics existants : {e}")
        return

    new_topics = []
    
    for t in TOPICS:
        if t["name"] in existing:
            print(f"  ~ Topic '{t['name']}' existe déjà")
        else:
            print(f"  + Préparation création topic '{t['name']}'")
            new_topic = NewTopic(
                t["name"],
                num_partitions=t["num_partitions"],
                replication_factor=t["replication_factor"],
                config=t["config"]
            )
            new_topics.append(new_topic)

    if not new_topics:
        return

    # Create topics asynchronously
    fs = admin.create_topics(new_topics)

    # Wait for each operation to finish
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None
            topic_conf = next(t for t in TOPICS if t["name"] == topic)
            print(f"  ✓ Topic '{topic}' créé avec succès")
        except Exception as e:
            print(f"  ❌ Échec création topic '{topic}': {e}")


if __name__ == "__main__":
    print("\n=== Kafka Setup — SportConnect ===")
    admin = get_admin()
    create_topics(admin)
    print("\n✅ Kafka initialisé avec succès\n")
