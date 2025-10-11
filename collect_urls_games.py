
import requests
from bs4 import BeautifulSoup
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# --- Configuration ---
# L'URL de l'API "cachée" de Steam pour la recherche
API_URL = "https://store.steampowered.com/search/results?tags=492&ndl=1"

# Paramètres de base pour la requête à l'API
PARAMS = {
    'tagid': '492',      # L'ID du tag "Indie"
    'count': 50,         # Nombre de jeux à récupérer par requête
    'infinite': '1',     # Paramètre crucial pour l'API de scroll infini
}

# Nombre de threads sinon le script prend du temps...
MAX_WORKERS = 16

def get_total_games(session):
    """
    Interroge l'API une fois pour obtenir le nombre total de jeux.
    """
    print("Détection du nombre total de jeux via l'API...")
    try:
        api_params = PARAMS.copy()
        api_params['start'] = 0
        api_params['count'] = 1
        
        response = session.get(API_URL, params=api_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            return data.get('total_count', 0)
        return 0
    except Exception as e:
        print(f"Erreur lors de la détection du nombre total de jeux: {e}")
        return 0

def scrape_batch(session, start_index):
    """
    Récupère un lot de jeux à partir d'un index de départ.
    """
    api_params = PARAMS.copy()
    api_params['start'] = start_index
    games_in_batch = []
    
    
    try:
        response = session.get(API_URL, params=api_params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        html_results = data.get('results_html', '')
        soup = BeautifulSoup(html_results, 'lxml')
        game_links = soup.find_all('a', class_='search_result_row')
        
        for link in game_links:
            title_element = link.find('span', class_='title')
            if title_element:
                games_in_batch.append({
                    'Nom': title_element.text.strip(),
                    'URL': link['href']
                })
        return games_in_batch
    except requests.exceptions.RequestException:
        return []

def main():
    """
    Fonction principale pour orchestrer le scraping parallèle via l'API.
    """
    all_games_data = []
    
    with requests.Session() as session:
        total_games = get_total_games(session)
        if not total_games:
            print("Impossible de continuer sans le nombre total de jeux.")
            return
            
        print(f"✅ API contactée : {total_games} jeux au total à récupérer.")
        
        start_indices = range(0, total_games, PARAMS['count'])
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scrape_batch, session, idx) for idx in start_indices]
            
            for future in tqdm(as_completed(futures), total=len(start_indices), desc="Téléchargement des lots de jeux", unit="lot"):
                result = future.result()
                if result:
                    all_games_data.extend(result)

    # Création du DataFrame (utile pour l'affichage et d'éventuelles manipulations)
    df = pd.DataFrame(all_games_data)
    
    # --- MODIFICATION : Sauvegarde en JSON au lieu de CSV ---
    output_filename = 'data_collected/steam_indie_games_final_api.json'
    df.to_json(output_filename, orient='records', indent=4, force_ascii=False)
    
    print(f"\n🎉 Scraping terminé ! {len(df)} jeux sauvegardés dans '{output_filename}'.")

if __name__ == "__main__":
    main()
