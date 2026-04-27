# Présentation SportConnect

---

## 🏃‍♂️ SportConnect - Plateforme Sportive Connectée

### Architecture Polyglotte · 6 Bases de Données · Microservices

---

## 📋 Sommaire

1. **Vision du Projet**
2. **Architecture Technique**
3. **Les 6 Bases de Données**
4. **Fonctionnalités Clés**
5. **Démonstration Live**
6. **Métriques & Performance**
7. **Déploiement Production**
8. **Questions**

---

## 🎯 Vision du Projet

### Problématique
- **Fragmentation** des applications sportives actuelles
- **Silos de données** entre activités, social, et analytique
- **Performance** limitée par les architectures monolithiques

### Solution SportConnect
- **Plateforme unifiée** pour tous les sports
- **Architecture microservices** avec bases de données spécialisées
- **Expérience utilisateur** fluide et personnalisée

---

## 🏗️ Architecture Technique

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Applications  │    │   Mobile/Web    │    │   IoT Capteurs  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │     Kafka       │ ← Bus d'événements
                    └─────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │     MongoDB     │    │     Neo4j       │
│  Utilisateurs   │    │   Activités     │    │   Social Graph  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Redis       │    │   InfluxDB      │    │ Elasticsearch   │
│     Cache       │    │  Time Series    │    │    Recherche     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🗄️ Les 6 Bases de Données

### 1. PostgreSQL - Le Cœur Relationnel
- **Rôle** : Profils utilisateurs, authentification, transactions
- **Force** : ACID, contraintes, partitionnement automatique
- **Tables** : 7 tables principales avec RLS (Row Level Security)

### 2. MongoDB - Documents Flexibles
- **Rôle** : Activités sportives diversifiées
- **Force** : Schéma flexible, géospatial, agrégations
- **Collections** : Activités, stats, équipements

### 3. Neo4j - Graphe Social
- **Rôle** : Relations followers/likes, recommandations
- **Force** : Traversals O(k), suggestions d'amis
- **Nœuds** : Users, Activities, Locations

### 4. Redis - Cache Ultra-Rapide
- **Rôle** : Sessions, leaderboard, feed temporaire
- **Force** : < 1ms response time, 85%+ hit rate
- **Structures** : Strings, Sets, Sorted Sets

### 5. InfluxDB - Séries Temporelles
- **Rôle** : Métriques IoT, fréquence cardiaque, GPS
- **Force** : Compression native, rétention automatique
- **Buckets** : 90j, 1an, 5ans avec down-sampling

### 6. Elasticsearch - Moteur de Recherche
- **Rôle** : Recherche full-text, géospatial, autocomplétion
- **Force** : French analyzer, geo-distance, scoring
- **Index** : Activities, Users, Locations

---

## ⚡ Fonctionnalités Clés

### 🏃‍♂️ Gestion Sportive
- **Tracking GPS** en temps réel
- **Métriques santé** (FC, calories, altitude)
- **Statistiques** personnelles et comparatives
- **Défis** et objectifs personnalisés

### 👥 Social & Communauté
- **Feed d'actualités** personnalisé
- **Système de followers** et likes
- **Recommandations** d'amis et d'activités
- **Commentaires** et partages

### 🔍 Recherche & Découverte
- **Recherche full-text** multilingue
- **Filtres géospatiaux** (proximité 10km)
- **Autocomplétion** intelligente
- **Recommandations** basées sur le profil

### 📊 Analytique & Monitoring
- **Tableaux de bord** temps réel
- **Tendances** et statistiques
- **Alertes** personnalisées
- **Export** des données

---

## 🚀 Démonstration Live

### Étape 1 : Démarrage Infrastructure
```bash
docker compose up -d          # 2 minutes
python scripts/init_all.py     # Initialisation complète
```

### Étape 2 : Flux de Données Complet
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

### Étape 3 : Interfaces de Visualisation
- **Neo4j Browser** : http://localhost:7474
- **Grafana Dashboard** : http://localhost:3000
- **Kafka UI** : Monitoring des topics

---

## 📈 Métriques & Performance

### Temps de Réponse
- **Cache Redis** : < 1ms
- **Requêtes SQL** : < 50ms (indexés)
- **Graphe Neo4j** : < 100ms (traversals)
- **Recherche ES** : < 200ms (full-text)

### Débit
- **Kafka** : 10K+ events/second
- **InfluxDB** : 1M+ points/second
- **Concurrent users** : 10K+ (Redis)

### Stockage & Scalabilité
- **Partitionnement** automatique PostgreSQL
- **Sharding** MongoDB horizontal
- **Réplication** multi-zones
- **Backup** quotidien vers GCS

---
---

## 7. Système de Backup & Sauvegarde

### Architecture de Backup
```
Bases de Données locales
         |
    Scripts Python (backup.py)
         |
    Compression & Chiffrement
         |
    Google Cloud Storage (GCS)
         |
    Rétention automatique
```

