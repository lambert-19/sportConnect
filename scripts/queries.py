"""
SportConnect — Requêtes types pour toutes les fonctionnalités principales
Organisées par domaine fonctionnel.

Usage :
    from scripts.queries import pg_queries, mongo_queries, neo4j_queries, redis_queries
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from pymongo import MongoClient
from neo4j import GraphDatabase
import redis
from elasticsearch import Elasticsearch as ESClient
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision

# ===================================================================
# Connexions (variables d'environnement)
# ===================================================================
PG_URL      = os.getenv("PG_URL")
MONGO_URI   = os.getenv("MONGO_URI")
NEO4J_URI   = os.getenv("NEO4J_URI",   "bolt://localhost:7687")
NEO4J_CREDS = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD"))
REDIS_URL   = os.getenv("REDIS_URL")
ES_HOST     = os.getenv("ES_HOSTS")
INFLUX_URL  = os.getenv("INFLUXDB_URL")
INFLUX_TOKEN= os.getenv("INFLUXDB_TOKEN")
INFLUX_ORG  = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")
GRAFANA_URL = os.getenv("GRAFANA_CLOUD_URL", "https://ibrahima19.grafana.net")

# ===================================================================
# 1. PROFILS UTILISATEUR — PostgreSQL
# ===================================================================

class PGQueries:
    def __init__(self):
        self.conn = psycopg2.connect(PG_URL)
        self.conn.autocommit = False

    def create_user(self, email: str, password: str, username: str, role: str = "user") -> str:
        """Crée un utilisateur avec email chiffré AES-256 et mot de passe bcrypt."""
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (email, email_hash, password_hash, role)
                VALUES (
                    pgp_sym_encrypt(%(email)s, current_setting('app.encryption_key')),
                    %(email_hash)s,
                    crypt(%(password)s, gen_salt('bf', 12))
                )
                RETURNING id;
            """, {"email": email, "email_hash": email_hash, "password": password})
            user_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO user_profiles (user_id, username)
                VALUES (%(user_id)s, %(username)s);
            """, {"user_id": str(user_id), "username": username})

            cur.execute("""
                INSERT INTO audit_log (user_id, action, details)
                VALUES (%(user_id)s, 'login', '{"event": "account_created"}'::jsonb);
            """, {"user_id": str(user_id)})

            self.conn.commit()
            return str(user_id)

    def authenticate_user(self, email: str, password: str) -> Optional[dict]:
        """Authentifie un utilisateur par email + mot de passe."""
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, role, is_active,
                       password_hash = crypt(%(password)s, password_hash) AS password_ok
                FROM users
                WHERE email_hash = %(email_hash)s
                  AND deleted_at IS NULL;
            """, {"email_hash": email_hash, "password": password})
            row = cur.fetchone()
            if row and row["password_ok"] and row["is_active"]:
                return dict(row)
        return None

    def get_profile(self, username: str) -> Optional[dict]:
        """Récupère un profil public par username (insensible à la casse)."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.username, p.display_name, p.bio, p.city, p.country,
                       p.followers_count, p.following_count, p.activities_count,
                       p.avatar_url, p.is_public,
                       ST_AsGeoJSON(p.geolocation) AS geolocation_json
                FROM user_profiles p
                JOIN users u ON u.id = p.user_id
                WHERE lower(p.username) = lower(%(username)s)
                  AND u.deleted_at IS NULL
                  AND p.is_public = TRUE;
            """, {"username": username})
            return cur.fetchone()

    def find_users_nearby(self, lat: float, lng: float, radius_km: float = 50) -> list:
        """Trouve des sportifs à proximité via PostGIS ST_DWithin."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.username, p.display_name, p.city,
                       ST_Distance(p.geolocation, ST_MakePoint(%(lng)s, %(lat)s)::GEOGRAPHY) / 1000 AS distance_km
                FROM user_profiles p
                JOIN users u ON u.id = p.user_id
                WHERE p.is_public = TRUE
                  AND u.deleted_at IS NULL
                  AND ST_DWithin(
                      p.geolocation,
                      ST_MakePoint(%(lng)s, %(lat)s)::GEOGRAPHY,
                      %(radius_m)s
                  )
                ORDER BY distance_km ASC
                LIMIT 20;
            """, {"lat": lat, "lng": lng, "radius_m": radius_km * 1000})
            return cur.fetchall()

    def follow_user(self, follower_id: str, following_id: str) -> bool:
        """Abonne follower_id à following_id."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO follows (follower_id, following_id)
                    VALUES (%(follower_id)s, %(following_id)s)
                    ON CONFLICT DO NOTHING;
                """, {"follower_id": follower_id, "following_id": following_id})
                self.conn.commit()
                return cur.rowcount == 1
        except Exception as e:
            self.conn.rollback()
            raise e

    def add_like(self, user_id: str, activity_id: str):
        """Ajoute un like (idempotent)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO likes (user_id, activity_id)
                VALUES (%(user_id)s, %(activity_id)s)
                ON CONFLICT DO NOTHING;
            """, {"user_id": user_id, "activity_id": activity_id})
            self.conn.commit()

    def add_comment(self, activity_id: str, user_id: str, content: str,
                    parent_id: Optional[int] = None) -> int:
        """Ajoute un commentaire sur une activité."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO comments (activity_id, user_id, content, parent_id)
                VALUES (%(activity_id)s, %(user_id)s, %(content)s, %(parent_id)s)
                RETURNING id;
            """, {"activity_id": activity_id, "user_id": user_id,
                  "content": content, "parent_id": parent_id})
            self.conn.commit()
            return cur.fetchone()[0]

    def get_comments(self, activity_id: str, limit: int = 50) -> list:
        """Récupère les commentaires d'une activité (non supprimés)."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.id, c.content, c.parent_id, c.created_at,
                       p.username, p.avatar_url
                FROM comments c
                JOIN user_profiles p ON p.user_id = c.user_id
                WHERE c.activity_id = %(activity_id)s
                  AND c.is_deleted = FALSE
                ORDER BY c.created_at ASC
                LIMIT %(limit)s;
            """, {"activity_id": activity_id, "limit": limit})
            return cur.fetchall()

    def get_user_notifications(self, user_id: str, unread_only: bool = False) -> list:
        """Récupère les notifications d'un utilisateur."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT n.id, n.type, n.entity_type, n.entity_id, n.is_read, n.created_at,
                       p.username AS sender_username, p.avatar_url AS sender_avatar
                FROM notifications n
                LEFT JOIN user_profiles p ON p.user_id = n.sender_id
                WHERE n.recipient_id = %(user_id)s
                  AND (%(unread_only)s = FALSE OR n.is_read = FALSE)
                ORDER BY n.created_at DESC
                LIMIT 50;
            """, {"user_id": user_id, "unread_only": unread_only})
            return cur.fetchall()

    def gdpr_anonymize_user(self, user_id: str, gdpr_ticket: str):
        """Droit à l'oubli : anonymisation dans PostgreSQL (étape 1 du Saga)."""
        with self.conn.cursor() as cur:
            # Anonymisation email + désactivation
            cur.execute("""
                UPDATE users SET
                    email      = pgp_sym_encrypt(gen_random_uuid()::text,
                                   current_setting('app.encryption_key')),
                    email_hash = encode(sha256(gen_random_uuid()::text::bytea), 'hex'),
                    is_active  = FALSE,
                    deleted_at = NOW()
                WHERE id = %(user_id)s;
            """, {"user_id": user_id})

            # Audit RGPD
            cur.execute("""
                INSERT INTO audit_log (user_id, action, details)
                VALUES (%(user_id)s, 'gdpr_delete',
                        jsonb_build_object('ticket', %(ticket)s, 'step', 'postgresql'));
            """, {"user_id": user_id, "ticket": gdpr_ticket})
            self.conn.commit()
        print(f"  ✓ PostgreSQL : utilisateur {user_id} anonymisé (ticket {gdpr_ticket})")


