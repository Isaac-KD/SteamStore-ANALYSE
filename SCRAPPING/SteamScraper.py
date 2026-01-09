# Fichier : scraper_autotune.py
# Description : Un scraper auto-apprenant doté d'un "Gouverneur de Performance"
#               qui cherche et maintient dynamiquement la vitesse de scraping
#               maximale possible en sondant les limites des serveurs Steam.

import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import time
import argparse
from collections import deque
from enum import Enum, auto
from tqdm.asyncio import tqdm_asyncio
from typing import Set, Optional, Dict, Any, Tuple, List

# --- Configuration du Logger ---
logger = logging.getLogger(__name__)

try:
    from SCRAPPING.SteamDataExtract import SteamDataProcessor
except ImportError:
    logger.critical("ERREUR: Le fichier 'SteamDataExtract.py' est introuvable.")
    exit(1)

# ==============================================================================
# --- CLASSES DE CONTRÔLE ET D'EXCEPTION ---
# ==============================================================================

class IPBannedException(Exception): pass

class RequestOutcome(Enum):
    SUCCESS = auto()
    RATE_LIMIT = auto()
    FAILURE = auto()

class GovernorState(Enum):
    OPTIMIZING = auto() # Cherche à accélérer
    THROTTLED = auto()  # A trouvé la limite, se stabilise
    RECOVERING = auto() # Vitesse minimale après un ban

class PerformanceGovernor:
    """Le cerveau du scraper. Apprend et ajuste la vitesse pour une performance maximale."""
    def __init__(self, args):
        self.args = args
        self.state = GovernorState.OPTIMIZING
        
        # Garde l'historique des X derniers résultats
        self.history = deque(maxlen=args.history_size)
        
        # Limites et état de la vitesse
        self.min_concurrency = args.min_concurrency
        self.max_concurrency = args.max_concurrency
        self.min_delay = args.min_delay
        self.max_delay = args.max_delay
        self.current_concurrency = self.min_concurrency
        self.current_delay = (self.min_delay + self.max_delay) / 2 # Commence au milieu

        logger.info("Gouverneur de Performance activé. Prêt à trouver la vitesse optimale.")

    @property
    def status_line(self) -> str:
        """Retourne une ligne de statut lisible."""
        stats = {outcome: self.history.count(outcome) for outcome in RequestOutcome}
        rate_limit_pct = (stats.get(RequestOutcome.RATE_LIMIT, 0) / len(self.history) * 100) if self.history else 0
        return (f"État: {self.state.name} | "
                f"Concurrence: {self.get_concurrency()} | "
                f"Délai: ~{self.current_delay:.2f}s | "
                f"Taux 429 (récent): {rate_limit_pct:.1f}%")

    def get_concurrency(self) -> int: return int(self.current_concurrency)
    def get_delay(self) -> float: return self.current_delay * random.uniform(0.8, 1.2)

    def record_outcome(self, outcome: RequestOutcome):
        """Enregistre le résultat d'une requête."""
        self.history.append(outcome)

    def assess_and_adjust(self):
        """Analyse l'historique récent et ajuste la stratégie de vitesse."""
        if len(self.history) < self.args.history_size / 2:
            return # Attend d'avoir assez de données

        rate_limit_pct = self.history.count(RequestOutcome.RATE_LIMIT) / len(self.history)

        # --- Logique de changement d'état ---
        if self.state == GovernorState.OPTIMIZING and rate_limit_pct > self.args.throttle_threshold_pct / 100:
            self.state = GovernorState.THROTTLED
            logger.warning(f"Seuil de Rate Limit dépassé ({rate_limit_pct:.1f}%). Passage en mode THROTTLED.")
        elif self.state == GovernorState.THROTTLED and rate_limit_pct < self.args.throttle_threshold_pct / 100:
            self.state = GovernorState.OPTIMIZING
            logger.info("Taux de Rate Limit stabilisé. Retour en mode OPTIMIZING.")

        # --- Logique d'ajustement de la vitesse ---
        if self.state == GovernorState.OPTIMIZING:
            # Accélère agressivement
            self.current_delay = max(self.min_delay, self.current_delay * 0.95)
            if self.current_delay == self.min_delay:
                self.current_concurrency = min(self.max_concurrency, self.current_concurrency + 0.5) # Augmente doucement
        
        elif self.state == GovernorState.THROTTLED:
            # Ralentit pour se stabiliser juste sous la limite
            self.current_concurrency = max(self.min_concurrency, self.current_concurrency * 0.9)
            self.current_delay = min(self.max_delay, self.current_delay * 1.1)

        elif self.state == GovernorState.RECOVERING:
            # N'accélère que si le taux d'erreur est absolument nul
            if rate_limit_pct == 0:
                self.state = GovernorState.OPTIMIZING
                logger.info("Récupération terminée. Reprise de l'optimisation.")

    def reset_after_ban(self):
        """Réinitialisation d'urgence après une hibernation."""
        self.state = GovernorState.RECOVERING
        self.current_concurrency = self.min_concurrency
        self.current_delay = self.max_delay
        self.history.clear()
        logger.critical("HIBERNATION TERMINÉE. Passage en mode RECOVERING à vitesse minimale.")

