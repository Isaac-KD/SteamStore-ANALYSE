#!/bin/bash

# ==============================================================================
# --- LANCEUR INTELLIGENT ET GARDIEN DE SCRAPER ---
# ==============================================================================
# Ce script orchestre tout le processus de scraping :
# 1. PRÉPARATION : Il vérifie si les URLs des jeux ont déjà été collectées.
#    - Si non, il lance le script de collecte (`collect_urls_games.py`).
# 2. SURVEILLANCE : Il lance le scraper principal (`scraper_autotune.py`) avec
#    des arguments optimisés et le redémarre automatiquement en cas de crash.
# ==============================================================================

# --- SECTION DE CONFIGURATION ---

# Interpréteur Python à utiliser ('python' ou 'python3').
PYTHON_CMD="python3"

# --- Noms des scripts Python ---
# Le script qui collecte UNIQUEMENT les URLs des jeux.
COLLECTOR_SCRIPT="collect_urls_games.py"
# Le script principal qui scrape les détails de chaque jeu.
SCRAPER_SCRIPT="SteamScraper.py"

# --- Fichiers et Dossiers ---
# Le dossier où toutes les données seront stockées.
DATA_DIR="data_collected"
# Le fichier JSON que le COLLECTOR_SCRIPT doit créer. C'est notre indicateur de préparation.
SOURCE_FILE="$DATA_DIR/steam_indie_games_final_api.json"

# --- Arguments pour le SCRAPER_SCRIPT principal ---
# Ces arguments définissent les limites dans lesquelles le "Gouverneur de Performance"
# va travailler pour trouver la vitesse optimale. Ce sont des valeurs de départ saines.
SCRAPER_ARGS="--min-concurrency 4 \
              --max-concurrency 8 \
              --min-delay 4.0 \
              --max-delay 8.0 \
              --chunk-size 100 \
              --hibernate-minutes 30 \
              --throttle-threshold-pct 8.0"

# Durée en secondes à attendre après un crash avant de relancer.
RESTART_DELAY_SECONDS=30

# Couleurs pour une sortie plus lisible
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Pas de couleur

# --- ÉTAPE 1 : PRÉPARATION ---

echo -e "${BLUE}===================================================${NC}"
echo -e "${BLUE}  LANCEUR DE SCRAPER INTELLIGENT${NC}"
echo -e "${BLUE}===================================================${NC}"

# On vérifie si le fichier source avec toutes les URLs existe déjà.
if [ ! -f "$SOURCE_FILE" ]; then
    echo -e "${YELLOW}[$(date)] - Le fichier source '$SOURCE_FILE' est introuvable.${NC}"
    echo "[$(date)] - Lancement du script de collecte des URLs : '$COLLECTOR_SCRIPT'..."
    echo ""

    # Exécute le script de collecte.
    $PYTHON_CMD "$COLLECTOR_SCRIPT"
    EXIT_CODE=$? # Récupère son code de sortie.

    if [ $EXIT_CODE -ne 0 ]; then
        echo ""
        echo -e "${RED}[$(date)] - Le script de collecte a échoué (code: $EXIT_CODE). Impossible de continuer.${NC}"
        echo -e "${RED}Veuillez corriger les erreurs dans '$COLLECTOR_SCRIPT' avant de relancer.${NC}"
        exit 1 # Arrête tout le processus.
    else
        echo ""
        echo -e "${GREEN}[$(date)] - La collecte des URLs a réussi. Le fichier '$SOURCE_FILE' a été créé.${NC}"
    fi
else
    echo -e "${GREEN}[$(date)] - Le fichier source '$SOURCE_FILE' a été trouvé. Passage direct au scraping.${NC}"
fi


# --- ÉTAPE 2 : SURVEILLANCE (GARDIEN) ---

echo ""
echo -e "${BLUE}===================================================${NC}"
echo -e "${BLUE}  Gardien de Scraper - Lancement du processus${NC}"
echo -e "${BLUE}  Le script '$SCRAPER_SCRIPT' sera redémarré en cas de crash.${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""

while true
do
    echo "[$(date)] - Lancement d'une nouvelle instance du scraper principal..."
    echo "[$(date)] - Arguments utilisés: $SCRAPER_ARGS"
    
    # Exécute le scraper principal avec ses arguments.
    $PYTHON_CMD "$SCRAPER_SCRIPT" $SCRAPER_ARGS
    
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ [$(date)] - Le script a terminé avec succès (code 0). Le travail est fini.${NC}"
        echo "==================================================="
        break # Le travail est terminé, on sort de la boucle.
    else
        echo ""
        echo -e "${RED}⚠️  [$(date)] - Le script a crashé ou s'est terminé avec une erreur (code: $EXIT_CODE).${NC}"
        echo -e "${YELLOW}Le gardien va le relancer dans $RESTART_DELAY_SECONDS secondes...${NC}"
        echo "==================================================="
        sleep $RESTART_DELAY_SECONDS
    fi
done

echo "Processus de surveillance terminé."
