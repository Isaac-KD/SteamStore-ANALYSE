# Fichier : SteamScraper.py
# Description : Script autonome qui découvre (si besoin) puis traite les jeux Steam
#               par lots de manière continue, en gérant les blocages IP via une 
#               hibernation et des délais dynamiques.

import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import time
from tqdm.asyncio import tqdm_asyncio
from typing import Set, Optional, Dict, Any, Tuple

# --- DÉPENDANCE EXTERNE ---
try:
    # Ce fichier est nécessaire pour le traitement et la validation des données
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
# --- CLASSE POUR LA GESTION DYNAMIQUE DES DÉLAIS ---
# ==============================================================================

class DynamicDelayManager:
    """Gère dynamiquement les temps de pause pour éviter le rate limiting."""
    def __init__(self, min_delay=2.0, max_delay=5.0, increase_factor=1.5, decrease_factor=0.995):
        self.base_min = min_delay
        self.base_max = max_delay
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        logging.info(f"Contrôleur de vitesse initialisé : Délai entre {self.base_min:.2f}s et {self.base_max:.2f}s")

    def get_delay(self) -> float:
        """Retourne une durée de pause aléatoire dans la fourchette actuelle."""
        return random.uniform(self.base_min, self.base_max)

    def record_success(self):
        """Réduit légèrement les délais après une requête réussie."""
        self.base_min = max(1.25, self.base_min * self.decrease_factor) # Ne descend pas sous 1.25s
        self.base_max = max(2, self.base_max * self.decrease_factor) # Ne descend pas sous 2s

    def record_rate_limit(self):
        """Augmente significativement les délais après une erreur de type 429."""
        logging.warning("RATE LIMIT DÉTECTÉ. Augmentation agressive des délais.")
        self.base_min *= self.increase_factor
        self.base_max = self.base_min + random.uniform(2, 5) # Ajoute une variance
        logging.info(f"Nouveaux délais ajustés : entre {self.base_min:.2f}s et {self.base_max:.2f}s")

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
    SCRAPE_CHUNK_SIZE = 50 # Lots plus grands grâce à une meilleure gestion

    # --- Stratégie "Anti-Blocage" ---
    SCRAPE_CONCURRENCY =2 # Moins de requêtes parallèles pour plus de discrétion
    HIBERNATION_DURATION_MINUTES = 30 # Hibernation plus longue en cas de blocage IP

    # --- Chemins et Paramètres Techniques ---
    OUTPUT_FILENAME = "data_collected/steam_indie_games_detailed.jsonl"
    SCHEMA_FILENAME = "schema.json"
    INVALID_OUTPUT_FILENAME = "data_collected/steam_indie_games_errors.jsonl"
    BATCH_SAVE_SIZE = 50 # Sauvegarde des données tous les 50 jeux
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8', # Priorise le français mais accepte l'anglais
    }
    REQUEST_TIMEOUT = 30
    AGE_GATE_COOKIES = {'birthtime': '631152001', 'lastagecheckage': '1-January-1990'}

    def __init__(self):
        """Initialise le scraper."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        os.makedirs("data_collected", exist_ok=True)
        # Instance du gestionnaire de délais dynamiques
        self.delay_manager = DynamicDelayManager(min_delay=3.0, max_delay=7.0)

    @staticmethod
    def save_all_ids(ids: Set[int], filename: str):
        """Sauvegarde un ensemble d'IDs dans un fichier, un par ligne."""
        logging.info(f"Sauvegarde de {len(ids)} IDs dans '{filename}'...")
        with open(filename, 'w', encoding='utf-8') as f:
            for app_id in sorted(list(ids)):
                f.write(f"{app_id}\n")

    @staticmethod
    def load_ids(filename: str) -> Set[int]:
        """Charge les IDs depuis un fichier."""
        if not os.path.exists(filename):
            return set()
        with open(filename, 'r', encoding='utf-8') as f:
            ids = {int(line.strip()) for line in f if line.strip().isdigit()}
        logging.info(f"{len(ids)} IDs chargés depuis '{filename}'.")
        return ids

    @staticmethod
    def get_already_processed_ids(filename: str) -> Set[int]:
        """Lit un fichier .jsonl pour extraire les IDs des jeux déjà traités."""
        processed_ids = set()
        if not os.path.exists(filename):
            return processed_ids
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'app_id' in data:
                        processed_ids.add(data['app_id'])
                except json.JSONDecodeError:
                    continue
        return processed_ids
    
    @staticmethod
    def is_captcha_page(html_text: str) -> bool:
        """Vérifie si le HTML contient une page de CAPTCHA."""
        return "g-recaptcha" in html_text or "Veuillez vérifier que vous n'êtes pas un robot" in html_text

    async def discover_all_app_ids_from_json(self) -> Set[int]:
        """Lit un fichier JSON source pour en extraire tous les App IDs uniques."""
        logging.info(f"--- PHASE DE DÉCOUVERTE : Lecture depuis '{self.SOURCE_JSON_FOR_DISCOVERY}' ---")
        
        if not os.path.exists(self.SOURCE_JSON_FOR_DISCOVERY):
            logging.error(f"Le fichier source '{self.SOURCE_JSON_FOR_DISCOVERY}' est introuvable.")
            logging.error("Veuillez d'abord lancer le script de collecte des URLs.")
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
        """Effectue une requête web avec gestion des erreurs et des limites de taux."""
        try:
            async with session.get(url, timeout=self.REQUEST_TIMEOUT, cookies=self.AGE_GATE_COOKIES) as response:
                if response.status == 429:
                    self.delay_manager.record_rate_limit()
                    logging.warning("Rate Limited (429). Pause forcée de 90 secondes...")
                    await asyncio.sleep(90)
                    # Nouvelle tentative après la pause
                    async with session.get(url, timeout=self.REQUEST_TIMEOUT, cookies=self.AGE_GATE_COOKIES) as retry_response:
                        retry_response.raise_for_status()
                        self.delay_manager.record_success()
                        return await retry_response.text()
                        
                if response.status == 403:
                    raise IPBannedException(f"IP bannie (403) à l'URL {url}.")
                
                response.raise_for_status()
                html = await response.text()
                
                if self.is_captcha_page(html):
                    raise IPBannedException(f"Page CAPTCHA détectée sur {url}.")
                
                self.delay_manager.record_success()
                return html
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.warning(f"Erreur réseau pour {url}: {e}.")
            return None

    async def fetch_steam_api_data_async(self, session: aiohttp.ClientSession, app_id: int) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Récupère les données des deux APIs Steam (détails et avis)."""
        details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=FR&l=french"
        reviews_url = f"https://store.steampowered.com/appreviews/{app_id}?json=1&language=all"
        
        async def fetch_json(url: str, retries: int = 3) -> Optional[Dict]:
            """ Tente de fetch une URL JSON avec une stratégie de retry sur le code 429. """
            for i in range(retries):
                try:
                    async with session.get(url, timeout=self.REQUEST_TIMEOUT) as response:
                        # Cas 1: Succès
                        if response.status == 200:
                            self.delay_manager.record_success()
                            return await response.json(content_type=None)
                        
                        # Cas 2: Rate Limit (Avertissement)
                        elif response.status == 429:
                            self.delay_manager.record_rate_limit()
                            retry_delay = (i + 1) * 30 # Attente croissante : 30s, 60s, 90s
                            logging.warning(f"API Rate Limited (429) sur {url}. Nouvelle tentative dans {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                            continue # On passe à la prochaine itération de la boucle
                        
                        # Cas 3: Bannissement (Grave)
                        elif response.status == 403:
                            raise IPBannedException(f"IP bannie par l'API ({response.status}) sur {url}")
                        
                        # Cas 4: Autre erreur serveur
                        else:
                            logging.warning(f"Erreur inattendue de l'API ({response.status}) sur {url}")
                            return None

                except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as e:
                    logging.warning(f"Erreur réseau/JSON pour {url}: {e}")
                    return None
            
            logging.error(f"Échec de la récupération de {url} après {retries} tentatives.")
            return None

        # Lance les deux requêtes API en parallèle
        return await asyncio.gather(fetch_json(details_url), fetch_json(reviews_url))

    async def process_game_details(self, app_id: int, session: aiohttp.ClientSession, processor: SteamDataProcessor, semaphore: asyncio.Semaphore):
        """Worker qui télécharge, structure et valide les données d'un seul jeu."""
        async with semaphore:
            try:
                # Pause dynamique avant chaque requête
                await asyncio.sleep(self.delay_manager.get_delay())
                
                # Récupère la page du magasin et les données API en parallèle
                store_html, api_data = await asyncio.gather(
                    self.fetch_with_retries(session, f"https://store.steampowered.com/app/{app_id}/"),
                    self.fetch_steam_api_data_async(session, app_id)
                )

                if not all(api_data or []) or not store_html:
                    logging.warning(f"Données incomplètes pour l'App ID {app_id}. Annulation.")
                    return
                
                details_json, reviews_json = api_data
                structured_data = processor.extract_and_structure_data(app_id, details_json, reviews_json, store_html)
                
                if structured_data:
                    processor.process_and_validate_item(structured_data)
                    await processor.flush_batches_if_needed()
            except IPBannedException:
                raise # Propage l'exception pour déclencher l'hibernation
            except Exception:
                logging.exception(f"Erreur inattendue pour l'App ID {app_id}")

    async def run(self):
        """Orchestre le traitement de TOUS les jeux en boucle continue."""
        # --- Étape 1 : Préparation des IDs ---
        if not os.path.exists(self.ALL_IDS_FILENAME):
            logging.info(f"Le fichier '{self.ALL_IDS_FILENAME}' est introuvable. Lancement de la découverte.")
            all_ids = await self.discover_all_app_ids_from_json()
            if all_ids:
                self.save_all_ids(all_ids, self.ALL_IDS_FILENAME)
            else:
                logging.error("La découverte n'a renvoyé aucun ID. Arrêt du script.")
                return
        else:
            all_ids = self.load_ids(self.ALL_IDS_FILENAME)

        processor = SteamDataProcessor(
            output_filename=self.OUTPUT_FILENAME, schema_filename=self.SCHEMA_FILENAME,
            invalid_output_filename=self.INVALID_OUTPUT_FILENAME, batch_size=self.BATCH_SAVE_SIZE,
            enable_logging=True
        )
        if not processor.schema:
            return

        # --- Étape 2 : Boucle principale de scraping ---
        while True:
            processed_ids = self.get_already_processed_ids(self.OUTPUT_FILENAME).union(
                self.get_already_processed_ids(self.INVALID_OUTPUT_FILENAME)
            )
            remaining_ids = sorted(list(all_ids - processed_ids))
            
            if not remaining_ids:
                logging.info("🎉 Tous les jeux ont été traités. Travail terminé.")
                break

            ids_for_this_run = remaining_ids[:self.SCRAPE_CHUNK_SIZE]
            logging.info("--- NOUVELLE SESSION DE SCRAPING ---")
            logging.info(f"{len(remaining_ids)} jeux restants. Traitement d'un lot de {len(ids_for_this_run)}.")
            
            try:
                semaphore = asyncio.Semaphore(self.SCRAPE_CONCURRENCY)
                async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                    tasks = [self.process_game_details(app_id, session, processor, semaphore) for app_id in ids_for_this_run]
                    await tqdm_asyncio.gather(*tasks, desc="Traitement du lot")
                
            except IPBannedException as e:
                logging.error(f"🚫 BAN IP DÉTECTÉ : {e}")
                logging.warning(f"Sauvegarde des données et hibernation pour {self.HIBERNATION_DURATION_MINUTES} minutes.")
                processor.finalize_processing()
                
                hibernation_seconds = self.HIBERNATION_DURATION_MINUTES * 60
                for i in range(hibernation_seconds, 0, -1):
                    print(f"\rReprise dans {i // 60:02d}:{i % 60:02d}...", end="")
                    time.sleep(1)
                print(f"\r{' ' * 40}\r", end="") # Efface la ligne du compte à rebours
                logging.info("Hibernation terminée. Poursuite du scraping...")

        # --- Étape 3 : Finalisation ---
        logging.info("Sauvegarde finale des données restantes...")
        processor.finalize_processing()
        logging.info("✅ Script terminé.")

if __name__ == "__main__":
    # Correction nécessaire pour la compatibilité aiohttp sur Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Instanciation et exécution du scraper
    scraper = SteamScraper()
    asyncio.run(scraper.run())