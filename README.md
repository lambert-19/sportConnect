# 🏃‍♂️ SportConnect

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Plateforme sportive connectée avec architecture polyglotte et microservices**

SportConnect est une plateforme unifiée pour tous les sports qui utilise une architecture microservices avec 6 bases de données spécialisées pour offrir des performances optimales et une expérience utilisateur fluide.

## 🎯 Vision du Projet

### Problématique
- **Fragmentation** des applications sportives actuelles
- **Silos de données** entre activités, social, et analytique  
- **Performance** limitée par les architectures monolithiques

### Solution SportConnect
- **Plateforme unifiée** pour tous les sports
- **Architecture microservices** avec bases de données spécialisées
- **Expérience utilisateur** fluide et personnalisée

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
│  (Utilisateurs) │    │   (Activités)   │    │   (Social)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    InfluxDB     │    │     Redis       │    │ Elasticsearch   │
│   (Time Series) │    │    (Cache)      │    │   (Recherche)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 💾 Les 6 Bases de Données

| Base de données | Rôle | Cas d'usage |
|----------------|------|-------------|
| **PostgreSQL 16** | Transactionnel | Comptes, authentification, profils, relations |
| **MongoDB 7.0** | Document | Activités sportives, feeds, statistiques |
| **Neo4j 5.19** | Graphe | Réseau social, recommandations, parcours |
| **InfluxDB 2.7** | Time Series | Données capteurs, GPS, fréquence cardiaque |
| **Redis 7** | Cache | Sessions, leaderboards, temps réel |
| **Elasticsearch 8** | Recherche | Full-text, géolocalisation, analytics |

## 🚀 Démarrage Rapide

### Prérequis
- Python 3.9+
- Docker & Docker Compose
- Git

### Installation

```bash
# 1. Cloner le projet
git clone https://github.com/ibrahima19/SportConnect.git
cd SportConnect

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos configurations

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Démarrer tous les services
python scripts/init_all.py

# 5. Vérifier l'installation
python scripts/admin/admin.py health-check
```

### Accès aux Services

| Service | URL | Identifiants |
|---------|-----|--------------|
| PostgreSQL | `localhost:5432` | `postgres:#ibrahimaNDAW19` |
| Neo4j Browser | `http://localhost:7474` | `neo4j:password` |
| InfluxDB UI | `http://localhost:8086` | Token: `dev-token-changeme` |
| Grafana Cloud | `https://ibrahima19.grafana.net` | Voir configuration |

## 📁 Structure du Projet

```
sportconnect/
├── .env                    ← Variables d'environnement
├── requirements.txt        ← Dépendances Python
├── docker/                 ← Configurations Docker
│   ├── docker-compose.yml  ← Stack complète
│   ├── postgres/           ← Config PostgreSQL
│   ├── mongodb/            ← Config MongoDB
│   ├── influxdb/           ← Config InfluxDB
│   ├── redis/              ← Config Redis
│   └── elasticsearch/      ← Config Elasticsearch
└── scripts/                ← Scripts d'administration
    ├── init_all.py         ← Initialisation complète
    ├── queries.py          ← Requêtes types
    ├── sql/                ├── Schéma PostgreSQL
    ├── mongodb/            ← Setup MongoDB
    ├── neo4j/              ← Setup Neo4j
    ├── influxdb/           ← Setup InfluxDB
    ├── elasticsearch/      ← Setup Elasticsearch
    ├── kafka/              ← Setup Kafka
    ├── admin/              ← Administration
    └── backup/             ← Sauvegardes
```

## 🎯 Fonctionnalités Clés

### Gestion des Utilisateurs
- ✅ Création de comptes et authentification
- ✅ Profils personnalisés avec préférences sportives
- ✅ Système de suivi social (follow/unfollow)
- ✅ Gestion des notifications

### Activités Sportives
- ✅ Tracking GPS et fréquence cardiaque
- ✅ Analyse de performance en temps réel
- ✅ Statistiques hebdomadaires et mensuelles
- ✅ Feed social d'activités

### Réseau Social
- ✅ Graphe de relations (Neo4j)
- ✅ Suggestions d'amis intelligentes
- ✅ Likes et commentaires
- ✅ Partage d'activités

### Recherche et Analytics
- ✅ Recherche full-text multilingue
- ✅ Autocomplétion intelligente
- ✅ Géolocalisation d'activités
- ✅ Tableaux de bord analytiques

## 🛠️ Administration

### Health Checks
```bash
# Vérification complète
python scripts/admin/admin.py health-check

# Monitoring détaillé
python scripts/admin/admin.py health-check --verbose
```

### Gestion des Données
```bash
# Audit de cohérence
python scripts/admin/admin.py check-consistency

# Nettoyage automatique
python scripts/admin/admin.py cleanup-notifications

# Droit à l'oubli RGPD
python scripts/admin/admin.py gdpr-delete --user-id "UUID" --ticket "RGPD-XXXX"
```

### Sauvegardes
```bash
# Sauvegarde complète
python scripts/backup/backup.py run-all

# Par service
python scripts/backup/backup.py postgres
python scripts/backup/backup.py mongodb

# Vérification
python scripts/backup/backup.py verify --service postgres
```

## 📊 Métriques et Monitoring

| Service | Métrique | Warning | Critical |
|---------|----------|---------|----------|
| PostgreSQL | Lag réplication | 10 Mo | 100 Mo |
| PostgreSQL | Connexions actives | 150/200 | 180/200 |
| MongoDB | Opérations en attente | 100 | 500 |
| Redis | Cache hit rate | < 85% | < 70% |
| InfluxDB | Latence écriture | 50 ms | 200 ms |
| Kafka | Consumer lag | 10 000 msgs | 100 000 msgs |
| Elasticsearch | Heap JVM | 75% | 90% |

## ☁️ Déploiement Production

### Architecture GCP
- **PostgreSQL** → Cloud SQL for PostgreSQL 16
- **MongoDB** → MongoDB Atlas on GCP (VPC Peering)
- **Neo4j** → Neo4j AuraDB (HTTPS Bolt)
- **InfluxDB** → InfluxDB Cloud Serverless
- **Redis** → Memorystore Standard Tier
- **Kafka** → MSK 3 brokers kafka.m5.large
- **Elasticsearch** → Elastic Cloud on GCP

### Sécurité
- Secrets gérés via **GCP Secret Manager**
- **Workload Identity** pour l'authentification
- **VPC Private** pour les services sensibles
- **IP Allowlists** pour les accès externes

## 🧪 Tests et Qualité

### Validation de l'Architecture
```bash
# Tests de connectivité
python scripts/test_connectivity.py

# Tests de performance
python scripts/benchmark.py

# Validation des schémas
python scripts/validate_schemas.py
```

### Couverture Fonctionnelle
- ✅ Tests unitaires pour chaque service
- ✅ Tests d'intégration end-to-end
- ✅ Tests de charge et performance
- ✅ Tests de sécurité et RGPD

---

**⚡ SportConnect - Connectez votre passion sportive**
