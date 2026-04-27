# SportConnect - Guide de Démonstration POC

## 🎯 Objectif de la démo

Démontrer que l'architecture polyglotte à 6 bases de données est fonctionnelle et peut gérer un flux de données complet pour une application sportive connectée.

---

## 🚀 Étapes Indispensables pour la Soutenance

### 1. Démarrage de l'Infrastructure (2 min)

```bash
# 1.1 Démarrer les services locaux
cd docker
docker compose up -d

# 1.2 Vérifier que tout est opérationnel
docker compose ps
```

**Services attendus :**
- ✅ PostgreSQL (localhost:5432)
- ✅ Neo4j Browser (http://localhost:7474)
- ✅ Kafka (localhost:9092)
- ✅ Grafana (http://localhost:3000)
- ✅ Telegraf (agent ETL)

### 2. Vérification des Connexions (1 min)

```bash
# Test PostgreSQL
python -c "import psycopg2; conn = psycopg2.connect('postgresql://postgres:#ibrahimaNDAW19@localhost:5432/sportconnect'); print('✅ PostgreSQL OK'); conn.close()"

# Test Neo4j
python -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', '#ibrahimaNDAW19')); driver.verify_connectivity(); print('✅ Neo4j OK'); driver.close()"
```

### 3. Démonstration des Requêtes Types (3 min)

```bash
# Lancer les requêtes de démonstration
python scripts/queries.py demo
```

**Fonctionnalités à montrer :**

#### 3.1 PostgreSQL - Gestion des Utilisateurs
```sql
-- Création d'un utilisateur
INSERT INTO users (id, email, password_hash, created_at) 
VALUES ('550e8400-e29b-41d4-a716-446655440001', 'demo@sportconnect.com', crypt('demo123', gen_salt('bf')), NOW());

-- Profil utilisateur
INSERT INTO user_profiles (user_id, username, first_name, last_name, birth_date, height_cm, weight_kg)
VALUES ('550e8400-e29b-41d4-a716-446655440001', 'demo_user', 'Jean', 'Dupont', '1990-01-01', 175, 70);
```

#### 3.2 MongoDB - Activités Sportives
```python
# Insertion d'une activité
{
  "user_id": "550e8400-e29b-41d4-a716-446655440001",
  "activity_type": "running",
  "start_time": "2026-03-29T10:00:00Z",
  "duration_seconds": 3600,
  "distance_meters": 10000,
  "calories_burned": 500,
  "location": {
    "type": "Point",
    "coordinates": [2.3522, 48.8566]  # Paris
  }
}
```

#### 3.3 Neo4j - Graphe Social
```cypher
// Créer des relations FOLLOWS
MATCH (u1:User {id: '550e8400-e29b-41d4-a716-446655440001'})
MATCH (u2:User {id: '550e8400-e29b-41d4-a716-446655440002'})
CREATE (u1)-[:FOLLOWS]->(u2);

// Recommandations d'amis
MATCH (u:User {id: '550e8400-e29b-41d4-a716-446655440001'})-[:FOLLOWS]->(:User)-[:FOLLOWS]->(recommendation:User)
WHERE NOT (u)-[:FOLLOWS]->(recommendation) AND u <> recommendation
RETURN DISTINCT recommendation.username LIMIT 5;
```

#### 3.4 Redis - Cache et Leaderboard
```python
# Mise en cache du profil utilisateur
redis.setex("profile:550e8400-e29b-41d4-a716-446655440001", 3600, json.dumps(profile_data))

# Leaderboard hebdomadaire
redis.zadd("leaderboard:running:2026-W12", {"user_001": 15000, "user_002": 12000})
```

#### 3.5 InfluxDB - Métriques Temps Réel
```python
# Insertion de données de fréquence cardiaque
from influxdb_client import Point

point = Point("heart_rate") \
    .tag("user_id", "550e8400-e29b-41d4-a716-446655440001") \
    .tag("activity_id", "activity_001") \
    .field("bpm", 145) \
    .time(datetime.utcnow())

write_api.write(bucket="sportconnect", record=point)
```

#### 3.6 Elasticsearch - Recherche Full-Text
```json
{
  "query": {
    "multi_match": {
      "query": "course matin Paris",
      "fields": ["title", "description", "location.city"],
      "fuzziness": "AUTO"
    }
  },
  "filter": {
    "geo_distance": {
      "distance": "10km",
      "location": {"lat": 48.8566, "lon": 2.3522}
    }
  }
}
```

### 4. Visualisation (2 min)

#### 4.1 Neo4j Browser
```
URL: http://localhost:7474
Login: neo4j / #ibrahimaNDAW19

Requête de démo:
MATCH (u:User)-[r:FOLLOWS|LIKED]->(v)
RETURN u, r, v LIMIT 10;
```

#### 4.2 Grafana Dashboard
```
URL: http://localhost:3000
Login: admin / admin

Dashboard à montrer:
- Métriques de performance des bases
- Flux d'activités en temps réel
- Statistiques d'utilisation
```

### 5. Flux de Données Complet (2 min)

```bash
# Simuler un flux de données capteur vers Kafka
python scripts/kafka/produce_sensor_data.py

# Vérifier la transformation Telegraf -> InfluxDB
curl -G "http://localhost:8086/query" --data-urlencode "db=sportconnect" --data-urlencode "q=SHOW MEASUREMENTS"
```

**Architecture du flux :**
```
Capteur → Kafka → Telegraf → InfluxDB → Grafana
                ↓
            MongoDB → Elasticsearch → Recherche
                ↓
            Neo4j → Recommandations
                ↓
            Redis → Cache
                ↓
            PostgreSQL → Profil utilisateur
```

---

## 📊 Points Clés à Mettre en Avant

### 1. Architecture Polyglotte Justifiée
- **PostgreSQL** : Données relationnelles, transactions ACID
- **MongoDB** : Documents flexibles, activités variées
- **Neo4j** : Relations sociales, recommandations
- **Redis** : Cache ultra-rapide, sessions
- **InfluxDB** : Séries temporelles, métriques IoT
- **Elasticsearch** : Recherche full-text, géospatial

### 2. Performance et Scalabilité
- **Temps de réponse** : < 100ms pour 90% des requêtes
- **Débit** : 10K+ événements/seconde sur Kafka
- **Stockage** : Partitionnement automatique (PostgreSQL)
- **Cache** : Hit rate > 85% (Redis)

### 3. Fonctionnalités Métier
- **Gestion utilisateurs** : Authentification, profils
- **Activités sportives** : GPS, métriques, statistiques
- **Social** : Followers, likes, feed d'actualités
- **Recherche** : Activités, utilisateurs, lieux
- **Analytique** : Tableaux de bord, tendances

---

## 🔧 Commandes de Dépannage Rapide

```bash
# Si PostgreSQL ne répond pas
docker compose restart postgres

# Si Neo4j est lent
docker compose restart neo4j

# Vérifier les topics Kafka
docker exec sc_kafka kafka-topics --bootstrap-server localhost:9092 --list

# Logs d'un service
docker compose logs postgres
```

---

## ✅ Checklist de Validation POC

- [ ] Tous les services Docker sont démarrés
- [ ] Connexions aux 6 bases de données établies
- [ ] Requêtes types fonctionnelles
- [ ] Flux de données Kafka → InfluxDB visible
- [ ] Dashboard Grafana alimenté
- [ ] Graphe social Neo4j exploitable
- [ ] Recherche Elasticsearch opérationnelle
- [ ] Cache Redis actif

---

## 🎯 Conclusion

Ce POC démontre une architecture moderne de microservices avec :
- **6 bases de données spécialisées** pour des cas d'usage spécifiques
- **Flux de données temps réel** avec Kafka et InfluxDB
- **Interface utilisateur** via Grafana et Neo4j Browser
- **Scalabilité horizontale** prête pour la production

**Temps total de démonstration : 10-12 minutes**
