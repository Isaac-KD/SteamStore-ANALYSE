import requests
import json
import asyncio
import aiohttp
import os
import logging
from SteamDataExtract import SteamDataProcessor
from tqdm.asyncio import tqdm_asyncio
from typing import Dict, Any, Tuple, Optional

# --- VARIABLES DE CONTRÔLE POUR LES LOGS ---
ACTIVER_LOGS = True
DESACTIVER_LOGS = not ACTIVER_LOGS

HEADERS = {
    'User-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# Augmentation du timeout pour les connexions lentes ou les serveurs surchargés
REQUEST_TIMEOUT = 20
log_level = logging.INFO if ACTIVER_LOGS else logging.CRITICAL + 1
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')


# --- FONCTION AMÉLIORÉE AVEC GESTION DES ERREURS ET DES ESSAIS MULTIPLES ---
async def fetch_with_retries(session: aiohttp.ClientSession, url: str, app_id: int) -> Optional[str]:
    """Tente de récupérer une URL avec plusieurs essais en cas d'erreur serveur (5xx)."""
    max_retries = 3
    base_delay = 2  # secondes
    for attempt in range(max_retries):
        try:
            cookies = {'birthtime': '631152001', 'lastagecheckage': '1-January-1990'}
            async with session.get(url, timeout=REQUEST_TIMEOUT, cookies=cookies) as response:
                if response.status >= 500: # Erreur serveur (500, 503, etc.)
                    logging.warning(f"Serveur inaccessible (code {response.status}) pour l'App ID {app_id}. Tentative {attempt + 1}/{max_retries}...")
                    if attempt + 1 < max_retries:
                        await asyncio.sleep(base_delay * (2 ** attempt)) # Exponential backoff: 2s, 4s, 8s...
                    continue # Passe à la tentative suivante
                
                response.raise_for_status() # Lève une exception pour les autres erreurs HTTP (4xx)
                return await response.text()
                
        except aiohttp.ClientError as e:
            logging.warning(f"Erreur client (aiohttp) pour l'App ID {app_id}: {e}. Tentative {attempt + 1}/{max_retries}.")
        except asyncio.TimeoutError:
            logging.warning(f"Timeout pour l'App ID {app_id}. Tentative {attempt + 1}/{max_retries}.")

        if attempt + 1 < max_retries:
            await asyncio.sleep(base_delay * (2 ** attempt)) # Attente avant le prochain essai

    logging.error(f"Échec de la récupération de l'URL pour l'App ID {app_id} après {max_retries} tentatives.")
    return None


def fetch_steam_api_data(session: requests.Session, app_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=FR&l=french"
    reviews_url = f"https://store.steampowered.com/appreviews/{app_id}?json=1&language=all"
    try:
        details_response = session.get(details_url, timeout=REQUEST_TIMEOUT)
        details_response.raise_for_status()
        reviews_response = session.get(reviews_url, timeout=REQUEST_TIMEOUT)
        reviews_response.raise_for_status()
        details_json = details_response.json()
        reviews_json = reviews_response.json()
        if details_json.get(str(app_id), {}).get('success') and reviews_json.get('success'):
            return details_json, reviews_json
    except requests.exceptions.RequestException as e:
        logging.warning(f"Erreur de requête API pour l'App ID {app_id}: {e}")
    except json.JSONDecodeError as e:
        logging.warning(f"Erreur de décodage JSON pour l'App ID {app_id}: {e}")
    return None, None


async def fetch_store_page_html_async(session: aiohttp.ClientSession, app_id: int) -> Optional[str]:
    url = f"https://store.steampowered.com/app/{app_id}/"
    return await fetch_with_retries(session, url, app_id)


async def process_game(app_id: int, session: aiohttp.ClientSession, processor: SteamDataProcessor, semaphore: asyncio.Semaphore):
    """Télécharge, structure, valide ET déclenche la sauvegarde par lot si nécessaire."""
    async with semaphore:
        try:
            # Petite pause pour être moins agressif
            await asyncio.sleep(0.5) 
            
            req_session = requests.Session()
            details_json, reviews_json = await asyncio.to_thread(fetch_steam_api_data, req_session, app_id)
            store_html = await fetch_store_page_html_async(session, app_id)

            if not all([details_json, reviews_json, store_html]):
                logging.debug(f"Données manquantes pour {app_id}, traitement annulé.")
                return

            structured_data = processor.extract_and_structure_data(app_id, details_json, reviews_json, store_html)
            
            if structured_data:
                processor.process_and_validate_item(structured_data)
                await processor.flush_batches_if_needed()

        except Exception:
            # --- MODIFICATION CLÉ POUR LE DEBUGGING ---
            # Utilise logging.exception pour afficher la trace complète de l'erreur
            logging.exception(f"Une erreur inattendue est survenue lors du traitement de l'App ID {app_id}")


async def main():
    # --- RÉDUCTION DE LA CONCURRENCE POUR ÉVITER LE BLOCAGE IP ---
    CONCURRENCY_LIMIT = 10
    BATCH_SAVE_SIZE = 20 
    OUTPUT_FILENAME = "ma_collection_steam.jsonl"
    SCHEMA_FILENAME = "schema.json"
    INVALID_OUTPUT_FILENAME = "ma_collection_steam_erreurs.jsonl"
    
    all_app_ids = [1091500, 227300, 275850, 578080, 730, 892970, 413150, 1085660, 1172470, 620, 
                   374320, 1245620, 570, 252490, 346110, 440, 230410, 218620, 1623730, 632360,
                   10, 20, 30, 40, 50, 60, 70, 80, 999999999]
    ids_to_process = all_app_ids
    
    if not ids_to_process:
        logging.info("La liste des jeux à traiter est vide.")
        return

    logging.info(f"Lancement du traitement pour {len(ids_to_process)} applications.")

    processor = SteamDataProcessor(
        output_filename=OUTPUT_FILENAME, 
        schema_filename=SCHEMA_FILENAME, 
        invalid_output_filename=INVALID_OUTPUT_FILENAME,
        batch_size=BATCH_SAVE_SIZE,
        enable_logging=False
    )
    
    if not processor.schema:
        logging.error("Traitement arrêté car le schéma n'a pas pu être chargé.")
        return
        
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [process_game(app_id, session, processor, semaphore) for app_id in ids_to_process]
        await tqdm_asyncio.gather(*tasks, desc="Traitement des jeux Steam")

    logging.info("Toutes les tâches de scraping sont terminées. Sauvegarde des données restantes...")
    processor.finalize_processing()
    logging.info("Script terminé.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())