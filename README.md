# Scraper de Données de Jeux Steam

Ce projet fournit un ensemble de scripts robustes et performants pour extraire, structurer, valider et sauvegarder des informations détaillées sur les jeux de la plateforme Steam. Il est conçu pour être à la fois efficace, grâce à l'utilisation de l'asynchronisme, et fiable, en garantissant l'intégrité des données collectées via un schéma de validation strict.

## Fonctionnalités Principales

-   **Scraping Asynchrone :** Utilise `aiohttp` et `asyncio` pour interroger les serveurs de Steam de manière concurrente, offrant des performances élevées pour le traitement de larges listes de jeux.
-   **Extraction de Données Multi-sources :** Collecte les informations depuis l'API officielle de Steam (détails des applications, avis utilisateurs) et les pages HTML du magasin (pour des données complémentaires comme les tags utilisateurs).
-   **Validation Rigoureuse des Données :** Chaque jeu traité est validé par rapport à un schéma JSON (`schema.json`) avant d'être sauvegardé. Cela garantit que toutes les données enregistrées sont complètes, structurées et cohérentes.
-   **Traitement et Écriture par Lots :** Les données sont écrites sur le disque par lots (`batch processing`) pour optimiser les opérations d'entrée/sortie et réduire la charge sur le système.
-   **Logging Configurable :** Le niveau de détail des logs peut être facilement activé ou désactivé, permettant de passer d'un mode de production silencieux à un mode de débogage verbeux.

## Structure du Projet

Le projet est organisé autour de trois fichiers principaux qui séparent clairement les responsabilités :

1.  📄 **`schema.json`**
    -   **Rôle :** Le "contrat" de données du projet.
    -   **Description :** Ce fichier définit la structure, les types de données, les contraintes (par exemple, valeur minimale, format d'URL) et les champs obligatoires pour chaque entrée de jeu. Il est utilisé par le processeur pour valider rigoureusement chaque jeu avant de le considérer comme "valide".

2.  🐍 **`SteamDataExtract.py`**
    -   **Rôle :** Le moteur de traitement et de logique métier.
    -   **Description :** Il contient la classe `SteamDataProcessor` qui orchestre l'extraction des informations depuis les sources brutes (JSON, HTML), leur nettoyage (ex: suppression des balises HTML), leur transformation en un objet de données structuré (`SteamAppData`), leur validation par rapport au schéma, et enfin leur sauvegarde dans les fichiers de sortie.

3.  🐍 **`test_extract.py`**
    -   **Rôle :** Le point d'entrée exécutable du script.
    -   **Description :** Ce script gère le flux global de l'application : il définit la liste des identifiants de jeux (`app_id`) à traiter, configure l'environnement asynchrone, gère la limite de requêtes concurrentes à l'aide d'un sémaphore, et lance les tâches de scraping en parallèle. Il initialise et pilote le `SteamDataProcessor` pour mener à bien le traitement.
  
![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)