# ===================================================================
# 2. ACTIVITÉS SPORTIVES — MongoDB
# ===================================================================

class MongoQueries:
    def __init__(self):
        client = MongoClient(MONGO_URI)
        self.db = client["sportconnect"]
        self.activities = self.db["activities"]

    def create_activity(self, user_id: str, activity_type: str, title: str,
                        metrics: dict, start_location: dict = None,
                        splits: list = None, tags: list = None) -> str:
        """Insère une nouvelle activité (source de vérité, étape 1 Saga)."""
        doc = {
            "userId":        user_id,
            "type":          activity_type,
            "title":         title,
            "startedAt":     datetime.now(timezone.utc),
            "metrics":       metrics,
            "startLocation": start_location or {"type": "Point", "coordinates": [0.0, 0.0]},
            "splits":        splits or [],
            "visibility":    "public",
            "likesCount":    0,
            "tags":          tags or [],
            "mediaUrls":     [],
            "deletedAt":     None,
        }
        result = self.activities.insert_one(doc)
        return str(result.inserted_id)

    def get_activity(self, activity_id: str) -> Optional[dict]:
        """Récupère une activité par son ObjectId."""
        from bson import ObjectId
        return self.activities.find_one(
            {"_id": ObjectId(activity_id), "deletedAt": None}
        )

    def get_user_activities(self, user_id: str, limit: int = 20, skip: int = 0) -> list:
        """Activités d'un utilisateur, triées par date décroissante."""
        return list(
            self.activities.find(
                {"userId": user_id, "deletedAt": None},
                sort=[("startedAt", -1)],
                limit=limit, skip=skip,
            )
        )

    def get_feed_activities(self, following_ids: list, limit: int = 20) -> list:
        """Feed social : activités des utilisateurs suivis."""
        since = datetime.now(timezone.utc) - timedelta(days=30)
        return list(
            self.activities.find(
                {
                    "userId": {"$in": following_ids},
                    "visibility": {"$in": ["public", "followers"]},
                    "startedAt": {"$gte": since},
                    "deletedAt": None,
                },
                sort=[("startedAt", -1)],
                limit=limit,
            )
        )

    def get_activities_near(self, lat: float, lng: float, radius_km: float = 10) -> list:
        """Activités dans un rayon géographique (index 2dsphere)."""
        return list(
            self.activities.find({
                "startLocation": {
                    "$near": {
                        "$geometry":    {"type": "Point", "coordinates": [lng, lat]},
                        "$maxDistance": radius_km * 1000,
                    }
                },
                "visibility": "public",
                "deletedAt": None,
            }).limit(20)
        )

    def get_weekly_stats(self, user_id: str, activity_type: str = None) -> dict:
        """Statistiques hebdomadaires via Aggregation Pipeline."""
        since = datetime.now(timezone.utc) - timedelta(days=7)
        match = {"userId": user_id, "startedAt": {"$gte": since}, "deletedAt": None}
        if activity_type:
            match["type"] = activity_type

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id":              "$type",
                "total_activities": {"$sum": 1},
                "total_distance":   {"$sum": "$metrics.distance"},
                "total_duration":   {"$sum": "$metrics.duration"},
                "total_calories":   {"$sum": "$metrics.calories"},
                "avg_heart_rate":   {"$avg": "$metrics.avgHeartRate"},
                "elevation_total":  {"$sum": "$metrics.elevationGain"},
            }},
            {"$sort": {"total_activities": -1}},
        ]
        return list(self.activities.aggregate(pipeline))

    def delete_user_activities(self, user_id: str):
        """Supprime toutes les activités d'un utilisateur (étape 2 Saga RGPD)."""
        result = self.activities.delete_many({"userId": user_id})
        print(f"  ✓ MongoDB : {result.deleted_count} activités supprimées pour {user_id}")


