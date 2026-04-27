"""
SportConnect — Redis Cloud : Initialisation du cache et données de test
Usage : python scripts/redis/redis_setup.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import redis

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

REDIS_URL = os.getenv("REDIS_URL")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_HOST = os.getenv("REDIS_URL", "").replace("redis://:", "").replace("redis://default:", "").split(":")[0] if os.getenv("REDIS_URL") else "localhost"
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

def get_client():
    """Établit une connexion Redis."""
    try:
        print(f"Connexion à Redis : {REDIS_HOST}:{REDIS_PORT}")

        if REDIS_URL:
            # Using URL format (for cloud Redis)
            r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=10)
        else:
            # Using host/port format
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=10
            )

        # Test connection
        r.ping()
        print("✓ Connexion Redis établie")
        return r

    except redis.ConnectionError as e:
        print(f"\n❌ ERREUR DE CONNEXION REDIS")
        print(f"   Message: {str(e)}")
        print(f"\n⚠️  Vérifiez que:")
        print(f"   1. Redis est en cours d'exécution sur {REDIS_HOST}:{REDIS_PORT}")
        print(f"   2. Les identifiants dans .env sont corrects")
        print(f"   3. Le mot de passe est valide pour Redis Cloud")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur : {str(e)}")
        sys.exit(1)


def setup_cache_keys(client):
    """Configure les clés de cache de base."""
    print("\n[CACHE] Configuration des clés de base...")

    try:
        # Configuration globale
        client.set("sportconnect:version", "1.0.0")
        client.set("sportconnect:env", os.getenv("ENVIRONMENT", "development"))
        client.set("sportconnect:cache_ttl", "300")  # 5 minutes par défaut

        # Statistiques de base
        client.set("stats:users_count", "3")  # Sera mis à jour dynamiquement
        client.set("stats:activities_count", "2")
        client.set("stats:connections_count", "1")

        print("  ✓ Clés de configuration définies")

    except Exception as e:
        print(f"❌ Erreur lors de la configuration des clés : {str(e)}")
        return False

    return True


def insert_test_data(client):
    """Insère des données de test pour démonstration."""
    print("\n[DONNÉES] Insertion des données de test...")

    try:
        # Cache des profils utilisateur (similaire à PostgreSQL)
        profiles = {
            "admin_sportconnect": {
                "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "username": "admin_sportconnect",
                "display_name": "SportConnect Admin",
                "bio": "System Administrator",
                "followers_count": 0,
                "following_count": 0,
                "is_public": True
            },
            "runner_john": {
                "user_id": "user-1-id",
                "username": "runner_john",
                "display_name": "John Runner",
                "bio": "Passionate about running",
                "followers_count": 0,
                "following_count": 1,
                "is_public": True
            },
            "cyclist_sarah": {
                "user_id": "user-2-id",
                "username": "cyclist_sarah",
                "display_name": "Sarah Cyclist",
                "bio": "Cycling enthusiast",
                "followers_count": 1,
                "following_count": 0,
                "is_public": True
            }
        }

        # Cache des profils (TTL 5 minutes)
        for username, profile in profiles.items():
            key = f"profile:{username.lower()}"
            client.setex(key, 300, json.dumps(profile))

        print(f"  ✓ {len(profiles)} profils mis en cache")

        # Sessions de test
        sessions = {
            "test_session_admin": {
                "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "username": "admin_sportconnect",
                "role": "admin",
                "ip": "127.0.0.1"
            },
            "test_session_user": {
                "user_id": "user-1-id",
                "username": "runner_john",
                "role": "user",
                "ip": "127.0.0.1"
            }
        }

        # Sessions (TTL 1 heure)
        for token, session_data in sessions.items():
            key = f"session:{token}"
            client.setex(key, 3600, json.dumps(session_data))

        print(f"  ✓ {len(sessions)} sessions créées")

        # Feed social de test
        feeds = {
            "user-1-id": ["activity-1"],  # John voit son activité
            "user-2-id": ["activity-2", "activity-1"]  # Sarah voit son activité + celle de John (elle le suit)
        }

        # Feeds (TTL 10 minutes)
        for user_id, activity_ids in feeds.items():
            key = f"feed:{user_id}"
            client.delete(key)  # Nettoyer d'abord
            for activity_id in activity_ids:
                client.lpush(key, activity_id)
            client.expire(key, 600)

        print(f"  ✓ {len(feeds)} feeds sociaux créés")

        # Leaderboard de test (semaine actuelle)
        week = datetime.now().strftime("%Y-W%V")

        leaderboard_key = f"leaderboard:running:{week}"
        leaderboard_data = {
            "user-1-id": 25.5,  # John: 25.5 km cette semaine
            "user-2-id": 15.2   # Sarah: 15.2 km cette semaine
        }

        client.delete(leaderboard_key)
        client.zadd(leaderboard_key, leaderboard_data)
        client.expire(leaderboard_key, 1_209_600)  # 14 jours

        print(f"  ✓ Leaderboard créé pour la semaine {week}")

        # Métriques de performance
        client.set("metrics:cache_hit_rate", "0.95")
        client.set("metrics:response_time_avg", "45")  # ms

        print("  ✓ Métriques de performance définies")

    except Exception as e:
        print(f"❌ Erreur lors de l'insertion des données : {str(e)}")
        return False

    return True


def verify_setup(client):
    """Vérifie que l'installation fonctionne correctement."""
    print("\n[VÉRIFICATION] Test des fonctionnalités...")

    try:
        # Test 1: Informations de base
        version = client.get("sportconnect:version")
        print(f"  ✓ Version SportConnect : {version}")

        # Test 2: Comptage des clés
        profile_keys = len(client.keys("profile:*"))
        session_keys = len(client.keys("session:*"))
        feed_keys = len(client.keys("feed:*"))

        print(f"  ✓ Clés profil : {profile_keys}")
        print(f"  ✓ Clés session : {session_keys}")
        print(f"  ✓ Clés feed : {feed_keys}")

        # Test 3: Récupération d'un profil
        admin_profile = client.get("profile:admin_sportconnect")
        if admin_profile:
            profile_data = json.loads(admin_profile)
            print(f"  ✓ Profil admin récupéré : {profile_data['display_name']}")

        # Test 4: Test du leaderboard
        leaderboard_key = f"leaderboard:running:{datetime.now().strftime('%Y-W%V')}"
        top_users = client.zrevrange(leaderboard_key, 0, 2, withscores=True)
        if top_users:
            print(f"  ✓ Leaderboard : {len(top_users)} utilisateurs")

        # Test 5: Informations Redis
        info = client.info()
        redis_version = info.get('redis_version', 'unknown')
        connected_clients = info.get('connected_clients', 0)
        used_memory = info.get('used_memory_human', 'unknown')

        print(f"  ✓ Redis version : {redis_version}")
        print(f"  ✓ Clients connectés : {connected_clients}")
        print(f"  ✓ Mémoire utilisée : {used_memory}")

    except Exception as e:
        print(f"❌ Erreur lors de la vérification : {str(e)}")
        return False

    return True


