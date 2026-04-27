"""
SportConnect — InfluxDB 2.7 : Initialisation des buckets et tâches Flux
Crée les buckets pour les métriques temps réel et configure le downsampling
Usage : python scripts/influxdb/influxdb_setup.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.exceptions import InfluxDBError
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

INFLUXDB_URL   = os.getenv("INFLUXDB_URL",   "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "dev-token-changeme")
INFLUXDB_ORG   = os.getenv("INFLUXDB_ORG",   "sportconnect")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sportconnect")

# Durées de rétention en secondes
RETENTION_90D   = 7_776_000    # 90 jours — données brutes capteurs
RETENTION_1Y    = 31_536_000   # 1 an    — agrégats horaires
RETENTION_5Y    = 157_680_000  # 5 ans — agrégats journaliers

# Tâche Flux : downsampling horaire (s'exécute toutes les heures)
FLUX_DOWNSAMPLE_1H = f"""
option task = {{name: "downsample_sensor_1h", every: 1h}}

from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "heart_rate" or r._measurement == "gps_speed")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> set(key: "_measurement", value: "aggregated_1h")
  |> to(bucket: "sensor_1h", org: "{INFLUXDB_ORG}")
"""

# Tâche Flux : downsampling journalier (s'exécute chaque nuit à 01h00)
FLUX_DOWNSAMPLE_DAILY = f"""
option task = {{name: "downsample_sensor_daily", every: 1d, offset: 1h}}

from(bucket: "sensor_1h")
  |> range(start: -1d)
  |> filter(fn: (r) => r._measurement == "aggregated_1h")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> set(key: "_measurement", value: "aggregated_daily")
  |> to(bucket: "sensor_daily", org: "{INFLUXDB_ORG}")
"""

# Tâche Flux : alerte fréquence cardiaque > 190 bpm
FLUX_ALERT_HR = f"""
option task = {{name: "alert_heart_rate", every: 30s}}

from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -1m)
  |> filter(fn: (r) => r._measurement == "heart_rate" and r._field == "bpm")
  |> filter(fn: (r) => r._value > 190.0)
  |> map(fn: (r) => ({{r with _value: string(v: r._value)}}))
  |> to(bucket: "alerts", org: "{INFLUXDB_ORG}")