# ===================================================================
# 3. GRAPHE SOCIAL — Neo4j
# ===================================================================

class Neo4jQueries:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_CREDS)

    def ensure_user_node(self, user_id: str, username: str, avatar_url: str = ""):
        """Crée ou met à jour un nœud User dans le graphe."""
        with self.driver.session() as s:
            s.run("""
                MERGE (u:User {id: $id})
                SET u.username = $username, u.avatarUrl = $avatar_url
            """, id=user_id, username=username, avatar_url=avatar_url)

    def create_activity_node(self, activity_id: str, user_id: str,
                             activity_type: str, visibility: str = "public"):
        """Crée un nœud Activity et la relation CREATED (étape 2 Saga)."""
        with self.driver.session() as s:
            s.run("""
                MERGE (a:Activity {id: $activity_id})
                SET a.type = $type, a.visibility = $visibility, a.createdAt = datetime()
                WITH a
                MATCH (u:User {id: $user_id})
                MERGE (u)-[:CREATED {at: datetime()}]->(a)
            """, activity_id=activity_id, user_id=user_id,
                 type=activity_type, visibility=visibility)

    def follow_user(self, follower_id: str, following_id: str):
        """Crée une relation FOLLOWS dans le graphe."""
        with self.driver.session() as s:
            s.run("""
                MATCH (a:User {id: $follower_id}), (b:User {id: $following_id})
                MERGE (a)-[:FOLLOWS {since: datetime()}]->(b)
            """, follower_id=follower_id, following_id=following_id)

    def like_activity(self, user_id: str, activity_id: str):
        """Crée une relation LIKED."""
        with self.driver.session() as s:
            s.run("""
                MATCH (u:User {id: $user_id}), (a:Activity {id: $activity_id})
                MERGE (u)-[:LIKED {at: datetime()}]->(a)
            """, user_id=user_id, activity_id=activity_id)

    def suggest_friends(self, user_id: str, limit: int = 10) -> list:
        """Suggestions d'amis (amis d'amis) — traversée O(k) Neo4j."""
        with self.driver.session() as s:
            result = s.run("""
                MATCH (me:User {id: $userId})-[:FOLLOWS]->(friend)-[:FOLLOWS]->(suggestion)
                WHERE NOT (me)-[:FOLLOWS]->(suggestion) AND suggestion <> me
                RETURN suggestion.id        AS user_id,
                       suggestion.username  AS username,
                       COUNT(DISTINCT friend) AS mutual_count
                ORDER BY mutual_count DESC
                LIMIT $limit
            """, userId=user_id, limit=limit)
            return [dict(r) for r in result]

    def get_following_ids(self, user_id: str) -> list:
        """Retourne la liste des IDs suivis par un utilisateur (pour le feed)."""
        with self.driver.session() as s:
            result = s.run("""
                MATCH (me:User {id: $userId})-[:FOLLOWS]->(f)
                RETURN f.id AS user_id
            """, userId=user_id)
            return [r["user_id"] for r in result]

    def delete_user(self, user_id: str):
        """DETACH DELETE le nœud User et toutes ses relations (étape 3 Saga RGPD)."""
        with self.driver.session() as s:
            s.run("MATCH (u:User {id: $user_id}) DETACH DELETE u", user_id=user_id)
        print(f"  ✓ Neo4j : nœud User {user_id} supprimé avec toutes ses relations")


