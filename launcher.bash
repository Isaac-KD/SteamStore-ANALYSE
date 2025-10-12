#!/bin/bash

# ==============================================================================
# --- LANCEUR DE SCRAPER ROBUSTE AVEC REDÉMARRAGE AUTOMATIQUE ---
# ==============================================================================
# Ce script agit comme un gardien (watcher). Il lance le scraper Python et le
# surveillera. Si le scraper se termine avec une erreur (crash), ce script
# attendra un court instant puis le relancera automatiquement.
# Si le scraper se termine normalement (code de sortie 0), le gardien
# considérera que le travail est terminé et s'arrêtera.
# ==============================================================================

# --- SECTION DE CONFIGURATION ---

# Nom du script Python de scraping à surveiller.
SCRAPPER_SCRIPT="SteamScraper.py"

# Interpréteur Python à utiliser ('python' ou 'python3').
PYTHON_CMD="python3"

# Durée en secondes à attendre après un crash avant de relancer le script.
# C'est une sécurité pour éviter une boucle de redémarrage infinie si le script
# crashe immédiatement à cause d'une erreur de syntaxe par exemple.
RESTART_DELAY_SECONDS=30

# --- CŒUR DU GARDIEN (WATCHER) ---

echo "==================================================="
echo "  Gardien de Scraper - Lancement du processus"
echo "  Le script '$SCRAPPER_SCRIPT' sera redémarré automatiquement en cas de crash."
echo "==================================================="
echo ""

# On utilise une boucle infinie 'while true' qui ne s'arrêtera
# que lorsque nous le déciderons avec la commande 'break'.
while true
do
    echo "[$(date)] - Lancement d'une nouvelle instance du scraper..."
    
    # Exécute le script de scraping.
    # Le script shell va attendre ici jusqu'à ce que le script Python se termine.
    $PYTHON_CMD "$SCRAPPER_SCRIPT"
    
    # Récupère le code de sortie de la dernière commande exécutée (le script Python).
    # '$?' est une variable spéciale en Bash qui contient ce code.
    EXIT_CODE=$?

    # On vérifie si le code de sortie est 0 (succès).
    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "✅ [$(date)] - Le script a terminé avec succès (code 0). Le travail est fini."
        echo "==================================================="
        break # On sort de la boucle infinie, car la tâche est complétée.
    else
        echo ""
        echo "⚠️  [$(date)] - Le script a crashé ou s'est terminé avec une erreur (code: $EXIT_CODE)."
        echo "Le gardien va le relancer dans $RESTART_DELAY_SECONDS secondes..."
        echo "==================================================="
        sleep $RESTART_DELAY_SECONDS
    fi
done

echo "Processus de surveillance terminé."