def health_check(client):
    """Health check complet de Redis."""
    print("\n[HEALTH CHECK] Tests de performance...")

    try:
        # Test de latence
        import time
        start_time = time.time()
        client.ping()
        latency = (time.time() - start_time) * 1000  # ms
        print(f"  ✓ Latence : {latency:.2f}ms")

        # Test d'écriture/lecture
        test_key = "health_check:test"
        test_value = "OK"

        client.setex(test_key, 10, test_value)
        retrieved_value = client.get(test_key)
        client.delete(test_key)

        if retrieved_value == test_value:
            print("  ✓ Lecture/Écriture : OK")
        else:
            print("  ⚠️  Lecture/Écriture : ÉCHEC")

        # Test des types de données
        # String
        client.set("test:string", "value")
        # Hash
        client.hset("test:hash", "field", "value")
        # List
        client.lpush("test:list", "item")
        # Set
        client.sadd("test:set", "member")
        # Sorted Set
        client.zadd("test:zset", {"member": 1.0})

        # Nettoyer
        for key in ["test:string", "test:hash", "test:list", "test:set", "test:zset"]:
            client.delete(key)

        print("  ✓ Types de données : OK")

    except Exception as e:
        print(f"❌ Erreur health check : {str(e)}")
        return False

    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Redis Setup — SportConnect (Cache & Sessions)")
    print("=" * 60)

    client = get_client()

    try:
        if setup_cache_keys(client):
            if insert_test_data(client):
                if verify_setup(client):
                    health_check(client)
                    print("\n✅ Redis initialisé avec succès!\n")
                else:
                    print("\n⚠️  Redis configuré mais vérification échouée\n")
            else:
                print("\n❌ Échec de l'insertion des données\n")
                sys.exit(1)
        else:
            print("\n❌ Échec de la configuration des clés\n")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Erreur lors de l'initialisation : {e}")
        sys.exit(1)
    finally:
        client.close()