# ===================================================================
# 4. CACHE ET TEMPS RÉEL — Redis
# ===================================================================

class RedisQueries:
    def __init__(self):
        self.r = redis.from_url(REDIS_URL, decode_responses=True)

    # ---- Profils ----
    def cache_profile(self, username: str, profile_data: dict):
        key = f"profile:{username.lower()}"
        self.r.setex(key, 300, json.dumps(profile_data))         # TTL 5 min

    def get_cached_profile(self, username: str) -> Optional[dict]:
        key = f"profile:{username.lower()}"
        data = self.r.get(key)
        return json.loads(data) if data else None

    # ---- Sessions ----
    def create_session(self, token: str, user_data: dict):
        self.r.setex(f"session:{token}", 3600, json.dumps(user_data))  # TTL 1h

    def get_session(self, token: str) -> Optional[dict]:
        data = self.r.get(f"session:{token}")
        return json.loads(data) if data else None

    def delete_session(self, token: str):
        self.r.delete(f"session:{token}")

    # ---- Feed social ----
    def push_to_feed(self, user_id: str, activity_id: str):
        key = f"feed:{user_id}"
        self.r.lpush(key, activity_id)
        self.r.ltrim(key, 0, 199)                                 # Max 200 entrées
        self.r.expire(key, 600)                                   # TTL 10 min

    def get_feed(self, user_id: str, limit: int = 20) -> list:
        return self.r.lrange(f"feed:{user_id}", 0, limit - 1)

    def invalidate_feed(self, user_id: str):
        self.r.delete(f"feed:{user_id}")

    # ---- Leaderboard ----
    def update_leaderboard(self, sport: str, user_id: str, distance_km: float):
        week = datetime.now(timezone.utc).strftime("%Y-W%V")
        key = f"leaderboard:{sport}:{week}"
        self.r.zadd(key, {user_id: distance_km}, nx=False, gt=True)
        self.r.expire(key, 1_209_600)                             # TTL 14 jours

    def get_leaderboard(self, sport: str, top_n: int = 10) -> list:
        week = datetime.now(timezone.utc).strftime("%Y-W%V")
        key = f"leaderboard:{sport}:{week}"
        return self.r.zrevrange(key, 0, top_n - 1, withscores=True)

    # ---- Likes ----
    def add_like_cache(self, activity_id: str, user_id: str):
        key = f"likes:{activity_id}"
        self.r.sadd(key, user_id)
        self.r.expire(key, 86_400)                                # TTL 24h

    def remove_like_cache(self, activity_id: str, user_id: str):
        self.r.srem(f"likes:{activity_id}", user_id)

    def get_likes_count(self, activity_id: str) -> int:
        return self.r.scard(f"likes:{activity_id}")

    def user_liked(self, activity_id: str, user_id: str) -> bool:
        return self.r.sismember(f"likes:{activity_id}", user_id)

    def delete_user_keys(self, user_id: str):
        """Supprime toutes les clés liées à un utilisateur (Saga RGPD étape 4)."""
        patterns = [f"session:*", f"feed:{user_id}", f"profile:*"]
        for pattern in patterns:
            for key in self.r.scan_iter(pattern):
                self.r.delete(key)
        print(f"  ✓ Redis : clés utilisateur {user_id} supprimées")


