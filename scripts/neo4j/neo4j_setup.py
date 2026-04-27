"""
SportConnect — Neo4j 5 : Initialisation du graphe social
Crée les nœuds et relations pour le réseau social
Usage : python scripts/neo4j/neo4j_setup.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS     = os.getenv("NEO4J_PASS",     "changeme_dev")

def get_driver():
    """Établit une connexion Neo4j."""
    try:
        print(f"Connexion à Neo4j : {NEO4J_URI}...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
        print("[OK] Connexion Neo4j établie")
        return driver
    except ServiceUnavailable as e:
        print(f"\n[ERREUR] ERREUR DE CONNEXION NEO4J")
        print(f"   Message: {str(e)}")
        print(f"\n[ATTENTION] Vérifiez que:")
        print(f"   1. Neo4j est en cours d'exécution sur {NEO4J_URI}")
        print(f"   2. Les identifiants dans .env sont corrects")
        print(f"   3. Neo4j n'est pas en mode read-only")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERREUR] ERREUR : {str(e)}")
        sys.exit(1)


# =============================================================
# Contraintes d'unicité (pour la performance)
# =============================================================
CONSTRAINTS = [
    "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User)     REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT activity_id_unique IF NOT EXISTS FOR (a:Activity) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag)      REQUIRE t.name IS UNIQUE",
]

# =============================================================
# Index pour les requêtes fréquentes
# =============================================================
INDEXES = [
    "CREATE INDEX user_username IF NOT EXISTS FOR (u:User)     ON (u.username)",
    "CREATE INDEX user_created IF NOT EXISTS FOR (u:User)     ON (u.createdAt)",
    "CREATE INDEX activity_type IF NOT EXISTS FOR (a:Activity) ON (a.type)",
    "CREATE INDEX activity_created IF NOT EXISTS FOR (a:Activity) ON (a.createdAt)",
    "CREATE INDEX activity_visibility IF NOT EXISTS FOR (a:Activity) ON (a.visibility)",
]


def setup_schema(driver):
    """Crée les contraintes et index."""
    print("\n[SCHÉMA] Configuration des contraintes et index...")
    
    with driver.session() as session:
        # Contraintes
        for stmt in CONSTRAINTS:
            try:
                session.run(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"  [ATTENTION] {str(e)[:100]}")
        print(f"  [OK] {len(CONSTRAINTS)} contraintes créées/vérifiées")

        # Index
        for stmt in INDEXES:
            try:
                session.run(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"  [ATTENTION] {str(e)[:100]}")
        print(f"  [OK] {len(INDEXES)} index créés/vérifiés")


def insert_test_data(driver):
    """Insère des données de test pour le graphe social."""
    print("\n[DONNÉES] Insertion des nœuds et relations de test...")
    
    with driver.session() as session:
        # Utilisateurs (correspondant à PostgreSQL)
        users = [
            {
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "username": "admin_sportconnect",
                "displayName": "SportConnect Admin"
            },
            {
                "id": "user-1-id",
                "username": "runner_john",
                "displayName": "John Runner"
            },
            {
                "id": "user-2-id",
                "username": "cyclist_sarah",
                "displayName": "Sarah Cyclist"
            }
        ]
        
        # Créer les nœuds User
        for user in users:
            session.run("""
                MERGE (u:User {id: $id})
                SET u.username = $username,
                    u.displayName = $displayName,
                    u.createdAt = datetime()
            """, user)
        
        print(f"  [OK] {len(users)} utilisateurs créés")
        
        # Créer une relation FOLLOWS (john suit sarah)
        session.run("""
            MATCH (follower:User {username: 'runner_john'}),
                  (following:User {username: 'cyclist_sarah'})
            MERGE (follower)-[r:FOLLOWS]->(following)
            SET r.createdAt = datetime()
        """)
        print("  [OK] Relation FOLLOWS créée (runner_john -> cyclist_sarah)")
        
        # Créer des activités de test
        activities = [
            {
                "id": "activity-1",
                "userId": "user-1-id",
                "type": "running",
                "title": "Morning Run in Central Park",
                "createdAt": "2026-03-24T08:00:00Z",
                "visibility": "public"
            },
            {
                "id": "activity-2",
                "userId": "user-2-id",
                "type": "cycling",
                "title": "Weekend Bike Ride",
                "createdAt": "2026-03-23T14:30:00Z",
                "visibility": "public"
            }
        ]
        
        for activity in activities:
            session.run("""
                MERGE (a:Activity {id: $id})
                SET a.type = $type,
                    a.title = $title,
                    a.createdAt = $createdAt,
                    a.visibility = $visibility
                WITH a
                MATCH (u:User {id: $userId})
                MERGE (u)-[r:CREATED]->(a)
            """, activity)
        
        print(f"  [OK] {len(activities)} activités créées")
        
        # Créer des relations LIKED
        session.run("""
            MATCH (u:User {username: 'cyclist_sarah'}),
                  (a:Activity {id: 'activity-1'})
            MERGE (u)-[r:LIKED]->(a)
            SET r.createdAt = datetime()
        """)
        print("  [OK] Relation LIKED créée (cyclist_sarah aime activity-1)")
        
        # Créer des tags
        tags = ["endurance", "cardio", "outdoor"]
        for tag in tags:
            session.run("""
                MERGE (t:Tag {name: $name})
            """, {"name": tag})
        
        print(f"  [OK] {len(tags)} tags créés")
        
        # Associer les tags aux activités
        session.run("""
            MATCH (a:Activity {id: 'activity-1'}),
                  (t:Tag {name: 'endurance'})
            MERGE (a)-[r:TAGGED]->(t)
        """)
        session.run("""
            MATCH (a:Activity {id: 'activity-1'}),
                  (t:Tag {name: 'cardio'})
            MERGE (a)-[r:TAGGED]->(t)
        """)
        print("  [OK] Activités associées aux tags")


def verify_graph(driver):
    """Vérifie la structure du graphe."""
    print("\n[VÉRIFICATION] État du graphe...")
    
    with driver.session() as session:
        # Compter les nœuds
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] as label, count(*) as count
            ORDER BY count DESC
        """)
        
        print("  Nœuds par type:")
        for record in result:
            print(f"    • {record['label']}: {record['count']}")
        
        # Compter les relations
        result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) as relationship, count(*) as count
            ORDER BY count DESC
        """)
        
        print("  Relations par type:")
        for record in result:
            print(f"    • {record['relationship']}: {record['count']}")
        
        # Exemple de requête : followers
        result = session.run("""
            MATCH (follower:User)-[r:FOLLOWS]->(following:User)
            RETURN follower.username as follower, following.username as following
        """)
        
        print("  Graphe de suivi:")
        for record in result:
            print(f"    • {record['follower']} -> {record['following']}")


def health_check(driver):
    """Health check du Neo4j."""
    print("\n[HEALTH CHECK] Tests de fonctionnalité...")
    
    with driver.session() as session:
        try:
            # Test de connectivité
            result = session.run("RETURN 1 as check")
            result.consume()
            print("  [OK] Connectivité : OK")
            
            # Test d'écriture
            session.run("""
                CREATE (n:TestNode {timestamp: datetime()})
                DELETE n
            """)
            print("  [OK] Lectures/Écritures : OK")
            
            # Version de Neo4j
            result = session.run("CALL dbms.components() YIELD versions")
            for record in result:
                versions = record['versions']
                if versions:
                    print(f"  [OK] Neo4j Version : {versions[0]}")
            
        except Exception as e:
            print(f"  [ERREUR] Health check échoué : {str(e)}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Neo4j Setup — SportConnect (Graphe Social)")
    print("=" * 60)
    
    driver = get_driver()
    
    try:
        setup_schema(driver)
        insert_test_data(driver)
        verify_graph(driver)
        health_check(driver)
        print("\n[OK] Neo4j initialisé avec succès!\n")
    except Exception as e:
        print(f"\n[ERREUR] Erreur lors de l'initialisation : {e}")
        sys.exit(1)
    finally:
        driver.close()