"""


def get_client():
    """Établit une connexion InfluxDB."""
    try:
        print(f"Connexion à InfluxDB : {INFLUXDB_URL}")
        print(f"  Organisation : {INFLUXDB_ORG}")
        print(f"  Bucket : {INFLUXDB_BUCKET}")
        
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        
        # Test connection with ping instead of health check
        if client.ping():
            print("[OK] Connexion InfluxDB établie")
            return client
        else:
            print("[ERREUR] Ping échoué")
            sys.exit(1)
            
    except Exception as e:
        print(f"[ERREUR] Erreur de connexion InfluxDB : {str(e)}")
        print(f"[ATTENTION]  Configuration actuelle :")
        print(f"   URL: {INFLUXDB_URL}")
        print(f"   Token: {INFLUXDB_TOKEN[:20]}...")
        print(f"   Org: {INFLUXDB_ORG}")
        sys.exit(1)


def setup_buckets(client):
    """Crée les buckets avec rétention automatique."""
    print("\n[BUCKETS] Configuration des buckets...")
    
    try:
        buckets_api = client.buckets_api()
        org = client.organizations_api().find_organizations(org=INFLUXDB_ORG)[0]
        
        buckets = [
            (INFLUXDB_BUCKET, RETENTION_90D,  "Données brutes capteurs (90j)"),
            ("sensor_1h",    RETENTION_1Y,   "Agrégats horaires (1 an)"),
            ("sensor_daily", RETENTION_5Y,   "Agrégats journaliers (5 ans)"),
            ("alerts",       86_400,         "Alertes FC > 190bpm (24h TTL)"),
        ]

        for name, retention_secs, description in buckets:
            try:
                existing = buckets_api.find_bucket_by_name(name)
                if existing:
                    print(f"  ~ Bucket '{name}' existe déjà")
                    continue
                    
                # Créer le bucket avec rétention
                from influxdb_client.client.bucket_api import BucketRetentionRules
                rules = [BucketRetentionRules(type="expire", every_seconds=retention_secs)]
                buckets_api.create_bucket(
                    bucket_name=name, 
                    retention_rules=rules, 
                    org_id=org.id
                )
                print(f"  [OK] Bucket '{name}' créé — rétention {retention_secs//86400}j — {description}")
                
            except Exception as e:
                print(f"  [ATTENTION]  Erreur bucket '{name}' : {str(e)}")
                
    except Exception as e:
        print(f"[ERREUR] Erreur lors de la création des buckets : {str(e)}")
        return False
        
    return True


def setup_tasks(client):
    """Crée les tâches Flux pour le downsampling automatique."""
    print("\n[TÂCHES] Configuration des tâches Flux...")
    
    try:
        tasks_api = client.tasks_api()
        org = client.organizations_api().find_organizations(org=INFLUXDB_ORG)[0]

        tasks = [
            ("downsample_sensor_1h",    FLUX_DOWNSAMPLE_1H),
            ("downsample_sensor_daily", FLUX_DOWNSAMPLE_DAILY),
            ("alert_heart_rate",        FLUX_ALERT_HR),
        ]

        existing_tasks = {t.name for t in tasks_api.find_tasks(org_id=org.id)}
        
        for name, flux in tasks:
            try:
                if name in existing_tasks:
                    print(f"  ~ Tâche '{name}' existe déjà")
                    continue

                tasks_api.create_task_with_flux(flux_script=flux, org_id=org.id)
                print(f"  [OK] Tâche Flux '{name}' créée")
                
            except Exception as e:
                print(f"  [ATTENTION]  Erreur tâche '{name}' : {str(e)}")
                
    except Exception as e:
        print(f"[ERREUR] Erreur lors de la création des tâches : {str(e)}")
        return False
        
    return True


def insert_test_data(client):
    """Insère des données de test pour démonstration."""
    print("\n[DONNÉES] Insertion des données de test...")
    
    try:
        write_api = client.write_api()
        
        # Données de fréquence cardiaque (dernières 24h)
        base_time = datetime.utcnow() - timedelta(hours=24)
        
        for hour in range(24):
            for minute in range(0, 60, 5):  # Toutes les 5 minutes
                timestamp = base_time + timedelta(hours=hour, minutes=minute)
                
                # Fréquence cardiaque simulée (60-180 bpm)
                hr_value = 70 + (hour * 2) + (minute // 10)  # Augmente avec l'effort
                
                point = Point("heart_rate") \
                    .tag("user_id", "user-1-id") \
                    .tag("activity_id", "activity-1") \
                    .field("bpm", float(hr_value)) \
                    .time(timestamp, WritePrecision.S)
                    
                write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        
        # Données GPS (vitesse)
        for hour in range(24):
            for minute in range(0, 60, 10):  # Toutes les 10 minutes
                timestamp = base_time + timedelta(hours=hour, minutes=minute)
                
                # Vitesse simulée (0-25 km/h)
                speed_value = 5 + (hour % 6) + (minute // 20)  # Varie selon l'activité
                
                point = Point("gps_speed") \
                    .tag("user_id", "user-1-id") \
                    .tag("activity_id", "activity-1") \
                    .field("kmh", float(speed_value)) \
                    .time(timestamp, WritePrecision.S)
                    
                write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        
        write_api.close()
        print(f"  [OK] Données de test insérées (24h de métriques)")
        
    except Exception as e:
        print(f"[ERREUR] Erreur lors de l'insertion des données : {str(e)}")
        return False
        
    return True


def verify_setup(client):
    """Vérifie que l'installation fonctionne correctement."""
    print("\n[VÉRIFICATION] Test des fonctionnalités...")
    
    try:
        query_api = client.query_api()
        
        # Test 1: Compter les points de données
        query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "heart_rate")
          |> count()
        '''
        
        result = query_api.query(query=query, org=INFLUXDB_ORG)
        total_points = 0
        for table in result:
            for record in table.records:
                total_points += record.get_value()
        
        print(f"  [OK] Points de données HR : {total_points}")
        
        # Test 2: Vérifier les buckets
        buckets_api = client.buckets_api()
        buckets = buckets_api.find_buckets().buckets
        bucket_names = [b.name for b in buckets if b.name in [INFLUXDB_BUCKET, "sensor_1h", "sensor_daily", "alerts"]]
        print(f"  [OK] Buckets actifs : {len(bucket_names)} ({', '.join(bucket_names)})")
        
        # Test 3: Vérifier les tâches
        tasks_api = client.tasks_api()
        org = client.organizations_api().find_organizations(org=INFLUXDB_ORG)[0]
        tasks = tasks_api.find_tasks(org_id=org.id)
        task_names = [t.name for t in tasks]
        print(f"  [OK] Tâches Flux : {len(task_names)} ({', '.join(task_names)})")
        
    except Exception as e:
        print(f"[ERREUR] Erreur lors de la vérification : {str(e)}")
        return False
        
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  InfluxDB Setup — SportConnect (Métriques Temps Réel)")
    print("=" * 60)
    
    client = get_client()
    
    try:
        if setup_buckets(client):
            if setup_tasks(client):
                insert_test_data(client)
                verify_setup(client)
                print("\n[OK] InfluxDB initialisé avec succès!\n")
            else:
                print("\n[ATTENTION]  InfluxDB partiellement configuré (tâches non créées)\n")
        else:
            print("\n[ERREUR] Échec de l'initialisation InfluxDB\n")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[ERREUR] Erreur lors de l'initialisation : {e}")
        sys.exit(1)
    finally:
        client.close()