# ===================================================================
# 5. CAPTEURS IoT — InfluxDB (écriture + requêtes Flux)
# ===================================================================

class InfluxQueries:
    def __init__(self):
        self.client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    def write_heart_rate(self, user_id: str, activity_id: str, bpm: int, confidence: float = 1.0):
        """Écrit un point de fréquence cardiaque (Line Protocol)."""
        from influxdb_client import Point
        point = (Point("heart_rate")
                 .tag("user_id", user_id)
                 .tag("activity_id", activity_id)
                 .field("bpm", bpm)
                 .field("confidence", confidence))
        self.write_api.write(bucket="sensor_data", record=point)

    def write_gps(self, user_id: str, activity_id: str, lat: float, lng: float, speed: float):
        """Écrit un point GPS."""
        from influxdb_client import Point
        point = (Point("gps_speed")
                 .tag("user_id", user_id)
                 .tag("activity_id", activity_id)
                 .field("speed", speed)
                 .field("lat", lat)
                 .field("lng", lng))
        self.write_api.write(bucket="sensor_data", record=point)

    def get_activity_hr_summary(self, user_id: str, activity_id: str) -> list:
        """Résumé FC d'une activité : min/max/moyenne."""
        flux = f"""
from(bucket: "sensor_data")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "heart_rate"
         and r.user_id == "{user_id}"
         and r.activity_id == "{activity_id}"
         and r._field == "bpm")
  |> reduce(
       identity: {{min: 250.0, max: 0.0, sum: 0.0, count: 0}},
       fn: (r, accumulator) => ({{
           min:   if r._value < accumulator.min then r._value else accumulator.min,
           max:   if r._value > accumulator.max then r._value else accumulator.max,
           sum:   accumulator.sum + r._value,
           count: accumulator.count + 1,
       }})
  )
"""
        return self.query_api.query(flux)

    def get_weekly_hr_trend(self, user_id: str) -> list:
        """Tendance hebdomadaire FC — agrégat horaire depuis sensor_1h."""
        flux = f"""
from(bucket: "sensor_1h")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "aggregated_1h"
         and r.user_id == "{user_id}"
         and r._field == "bpm")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
"""
        return self.query_api.query(flux)

    def delete_user_sensor_data(self, user_id: str):
        """Supprime les données capteurs d'un utilisateur (Saga RGPD étape 6)."""
        delete_api = self.client.delete_api()
        start = "1970-01-01T00:00:00Z"
        stop  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for bucket in ["sensor_data", "sensor_1h", "sensor_daily"]:
            delete_api.delete(start, stop,
                              predicate=f'user_id="{user_id}"',
                              bucket=bucket, org=INFLUX_ORG)
        print(f"  ✓ InfluxDB : données capteurs {user_id} supprimées")