### Stratégie de Backup Complète
- **PostgreSQL** : pg_dump quotidien + WAL archiving
- **MongoDB** : mongodump incrémental toutes les 6h
- **Redis** : RDB snapshots + AOF persistence
- **Elasticsearch** : Snapshots automatiques vers GCS
- **InfluxDB** : Backups par bucket selon rétention
- **Neo4j** : Full dumps + incrémentaux

### Commandes de Backup
```bash
# Backup complet de toutes les bases
python scripts/backup/backup.py run-all

# Backup par service
python scripts/backup/backup.py postgres
python scripts/backup/backup.py mongodb

# Vérification des backups
python scripts/backup/backup.py verify --service postgres

# Purge automatique (30 jours)
python scripts/backup/backup.py purge
```

### Rétention & Sécurité
- **30 jours** : Backups quotidiens complets
- **90 jours** : Backups hebdomadaires
- **1 an** : Backups mensuels compressés
- **Chiffrement** AES-256 au repos
- **Géoredondance** : Multi-régions GCP

---

## 8. Monitoring & Visualisation Grafana

### Dashboard Grafana Cloud
**URL** : https://ibrahima19.grafana.net

### Métriques Surveillées
- **Infrastructure** : CPU, RAM, Disk, Network
- **Bases de données** : Connections, requêtes, latence
- **Kafka** : Throughput, lag, partitions
- **Application** : Temps de réponse, erreurs, utilisateurs

### Alertes Configurées (7 niveaux)
| Service       | Métrique               | WARNING      | CRITICAL      |
|---------------|------------------------|--------------|---------------|
| PostgreSQL    | Lag réplication        | 10 Mo        | 100 Mo        |
| PostgreSQL    | Connexions actives     | 150/200      | 180/200       |
| MongoDB       | Opérations en attente  | 100          | 500           |
| Redis         | Cache hit rate         | < 85%        | < 70%         |
| InfluxDB      | Latence écriture       | 50 ms        | 200 ms        |
| Kafka         | Consumer lag           | 10 000 msgs  | 100 000 msgs  |
| Elasticsearch | Heap JVM               | 75%          | 90%           |

### Visualisations Temps Réel
- **Flux d'activités** par minute
- **Métriques santé** (FC, calories)
- **Graphe social** : nouveaux followers/likes
- **Performance** : temps de réponse par service
- **Utilisateurs actifs** en direct

### Health Checks Automatisés
```bash
# Vérification complète de l'infrastructure
python scripts/admin/admin.py health-check

# Monitoring Redis détaillé
python scripts/admin/admin.py redis-report

# Audit de cohérence inter-bases
python scripts/admin/admin.py check-consistency
```

---

## 9. Déploiement Production

## ☁️ Déploiement Production

### Infrastructure GCP
- **PostgreSQL** → Cloud SQL for PostgreSQL 16
- **MongoDB** → MongoDB Atlas on GCP
- **Neo4j** → Neo4j AuraDB
- **InfluxDB** → InfluxDB Cloud Serverless
- **Redis** → Memorystore Standard Tier
- **Kafka** → MSK (Managed Streaming for Kafka)
- **Elasticsearch** → Elastic Cloud on GCP

### Sécurité & Monitoring
- **GCP Secret Manager** + Workload Identity
- **Grafana Cloud** pour le monitoring
- **Alertes** configurées (7 niveaux)
- **RGPD** : droit à l'oubli sur toutes les bases

---

## 🎯 Points Différentiants

### Innovation Technique
- **Architecture polyglotte** justifiée par les cas d'usage
- **Flux temps réel** de bout en bout
- **Scalabilité** horizontale native

### Expérience Utilisateur
- **Performance** sub-100ms pour 90% des requêtes
- **Personnalisation** basée sur l'IA
- **Disponibilité** 99.9% avec redondance

### Ouverture & Extensibilité
- **API REST** pour tous les services
- **Webhooks** pour les intégrations
- **Export** des données personnelles

---

## 📊 Résultats Attendus

### Métriques Business
- **Engagement** +40% vs applications monolithes
- **Rétention** +25% à 6 mois
- **Performance** 5x plus rapide

### Métriques Techniques
- **Disponibilité** 99.9%
- **Temps de réponse** < 100ms (P90)
- **Scalabilité** 10K+ utilisateurs concurrents

---

## 🤝 Questions & Discussion

### Points à Discuter
- **Complexité** vs bénéfices de l'architecture polyglotte
- **Coûts** infrastructure et maintenance
- **Évolution** vers l'IA et le machine learning
- **Intégrations** avec wearables et applications tierces

### Prochaines Étapes
- **Beta testing** avec 1000 utilisateurs
- **Mobile apps** iOS/Android natives
- **Partenariats** avec équipementiers sportifs
- **Internationalisation** multilingue

---

## 📱 Contact & Ressources

- **Code source** : GitHub (privé)
- **Documentation** : `/docs`
- **Demo** : Disponible sur demande
- **Contact** : ibrahima.ndaw@example.com

---

**Merci pour votre attention !**

*SportConnect - Connecter les sportifs, unifier les données*
