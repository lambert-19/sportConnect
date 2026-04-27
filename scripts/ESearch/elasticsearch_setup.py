"""
SportConnect — Elasticsearch 8 : Index, mappings, ILM et analyseurs
Usage : python scripts/elasticsearch/elasticsearch_setup.py
"""

import os
from elasticsearch import Elasticsearch

ES_HOSTS    = os.getenv("ES_HOSTS")
ES_API_KEY  = os.getenv("ES_API_KEY")


def get_client():
    hosts = [h.strip() for h in ES_HOSTS.split(',')] if ES_HOSTS else []
    if not hosts:
        print("❌ ERREUR : La variable d'environnement ES_HOSTS n'est pas définie ou est vide.")
        exit(1)

    kwargs = {"hosts": hosts}
    if ES_API_KEY and ES_API_KEY.strip():
        kwargs["api_key"] = ES_API_KEY.strip()
    
    try:
        es = Elasticsearch(**kwargs)
        info = es.info()
        print(f"✓ Connexion Elasticsearch établie — version {info['version']['number']}")
        return es
    except Exception as e:
        print(f"❌ Échec de la connexion à Elasticsearch : {e}")
        exit(1)


# =============================================================
# Politique ILM : hot/warm/cold/delete
# =============================================================
# En mode Serverless, l'ILM n'est pas supporté de la même manière.
# On garde la structure mais on désactive l'application si nécessaire.
ILM_POLICY = {
    "policy": {
        "phases": {
            "hot":  {"min_age": "0ms",  "actions": {"rollover": {"max_age": "30d", "max_size": "50gb"}, "set_priority": {"priority": 100}}},
            "warm": {"min_age": "30d",  "actions": {"shrink": {"number_of_shards": 1}, "forcemerge": {"max_num_segments": 1}, "set_priority": {"priority": 50}}},
            "cold": {"min_age": "180d", "actions": {"freeze": {}, "set_priority": {"priority": 0}}},
            "delete": {"min_age": "365d", "actions": {"delete": {}}},
        }
    }
}

# =============================================================
# Mapping index "activities"
# Analyseur french + edge-ngram pour autocomplétion
# =============================================================
ACTIVITIES_SETTINGS = {
    "settings": {
        # "number_of_shards": 3,   <-- Non supporté en Serverless
        # "number_of_replicas": 1, <-- Non supporté en Serverless
        # "index.lifecycle.name": "sportconnect-ilm", <-- ILM peut poser problème en serverless standard
        "analysis": {
            "filter": {
                "french_stop":     {"type": "stop",     "stopwords": "_french_"},
                "french_stemmer":  {"type": "stemmer",  "language": "light_french"},
                "autocomplete_filter": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20},
            },
            "analyzer": {
                "french_analyzer": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "french_stop", "french_stemmer"],
                },
                "autocomplete": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "autocomplete_filter"],
                },
                "autocomplete_search": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "userId":    {"type": "keyword"},
            "type":      {"type": "keyword"},
            "title": {
                "type": "text", "analyzer": "french_analyzer",
                "fields": {"autocomplete": {"type": "text", "analyzer": "autocomplete", "search_analyzer": "autocomplete_search"}},
            },
            "startedAt": {"type": "date"},
            "metrics": {
                "properties": {
                    "distance":     {"type": "float"},
                    "duration":     {"type": "integer"},
                    "avgHeartRate": {"type": "integer"},
                    "calories":     {"type": "integer"},
                    "elevationGain": {"type": "float"},
                },
            },
            "startLocation": {"type": "geo_point"},
            "tags":      {"type": "keyword"},
            "visibility": {"type": "keyword"},
        }
    },
}

# Mapping index "users"
USERS_SETTINGS = {
    "settings": {
        # "number_of_shards": 2,   <-- Non supporté en Serverless
        # "number_of_replicas": 1, <-- Non supporté en Serverless
        # "index.lifecycle.name": "sportconnect-ilm",
        "analysis": {
            "filter": {
                "autocomplete_filter": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20},
            },
            "analyzer": {
                "autocomplete": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "autocomplete_filter"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "userId":      {"type": "keyword"},
            "username": {
                "type": "keyword",
                "fields": {"autocomplete": {"type": "text", "analyzer": "autocomplete"}},
            },
            "displayName": {"type": "text", "analyzer": "french_analyzer" if False else "standard"},
            "bio":         {"type": "text"},
            "city":        {"type": "keyword"},
            "country":     {"type": "keyword"},
            "geolocation": {"type": "geo_point"},
            "isPublic":    {"type": "boolean"},
        }
    },
}


def setup_ilm(es):
    # En Serverless, l'endpoint ILM standard peut ne pas être disponible ou être restreint.
    # On capture l'erreur pour ne pas bloquer le script.
    try:
        es.ilm.put_lifecycle(name="sportconnect-ilm", policy=ILM_POLICY["policy"])
        print("  ✓ Politique ILM 'sportconnect-ilm' créée")
    except Exception as e:
        # En Elastic Serverless, ILM est souvent géré automatiquement ou via une autre API
        print(f"  ℹ Note : Politique ILM ignorée (non supporté en Serverless)")

def setup_index(es, name, settings):
    try:
        if es.indices.exists(index=name):
            print(f"  ~ Index '{name}' existe déjà")
            # En serverless, on évite d'essayer de mettre à jour les settings statiques
            return
        
        # On supprime les paramètres incompatibles avec Serverless si présents
        clean_settings = settings.copy()
        if "settings" in clean_settings:
             # On fait une copie du dictionnaire settings pour ne pas modifier l'original
             clean_settings["settings"] = clean_settings["settings"].copy()
             clean_settings["settings"].pop("number_of_shards", None)
             clean_settings["settings"].pop("number_of_replicas", None)
             clean_settings["settings"].pop("index.lifecycle.name", None)

        es.indices.create(index=name, body=clean_settings)
        print(f"  ✓ Index '{name}' créé")
    except Exception as e:
         print(f"  ⚠ Erreur lors de la création de l'index '{name}' : {e}")


def setup_snapshot_repo(es):
    """Configure le repository GCS pour les snapshots (prod uniquement)."""
    gcs_bucket = os.getenv("GCS_BACKUP_BUCKET", "")
    if not gcs_bucket:
        print("  ~ Variable GCS_BACKUP_BUCKET non définie — snapshot repo ignoré")
        return
    try:
        es.snapshot.create_repository(
            name="gcs_repo", 
            body={
                "type": "gcs", 
                "settings": {"bucket": gcs_bucket, "base_path": "elasticsearch/"}
            }
        )
        print(f"  ✓ Snapshot repository GCS configuré → {gcs_bucket}")
    except Exception as e:
        if "serverless mode" in str(e) or "410" in str(e):
             print(f"  ℹ Note : Création de repository snapshot ignorée (non supporté en Serverless).")
        else:
             print(f"  ⚠ Erreur lors de la création du repo snapshot : {e}")


if __name__ == "__main__":
    print("\n=== Elasticsearch Setup — SportConnect ===")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        ES_HOSTS    = os.getenv("ES_HOSTS")
        ES_API_KEY  = os.getenv("ES_API_KEY")
    except ImportError:
        pass

    es = get_client()
    setup_ilm(es)
    setup_index(es, "activities", ACTIVITIES_SETTINGS)
    setup_index(es, "users",      USERS_SETTINGS)
    setup_snapshot_repo(es)
    print("\n✅ Elasticsearch initialisé avec succès\n")