# ===================================================================
# 6. RECHERCHE FULL-TEXT — Elasticsearch
# ===================================================================

class ESQueries:
    def __init__(self):
        self.es = ESClient([ES_HOST])

    def index_activity(self, activity_id: str, user_id: str, activity_type: str,
                       title: str, tags: list, metrics: dict,
                       start_location: dict = None):
        """Indexe une activité pour la recherche (étape 3 Saga)."""
        doc = {
            "userId":        user_id,
            "type":          activity_type,
            "title":         title,
            "startedAt":     datetime.now(timezone.utc).isoformat(),
            "metrics":       metrics,
            "tags":          tags,
            "visibility":    "public",
            "startLocation": start_location,
        }
        self.es.index(index="activities", id=activity_id, document=doc)

    def search_activities(self, query: str, activity_type: str = None,
                          lat: float = None, lng: float = None,
                          radius_km: float = 20, from_: int = 0, size: int = 20) -> dict:
        """Recherche full-text avec filtres type et géographique."""
        must = [{"multi_match": {"query": query, "fields": ["title^2", "tags"], "analyzer": "french_analyzer"}}]
        filter_ = [{"term": {"visibility": "public"}}]
        if activity_type:
            filter_.append({"term": {"type": activity_type}})
        if lat and lng:
            filter_.append({"geo_distance": {"distance": f"{radius_km}km", "startLocation": {"lat": lat, "lon": lng}}})

        body = {"query": {"bool": {"must": must, "filter": filter_}},
                "from": from_, "size": size}
        return self.es.search(index="activities", body=body)

    def autocomplete_users(self, prefix: str, size: int = 5) -> list:
        """Autocomplétion des noms d'utilisateurs dès 2 caractères."""
        body = {
            "query": {"match": {"username.autocomplete": {"query": prefix, "analyzer": "autocomplete_search"}}},
            "size":  size,
            "_source": ["userId", "username", "displayName"],
        }
        res = self.es.search(index="users", body=body)
        return [h["_source"] for h in res["hits"]["hits"]]

    def delete_user_documents(self, user_id: str):
        """Supprime tous les documents ES d'un utilisateur (Saga RGPD étape 5)."""
        for index in ["activities", "users"]:
            self.es.delete_by_query(
                index=index,
                body={"query": {"term": {"userId": user_id}}},
            )
        print(f"  ✓ Elasticsearch : documents {user_id} supprimés")
