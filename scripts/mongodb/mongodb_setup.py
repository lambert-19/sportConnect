"""
SportConnect — MongoDB 7.0 : Initialisation des collections et index
Usage : python scripts/mongodb/mongodb_setup.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE, IndexModel
from pymongo.errors import CollectionInvalid
from dotenv import load_dotenv

# Absolute path — works regardless of where the script is run from
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise EnvironmentError(
        "MONGO_URI is not set. Check that your .env file exists at the project root "
        "and contains: MONGO_URI=mongodb+srv://..."
    )



def get_db():
    try:
        print(f"Connexion à MongoDB Atlas...")
        # Extract basic info from URI for debugging (without password)
        uri_parts = MONGO_URI.replace("mongodb+srv://", "").split("@")
        if len(uri_parts) > 1:
            print(f"  Cluster: {uri_parts[1].split('/')[0]}")
        
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("[OK] Connexion MongoDB établie")
        return client["sportconnect"]
    except Exception as e:
        print(f"\n[ERREUR] ERREUR DE CONNEXION MONGODB")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print(f"\n[ATTENTION] Vérifiez que:")
        print(f"   1. Les credentials MongoDB Atlas sont corrects")
        print(f"   2. L'utilisateur ndawseri_db_user existe dans Atlas")
        print(f"   3. L'utilisateur a les droits sur la base 'sportconnect'")
        print(f"   4. Votre IP est whitelistée dans Atlas (Network Access)")
        sys.exit(1)




# =============================================================
# Validation JSON Schema pour la collection activities
# =============================================================
ACTIVITY_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["userId", "type", "title", "startedAt", "metrics", "visibility"],
        "properties": {
            "userId": {"bsonType": "string", "description": "UUID PostgreSQL de l'auteur"},
            "type": {
                "bsonType": "string",
                "enum": ["running", "cycling", "swimming", "hiking", "gym", "yoga", "other"],
            },
            "title":      {"bsonType": "string", "maxLength": 150},
            "startedAt":  {"bsonType": "date"},
            "endedAt":    {"bsonType": "date"},
            "metrics": {
                "bsonType": "object",
                "properties": {
                    "distance":     {"bsonType": "double", "minimum": 0},  # km
                    "duration":     {"bsonType": "int",    "minimum": 0},  # secondes
                    "avgSpeed":     {"bsonType": "double", "minimum": 0},
                    "avgHeartRate": {"bsonType": "int",    "minimum": 0, "maximum": 250},
                    "elevationGain": {"bsonType": "double"},
                    "calories":     {"bsonType": "int",    "minimum": 0},
                },
            },
            "startLocation": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type":        {"enum": ["Point"]},
                    "coordinates": {"bsonType": "array", "minItems": 2, "maxItems": 2},
                },
            },
            "splits":     {"bsonType": "array"},
            "visibility": {"enum": ["public", "followers", "private"]},
            "likesCount": {"bsonType": "int", "minimum": 0},
            "tags":       {"bsonType": "array"},
            "mediaUrls":  {"bsonType": "array"},
            "deletedAt":  {"bsonType": ["date", "null"]},
        },
    }
}


def setup_activities(db):
    """Crée la collection activities avec validation et index."""
    try:
        db.create_collection("activities", validator=ACTIVITY_SCHEMA)
        print("  [OK] Collection 'activities' créée avec validation JSON Schema")
    except CollectionInvalid:
        db.command("collMod", "activities", validator=ACTIVITY_SCHEMA)
        print("  [OK] Collection 'activities' — validator mis à jour")

    coll = db["activities"]
    indexes = [
        IndexModel([("userId", ASCENDING), ("startedAt", DESCENDING)], name="idx_user_date"),
        IndexModel([("startedAt", DESCENDING)],                         name="idx_date"),
        IndexModel([("type", ASCENDING), ("startedAt", DESCENDING)],    name="idx_type_date"),
        IndexModel([("visibility", ASCENDING), ("startedAt", DESCENDING)], name="idx_visibility_date"),
        IndexModel([("startLocation", GEOSPHERE)],                      name="idx_geospatial"),
        IndexModel([("tags", ASCENDING)],                               name="idx_tags"),
        IndexModel(
            [("deletedAt", ASCENDING)],
            name="idx_ttl_deleted",
            expireAfterSeconds=7_776_000,  # 90 jours après deletedAt
            sparse=True,
        ),
    ]
    coll.create_indexes(indexes)
    print(f"  [OK] {len(indexes)} index créés sur 'activities'")


def setup_notifications_mongo(db):
    """Collection notifications MongoDB (complément à la table PG)."""
    coll = db["notifications_push"]
    indexes = [
        IndexModel([("userId", ASCENDING), ("createdAt", DESCENDING)], name="idx_user_date"),
        IndexModel(
            [("createdAt", ASCENDING)],
            name="idx_ttl_notif",
            expireAfterSeconds=2_592_000,  # 30 jours TTL automatique
        ),
    ]
    coll.create_indexes(indexes)
    print("  [OK] Collection 'notifications_push' configurée")


def setup_roles(db):
    """Crée les rôles applicatifs MongoDB.

    NOTE : Sur MongoDB Atlas, createUser via le driver est interdit.
    Les utilisateurs doivent être créés dans l'UI Atlas :
      Atlas → Database Access → Add New Database User
      - sc_app_rw    : readWrite sur sportconnect
      - sc_analytics : read sur sportconnect
    Cette fonction est uniquement utile pour une instance locale.
    """
    if "mongodb+srv" in (MONGO_URI or ""):
        print("  ~ setup_roles ignoré : Atlas détecté (gérer les users via l'UI Atlas)")
        return

    for username, role in [("sc_app_rw", "readWrite"), ("sc_analytics", "read")]:
        try:
            db.client["sportconnect"].command(
                "createUser", username,
                pwd=os.getenv("MONGO_PASS"),
                roles=[{"role": role, "db": "sportconnect"}],
            )
            print(f"  [OK] Utilisateur '{username}' créé ({role})")
        except Exception as e:
            print(f"  ~ Utilisateur '{username}' : {e}")


if __name__ == "__main__":
    print("\n=== MongoDB Setup — SportConnect ===")
    db = get_db()
    setup_activities(db)
    setup_notifications_mongo(db)
    setup_roles(db)
    print("\n[OK] MongoDB initialisé avec succès\n")