# ==============================================================================
# --- CLASSE PRINCIPALE DU SCRAPER ---
# ==============================================================================

class SteamScraper:
    def __init__(self, args):
        self.args = args
        self.governor = PerformanceGovernor(args)
        self.processor = SteamDataProcessor(
            output_filename=args.output_file, schema_filename="schema.json",
            invalid_output_filename=args.invalid_output_file, batch_size=args.chunk_size,
            enable_logging=False
        )
        os.makedirs("data_collected", exist_ok=True)
        self.HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        self.COOKIES = {'birthtime': '568022401', 'wants_mature_content': '1', 'Steam_Language': 'english', 'steamCountry': 'US'}

    def _get_steam_urls(self, app_id: int):
        return {"details": f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english",
                "reviews": f"https://store.steampowered.com/appreviews/{app_id}?json=1&language=english",
                "store_page": f"https://store.steampowered.com/app/{app_id}/?l=english"}
    
    @staticmethod
    def get_already_processed_ids(filenames: List[str]):
        processed_ids = set()
        for filename in filenames:
            if not os.path.exists(filename): continue
            # On s'assure que le fichier est bien fermé même en cas d'erreur
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    try: 
                        app_id = int(json.loads(line)['app_id'])
                        processed_ids.add(app_id)
                    except (json.JSONDecodeError, KeyError, ValueError, TypeError): 
                        # Attrape toutes les erreurs possibles: ligne non-JSON, 
                        # clé manquante, valeur non convertible en int (ex: None)
                        continue
        return processed_ids

    @staticmethod
    def discover_all_app_ids_from_json(source_file: str): 
        if not os.path.exists(source_file):
            logger.error(f"Fichier source '{source_file}' introuvable.")
            return set()
        try:
            with open(source_file, 'r', encoding='utf-8') as f: games = json.load(f)
            ids = {int(m.group(1)) for g in games if (url := g.get("URL")) and (m := re.search(r'\/app\/(\d+)\/', url))}
            logger.info(f"Découverte terminée: {len(ids)} IDs uniques trouvés.")
            return ids
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erreur de lecture de '{source_file}': {e}")
            return set()

    async def process_game_details(self, app_id: int, session: aiohttp.ClientSession) -> RequestOutcome:
        """Traite un seul jeu et retourne son résultat pour le gouverneur."""
        await asyncio.sleep(self.governor.get_delay())
        urls = self._get_steam_urls(app_id)
        try:
            results = await asyncio.gather(
                session.get(urls["details"]), session.get(urls["reviews"]), session.get(urls["store_page"])
            )
            for resp in results:
                if resp.status == 429: return RequestOutcome.RATE_LIMIT
                if resp.status == 403: raise IPBannedException(f"Statut 403 (banni) sur {resp.url}")
                resp.raise_for_status()
            
            details_json = await results[0].json(content_type=None)
            reviews_json = await results[1].json(content_type=None)
            store_html = await results[2].text()

            if "g-recaptcha" in store_html: raise IPBannedException("CAPTCHA détecté")

            structured_data = self.processor.extract_and_structure_data(app_id, details_json, reviews_json, store_html)
            if structured_data:
                self.processor.process_and_validate_item(structured_data)
                await self.processor.flush_batches_if_needed()
            return RequestOutcome.SUCCESS

        except IPBannedException: raise
        except Exception as e:
            logger.debug(f"Erreur traitée pour l'App ID {app_id}: {e}")
            return RequestOutcome.FAILURE

    async def run(self):
        logger.info("Lancement du scraper auto-ajustable...")
        all_ids = self.discover_all_app_ids_from_json(self.args.source_file)
        if not all_ids or not self.processor.schema: return

        async with aiohttp.ClientSession(headers=self.HEADERS, cookies=self.COOKIES, timeout=aiohttp.ClientTimeout(total=self.args.timeout)) as session:
            while True:
                processed_ids = self.get_already_processed_ids([self.args.output_file, self.args.invalid_output_file])
                remaining_ids = sorted(list(all_ids - processed_ids))
                if not remaining_ids: break

                ids_for_this_run = remaining_ids[:self.args.chunk_size]
                logger.info("--- NOUVEAU LOT ---")
                logger.info(self.governor.status_line)
                
                try:
                    semaphore = asyncio.Semaphore(self.governor.get_concurrency())
                    
                    async def worker(app_id):
                        async with semaphore:
                            outcome = await self.process_game_details(app_id, session)
                            self.governor.record_outcome(outcome)
                    
                    await tqdm_asyncio.gather(*[worker(app_id) for app_id in ids_for_this_run], desc="Traitement du lot")
                    
                    # Ajuste la stratégie pour le prochain lot
                    self.governor.assess_and_adjust()

                except IPBannedException as e:
                    logger.error(f"🚫 BAN IP DÉTECTÉ: {e}")
                    logger.warning(f"Sauvegarde et hibernation pour {self.args.hibernate_minutes} minutes.")
                    self.processor.finalize_processing()
                    self.governor.reset_after_ban()
                    
                    for i in range(self.args.hibernate_minutes * 60, 0, -1):
                        print(f"\rReprise dans {i // 60:02d}:{i % 60:02d}...", end="")
                        await asyncio.sleep(1)
                    print("\r" + " " * 40 + "\r", end="")

        self.processor.finalize_processing()
        logger.info("🎉 Tous les jeux ont été traités. Script terminé.")

