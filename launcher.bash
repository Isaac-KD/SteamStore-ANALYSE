#!/bin/bash

# ==============================================================================
# --- SECTION DE CONFIGURATION ---
# ==============================================================================

# Nom du script qui collecte les URLs des jeux.
# Il sera lancé à chaque exécution de ce lanceur.
COLLECT_SCRIPT="collect_urls_games.py"

# Nom du script qui traite les lots de jeux.
SCRAPPER_SCRIPT="SteamScraper.py"

# Chemin vers le fichier JSON contenant les URLs des jeux.
# IMPORTANT: Ce fichier sera supprimé au début du script pour forcer
# une nouvelle collecte à chaque exécution.
SOURCE_URL_FILE="data_collected/steam_indie_games_final_api.json"

# Nombre total de fois où vous voulez lancer le script de scraping.
NOMBRE_DE_LANCEMENTS=2000

# Durée de la pause entre chaque lancement du scraper, en secondes.
PAUSE_EN_SECONDES=40

# Interpréteur Python à utiliser ('python' ou 'python3')
PYTHON_CMD="python3"

# ==============================================================================
# --- CŒUR DU SCRIPT ---
# ==============================================================================

echo "==================================================="
echo "  Lanceur de Scraper - Processus Complet"
echo "==================================================="

# --- ÉTAPE 1 : Nettoyage et Collecte des URLs ---
echo ""
echo "--- ÉTAPE 1 : Préparation et Lancement de la collecte des URLs ---"

# On vérifie si le fichier JSON source existe et on le supprime pour forcer une nouvelle collecte.
if [ -f "$SOURCE_URL_FILE" ]; then
    echo "Fichier d'URLs source '$SOURCE_URL_FILE' existant trouvé. Suppression pour forcer la mise à jour..."
    rm "$SOURCE_URL_FILE"
    if [ $? -eq 0 ]; then
        echo "Fichier supprimé avec succès."
    else
        echo "❌ ERREUR : Impossible de supprimer le fichier '$SOURCE_URL_FILE'."
        echo "Veuillez vérifier les permissions du dossier et du fichier."
        exit 1
    fi
else
    echo "Aucun fichier d'URLs source existant. Une nouvelle collecte sera lancée."
fi

echo ""
echo "Lancement de la collecte des URLs via : $PYTHON_CMD $COLLECT_SCRIPT"
echo "---------------------------------------------------"

$PYTHON_CMD "$COLLECT_SCRIPT"

# On vérifie si le script de collecte a réussi.
# '$?' contient le code de sortie de la dernière commande. 0 = succès.
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ ERREUR : Le script '$COLLECT_SCRIPT' a échoué."
    echo "Le processus est arrêté. Veuillez corriger l'erreur avant de relancer."
    exit 1
fi

echo ""
echo "✅ La collecte des URLs est terminée avec succès."
echo "==================================================="


# --- ÉTAPE 2 : Lancement du scraping en boucle ---
echo ""
echo "--- ÉTAPE 2 : Démarrage du scraping en boucle ---"
echo "Le script '$SCRAPPER_SCRIPT' sera lancé $NOMBRE_DE_LANCEMENTS fois."
echo "Pause entre les lancements : $PAUSE_EN_SECONDES secondes."
echo "---------------------------------------------------"

# Boucle pour lancer le script le nombre de fois défini
for (( i=1; i<=$NOMBRE_DE_LANCEMENTS; i++ ))
do
    echo "[LANCEMENT DU LOT N°$i / $NOMBRE_DE_LANCEMENTS] - $(date)"

    # Exécute le script de scraping
    $PYTHON_CMD "$SCRAPPER_SCRIPT"
    
    # Vérifie si c'était le dernier lancement pour ne pas faire de pause inutile
    if [ $i -lt $NOMBRE_DE_LANCEMENTS ]; then
        echo "---------------------------------------------------"
        echo "✅ Lot N°$i terminé."
        echo "⏳ PAUSE de $PAUSE_EN_SECONDES secondes avant le prochain lot..."
        sleep $PAUSE_EN_SECONDES
        echo "---------------------------------------------------"
    fi
done

echo ""
echo "==================================================="
echo "🎉 Tous les $NOMBRE_DE_LANCEMENTS lots sont terminés."
echo "==================================================="

