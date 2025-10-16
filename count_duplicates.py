import json
from collections import Counter
import argparse
import os

def count_duplicates_in_jsonl(filepath: str):
    """
    Compte les occurrences de chaque 'app_id' dans un fichier JSONL
    et rapporte les doublons.

    Args:
        filepath (str): Le chemin vers le fichier .jsonl à analyser.
    """
    if not os.path.exists(filepath):
        print(f"Erreur : Le fichier '{filepath}' est introuvable.")
        return

    print(f"Analyse du fichier : {filepath}\n")
    
    # Utilise un Counter pour stocker l'app_id et son nombre d'occurrences
    app_id_counts = Counter()
    line_number = 0

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line_number += 1
                try:
                    # Charge la ligne JSON
                    data = json.loads(line)
                    # Extrait l'app_id (si la clé existe)
                    if 'app_id' in data:
                        app_id_counts[data['app_id']] += 1
                    else:
                        print(f"Avertissement : Clé 'app_id' manquante à la ligne {line_number}")
                except json.JSONDecodeError:
                    print(f"Avertissement : Ligne invalide (non-JSON) à la ligne {line_number}")

    except Exception as e:
        print(f"Une erreur inattendue est survenue : {e}")
        return

    # Filtre pour ne garder que les IDs qui apparaissent plus d'une fois
    duplicates = {app_id: count for app_id, count in app_id_counts.items() if count > 1}

    # --- Rapport Final ---
    if not duplicates:
        print("🎉 Félicitations ! Aucun doublon trouvé.")
        print(f"   {len(app_id_counts)} IDs uniques traités.")
    else:
        print(f"🚨 {len(duplicates)} IDs en double trouvés !")
        print("-" * 30)
        # Trie les doublons par le nombre d'occurrences pour la lisibilité
        sorted_duplicates = sorted(duplicates.items(), key=lambda item: item[1], reverse=True)
        
        for app_id, count in sorted_duplicates:
            print(f"  - App ID: {app_id:<10} | Nombre d'occurrences: {count}")
        
        print("-" * 30)
        total_duplicate_entries = sum(duplicates.values())
        print(f"Nombre total de lignes dupliquées : {total_duplicate_entries}")
        print(f"Nombre total de lignes uniques : {len(app_id_counts)}")


def main():
    """Point d'entrée principal du script."""
    parser = argparse.ArgumentParser(
        description="Un outil pour trouver et compter les doublons basés sur 'app_id' dans un fichier JSONL.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "filepath", 
        type=str, 
        help="Chemin vers votre fichier .jsonl.\nExemple: data_collected/steam_indie_games_detailed.jsonl"
    )
    args = parser.parse_args()
    
    count_duplicates_in_jsonl(args.filepath)

if __name__ == "__main__":
    main()