def main():
    parser = argparse.ArgumentParser(description="Scraper Steam auto-ajustable avec Gouverneur de Performance.")
    
    # --- Arguments de base ---
    parser.add_argument('--source-file', type=str, default="data_collected/steam_indie_games_final_api.json")
    parser.add_argument('--output-file', type=str, default="data_collected/steam_indie_games_detailed.jsonl")
    parser.add_argument('--invalid-output-file', type=str, default="data_collected/steam_indie_games_errors.jsonl")
    parser.add_argument('--chunk-size', type=int, default=100)
    parser.add_argument('--hibernate-minutes', type=int, default=30)
    parser.add_argument('--timeout', type=int, default=30)
    
    # --- Arguments du Gouverneur de Performance ---
    gov_group = parser.add_argument_group('Gouverneur de Performance')
    gov_group.add_argument('--min-concurrency', type=int, default=5, help="Concurrence minimale.")
    gov_group.add_argument('--max-concurrency', type=int, default=8, help="Concurrence maximale que le gouverneur peut viser.")
    gov_group.add_argument('--min-delay', type=float, default=3.0, help="Délai minimal absolu (en secondes).")
    gov_group.add_argument('--max-delay', type=float, default=7.0, help="Délai maximal après de multiples erreurs.")
    gov_group.add_argument('--history-size', type=int, default=100, help="Nombre de requêtes récentes à analyser pour prendre des décisions.")
    gov_group.add_argument('--throttle-threshold-pct', type=float, default=7.5, help="Pourcentage d'erreurs 429 pour passer en mode THROTTLED.")

    parser.add_argument('--verbose', action='store_true', help="Active les logs de débogage.")
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    # 'force=True' est utile pour reconfigurer le logger dans les environnements comme Jupyter
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', force=True)

    if os.name == 'nt': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    scraper = SteamScraper(args)
    asyncio.run(scraper.run())

if __name__ == "__main__":
    main()
