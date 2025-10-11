# Fichier : scrapper.py
# Description : Script autonome qui découvre (si besoin) puis traite les jeux Steam
#               par lots, en gérant les blocages IP via une hibernation.

import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import time
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm_asyncio
from typing import Set, Optional, Dict, Any, Tuple

# --- DÉPENDANCE EXTERNE ---
try:
    from SteamDataExtract import SteamDataProcessor
except ImportError:
    print("ERREUR: Le fichier 'SteamDataExtract.py' est introuvable. Assurez-vous qu'il est dans le même dossier.")
    exit()

# ==============================================================================
# --- CLASSE D'EXCEPTION ---
# ==============================================================================

class IPBannedException(Exception):
    """Exception levée quand notre IP est considérée comme bannie."""
    pass

# ==============================================================================
# --- CLASSE PRINCIPALE DU SCRAPER ---
# ==============================================================================

class SteamScraper:
    """
    Orchestre l'ensemble du processus de scraping, de la découverte des IDs
    au traitement détaillé des jeux, avec une gestion robuste des erreurs et des blocages.
    """
    # --- Configuration du Scraping ---
    ALL_IDS_FILENAME = "data_collected/all_app_ids.txt"
    SOURCE_JSON_FOR_DISCOVERY = "data_collected/steam_indie_games_final_api.json"
    SCRAPE_CHUNK_SIZE = 50

    # --- Stratégie "Anti-Blocage" ---
    SCRAPE_CONCURRENCY = 9
    BASE_PAUSE_MIN = 5
    BASE_PAUSE_MAX = 10
    HIBERNATION_DURATION_MINUTES = 20

    # --- Chemins et Paramètres Techniques ---
    OUTPUT_FILENAME = "data_collected/steam_indie_games_detailed.jsonl"
    SCHEMA_FILENAME = "schema.json"
    INVALID_OUTPUT_FILENAME = "data_collected/steam_indie_games_errors.jsonl"
    BATCH_SAVE_SIZE = SCRAPE_CHUNK_SIZE
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    }
    REQUEST_TIMEOUT = 30
    AGE_GATE_COOKIES = {'birthtime': '631152001', 'lastagecheckage': '1-January-1990'}

    def __init__(self):
        """Initialise le scraper."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        # S'assure que le dossier de sortie existe
        os.makedirs("data_collected", exist_ok=True)

    @staticmethod
    def save_all_ids(ids: Set[int], filename: str):
        logging.info(f"Sauvegarde de {len(ids)} IDs dans '{filename}'...")
        with open(filename, 'w', encoding='utf-8') as f:
            for app_id in sorted(list(ids)): f.write(f"{app_id}\n")

    @staticmethod
    def load_ids(filename: str) -> Set[int]:
        if not os.path.exists(filename): return set()
        with open(filename, 'r', encoding='utf-8') as f:
            ids = {int(line.strip()) for line in f if line.strip().isdigit()}
        logging.info(f"{len(ids)} IDs chargés depuis '{filename}'.")
        return ids

    @staticmethod
    def get_already_processed_ids(filename: str) -> Set[int]:
        processed_ids = set()
        if not os.path.exists(filename): return processed_ids
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'app_id' in data: processed_ids.add(data['app_id'])
                except json.JSONDecodeError: continue
        return processed_ids
    
    @staticmethod
    def is_captcha_page(html_text: str) -> bool:
        return "g-recaptcha" in html_text or "Veuillez vérifier que vous n'êtes pas un robot" in html_text

    async def discover_all_app_ids_from_json(self) -> Set[int]:
        """Lit un fichier JSON pré-généré pour extraire tous les App IDs."""
        logging.info(f"--- PHASE DE DÉCOUVERTE : Lecture depuis '{self.SOURCE_JSON_FOR_DISCOVERY}' ---")
        
        if not os.path.exists(self.SOURCE_JSON_FOR_DISCOVERY):
            logging.error(f"Le fichier source '{self.SOURCE_JSON_FOR_DISCOVERY}' est introuvable.")
            logging.error("Veuillez lancer le script de collecte des URLs d'abord.")
            return set()

        all_ids = set()
        try:
            with open(self.SOURCE_JSON_FOR_DISCOVERY, 'r', encoding='utf-8') as f:
                games_list = json.load(f)
                for game in games_list:
                    if url := game.get("URL"):
                        if match := re.search(r'\/app\/(\d+)\/', url):
                            all_ids.add(int(match.group(1)))
            logging.info(f"--- DÉCOUVERTE TERMINÉE : {len(all_ids)} IDs uniques extraits. ---")
            return all_ids
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Erreur lors de la lecture de '{self.SOURCE_JSON_FOR_DISCOVERY}': {e}")
            return set()

    async def fetch_with_retries(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Effectue une requête web en gérant les erreurs et les blocages."""
        try:
            async with session.get(url, timeout=self.REQUEST_TIMEOUT, cookies=self.AGE_GATE_COOKIES) as response:
                if response.status == 429:
                    logging.warning("Rate Limited (429). Pause forcée de 90 secondes...")
                    await asyncio.sleep(90)
                    # On retente une fois après la pause
                    async with session.get(url, timeout=self.REQUEST_TIMEOUT, cookies=self.AGE_GATE_COOKIES) as retry_response:
                        retry_response.raise_for_status()
                        return await retry_response.text()
                if response.status == 403: raise IPBannedException(f"IP bannie (403) à {url}.")
                response.raise_for_status()
                html = await response.text()
                if self.is_captcha_page(html): raise IPBannedException(f"Page CAPTCHA sur {url}.")
                return html
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.warning(f"Erreur réseau pour {url}: {e}.")
            return None

    async def fetch_steam_api_data_async(self, session: aiohttp.ClientSession, app_id: int) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Récupère les données JSON des APIs Steam pour un jeu."""
        details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=FR&l=french"
        reviews_url = f"https://store.steampowered.com/appreviews/{app_id}?json=1&language=all"
        async def fetch_json(url):
            try:
                async with session.get(url, timeout=self.REQUEST_TIMEOUT) as response:
                    if response.status in [403, 429]: raise IPBannedException(f"IP bannie par API ({response.status})")
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except (aiohttp.ClientError, json.JSONDecodeError): return None
        return await asyncio.gather(fetch_json(details_url), fetch_json(reviews_url))

    async def process_game_details(self, app_id: int, session: aiohttp.ClientSession, processor: SteamDataProcessor, semaphore: asyncio.Semaphore):
        """Worker qui télécharge, structure et valide les données d'un seul jeu."""
        async with semaphore:
            try:
                await asyncio.sleep(random.uniform(self.BASE_PAUSE_MIN, self.BASE_PAUSE_MAX))
                store_html, api_data = await asyncio.gather(
                    self.fetch_with_retries(session, f"https://store.steampowered.com/app/{app_id}/"),
                    self.fetch_steam_api_data_async(session, app_id)
                )
                if not all(api_data or []) or not store_html:
                    logging.warning(f"Données incomplètes pour {app_id}. Annulé.")
                    return
                details_json, reviews_json = api_data
                structured_data = processor.extract_and_structure_data(app_id, details_json, reviews_json, store_html)
                if structured_data:
                    processor.process_and_validate_item(structured_data)
                    await processor.flush_batches_if_needed()
            except IPBannedException: raise
            except Exception: logging.exception(f"Erreur inattendue pour l'App ID {app_id}")

    async def run(self):
        """Orchestre la découverte (si besoin) puis le traitement d'UN SEUL lot."""
        # --- Étape 1 : Préparation des IDs (MODIFIÉ) ---
        # On force la suppression du fichier d'IDs pour garantir un rafraîchissement.
        if os.path.exists(self.ALL_IDS_FILENAME):
            logging.info(f"Suppression de l'ancien fichier '{self.ALL_IDS_FILENAME}' pour forcer le rafraîchissement.")
            try:
                os.remove(self.ALL_IDS_FILENAME)
            except OSError as e:
                logging.error(f"Impossible de supprimer le fichier d'IDs : {e}. Arrêt.")
                return

        # La découverte est maintenant lancée à chaque fois.
        all_ids_to_process = await self.discover_all_app_ids_from_json()
        if all_ids_to_process:
            self.save_all_ids(all_ids_to_process, self.ALL_IDS_FILENAME)
        else:
            logging.error("La découverte n'a renvoyé aucun ID. Arrêt du script.")
            return
        
        processed_ids = self.get_already_processed_ids(self.OUTPUT_FILENAME).union(self.get_already_processed_ids(self.INVALID_OUTPUT_FILENAME))
        remaining_ids_total = sorted(list(all_ids_to_process - processed_ids))
        print(len(remaining_ids_total))
        ids_for_this_run = remaining_ids_total[:self.SCRAPE_CHUNK_SIZE]

        if not ids_for_this_run:
            logging.info("🎉 Tous les jeux ont déjà été traités. Rien à faire."); return

        logging.info(f"--- SESSION DE SCRAPING : Traitement d'un lot de {len(ids_for_this_run)} jeux. ---")
        processor = SteamDataProcessor(
            output_filename=self.OUTPUT_FILENAME, schema_filename=self.SCHEMA_FILENAME,
            invalid_output_filename=self.INVALID_OUTPUT_FILENAME, batch_size=self.BATCH_SAVE_SIZE,
            enable_logging=False
        )
        if not processor.schema: return

        # --- Étape 2 : Boucle de persistance pour terminer le lot ---
        while True:
            current_processed_ids = self.get_already_processed_ids(self.OUTPUT_FILENAME).union(self.get_already_processed_ids(self.INVALID_OUTPUT_FILENAME))
            chunk_left_to_process = [id for id in ids_for_this_run if id not in current_processed_ids]
            if not chunk_left_to_process: break
            
            logging.info(f"Reprise du lot : {len(chunk_left_to_process)}/{len(ids_for_this_run)} jeux restants.")
            
            try:
                semaphore = asyncio.Semaphore(self.SCRAPE_CONCURRENCY)
                async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                    tasks = [self.process_game_details(app_id, session, processor, semaphore) for app_id in chunk_left_to_process]
                    await tqdm_asyncio.gather(*tasks, desc=f"Traitement du lot")
                break
            except IPBannedException as e:
                logging.error(f"🚫 BAN IP DÉTECTÉ : {e}")
                logging.warning(f"Sauvegarde et hibernation pour {self.HIBERNATION_DURATION_MINUTES} minutes.")
                processor.finalize_processing()
                
                hibernation_seconds = self.HIBERNATION_DURATION_MINUTES * 60
                for i in range(hibernation_seconds, 0, -1):
                    print(f"\rReprise dans {i // 60:02d}:{i % 60:02d}...", end="")
                    time.sleep(1)
                print(f"\r{' ' * 40}\r", end="")
                logging.info("Hibernation terminée. Poursuite du lot...")

        # --- Étape 3 : Finalisation ---
        logging.info("Sauvegarde finale de la session...")
        processor.finalize_processing()
        logging.info("✅ Script terminé pour cette session.")

if __name__ == "__main__":
    # Correction pour la compatibilité Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Instanciation et exécution du scraper
    scraper = SteamScraper()
    asyncio.run(scraper.run())
