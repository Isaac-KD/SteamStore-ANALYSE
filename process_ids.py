import json
import os

# --- CONFIGURATION DES CHEMINS ---
# Il est préférable de définir les chemins en haut du script pour les modifier facilement.
DATA_DIR = 'data_collected'
ALL_IDS_FILE = os.path.join(DATA_DIR, 'all_app_ids.txt')
DETAILED_FILE = os.path.join(DATA_DIR, 'steam_indie_games_detailed.jsonl')
ERRORS_FILE = os.path.join(DATA_DIR, 'steam_indie_games_errors.jsonl')

OUTPUT_FILE_1 = os.path.join(DATA_DIR, 'ids_a_traiter_part1.txt')
OUTPUT_FILE_2 = os.path.join(DATA_DIR, 'ids_a_traiter_part2.txt')


def get_all_ids(filepath):
    """Lit le fichier texte contenant tous les ID et les retourne dans un set."""
    print(f"📖 Lecture de la liste complète des ID depuis '{filepath}'...")
    try:
        with open(filepath, 'r') as f:
            # On utilise un set comprehension pour la performance et l'unicité.
            # int() convertit l'ID en nombre, strip() enlève les espaces/sauts de ligne.
            ids = {int(line.strip()) for line in f if line.strip()}
        print(f"    -> {len(ids)} ID uniques trouvés.")
        return ids
    except FileNotFoundError:
        print(f"❌ ERREUR: Le fichier '{filepath}' est introuvable. Veuillez vérifier le chemin.")
        return set()

def get_processed_ids(filepaths):
    """Lit les fichiers JSONL et extrait les app_id déjà traités."""
    processed_ids = set()
    for filepath in filepaths:
        print(f"📖 Lecture des ID déjà traités depuis '{filepath}'...")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        # On charge chaque ligne comme un objet JSON
                        data = json.loads(line)
                        # On ajoute l'ID au set. On utilise .get() pour éviter une erreur si la clé n'existe pas.
                        app_id = data.get("app_id")
                        if app_id is not None:
                            processed_ids.add(app_id)
                    except json.JSONDecodeError:
                        # Ignore les lignes qui ne sont pas du JSON valide
                        print(f"    -> AVERTISSEMENT: Ligne malformée ignorée dans '{filepath}'")
        except FileNotFoundError:
            print(f"    -> INFO: Le fichier '{filepath}' n'a pas été trouvé, il sera ignoré.")
            continue
    print(f"    -> {len(processed_ids)} ID déjà traités au total.")
    return processed_ids

def main():
    """Fonction principale du script."""
    # 1. Récupérer tous les ID à traiter
    all_ids_set = get_all_ids(ALL_IDS_FILE)
    if not all_ids_set:
        print("Aucun ID de base à traiter. Arrêt du script.")
        return

    # 2. Récupérer tous les ID déjà traités (avec succès ou en erreur)
    processed_ids_set = get_processed_ids([DETAILED_FILE, ERRORS_FILE])

    # 3. Calculer les ID restants (ceux qui ne sont dans aucun des deux fichiers de résultats)
    # L'opération de différence sur les sets est extrêmement rapide.
    untreated_ids = sorted(list(all_ids_set - processed_ids_set))
    
    print(f"\n✅ Calcul terminé : {len(untreated_ids)} ID n'ont pas encore été traités.")

    if not untreated_ids:
        print("Tous les ID ont déjà été traités. Aucun fichier de sortie ne sera créé.")
        return

    # 4. Diviser la liste des ID non traités en deux parties
    split_index = len(untreated_ids) // 2
    part1 = untreated_ids[:split_index]
    part2 = untreated_ids[split_index:]

    # 5. Écrire les deux parties dans des fichiers de sortie
    try:
        # S'assurer que le dossier de sortie existe
        os.makedirs(DATA_DIR, exist_ok=True)
        
        with open(OUTPUT_FILE_1, 'w') as f:
            for app_id in part1:
                f.write(f"{app_id}\n")
        print(f"    -> 📝 Fichier '{OUTPUT_FILE_1}' créé avec {len(part1)} ID.")

        with open(OUTPUT_FILE_2, 'w') as f:
            for app_id in part2:
                f.write(f"{app_id}\n")
        print(f"    -> 📝 Fichier '{OUTPUT_FILE_2}' créé avec {len(part2)} ID.")
        
        print("\n🎉 Opération terminée avec succès !")

    except IOError as e:
        print(f"❌ ERREUR: Impossible d'écrire dans les fichiers de sortie. Erreur: {e}")


# Lancer le script
if __name__ == "__main__":
    main()
