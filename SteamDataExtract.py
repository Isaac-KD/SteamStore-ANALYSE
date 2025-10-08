import json
import logging
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from bs4 import BeautifulSoup
from jsonschema import validate, ValidationError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


@dataclass
class SteamAppData:
    """Représente les données structurées d'une application Steam."""
    app_id: int
    nom: Optional[str]
    image: Optional[str]
    type: str
    description_courte: Optional[str]
    description_detaillee: Optional[str]
    est_gratuit: bool
    date_de_sortie: str
    developpeurs: List[str]
    editeurs: List[str]
    franchise: Optional[str]
    genres: List[str]
    categories: List[str]
    tags_utilisateurs: List[str]
    plateformes: List[str]
    configuration_requise: Dict[str, Dict[str, Dict[str, str]]]
    support_manette: Optional[str]
    langues: Dict[str, List[str]]
    evaluations: Dict[str, Any]
    donnees_commerciales: Dict[str, Any]
    contenu_et_fonctionnalites: Dict[str, Any]
    _validation_error: Optional[Dict[str, Any]] = None


class SteamDataProcessor:
    """
    Classe de traitement optimisée pour les données Steam, avec validation
    par schéma JSON et écriture par lots (périodique et finale).
    """

    # --- MODIFICATION 1 : Ajout du paramètre 'enable_logging' ---
    def __init__(self, output_filename: str, schema_filename: str, invalid_output_filename: str, batch_size: int = 20, enable_logging: bool = True):
        self.output_filename = output_filename
        self.invalid_output_filename = invalid_output_filename
        self.batch_size = batch_size
        self.enable_logging = enable_logging # On stocke l'état du logging

        self.schema = self._load_schema(schema_filename)
        self._valid_data_batch: List[Dict] = []
        self._invalid_data_batch: List[Dict] = []
        self._lock = asyncio.Lock()

    def _load_schema(self, schema_filename: str) -> Optional[Dict[str, Any]]:
        """Charge le schéma JSON depuis un fichier."""
        try:
            with open(schema_filename, 'r', encoding='utf-8') as f:
                if self.enable_logging: logging.info(f"Schéma '{schema_filename}' chargé.")
                return json.load(f)
        except FileNotFoundError:
            if self.enable_logging: logging.error(f"ERREUR: Fichier de schéma introuvable à '{schema_filename}'.")
            return None
        except json.JSONDecodeError as e:
            if self.enable_logging: logging.error(f"ERREUR: Le schéma '{schema_filename}' n'est pas un JSON valide: {e}")
            return None

    @staticmethod
    def _clean_html(html_content: Optional[str]) -> Optional[str]:
        """Nettoie une chaîne de caractères HTML pour ne conserver que le texte."""
        if not html_content: return None
        try:
            return BeautifulSoup(html_content, 'lxml').get_text(separator='\n', strip=True)
        except Exception as e:
            # On laisse un logging ici car c'est une erreur de parsing bas niveau qui peut être utile
            # même si le logging général est désactivé, mais on peut aussi le conditionner.
            # Pour l'instant, on le laisse inconditionnel car c'est une exception inattendue.
            logging.warning(f"Impossible de nettoyer le contenu HTML: {e}")
            return html_content

    @staticmethod
    def _parse_single_requirement_block(html_content: str) -> Dict[str, str]:
        if not html_content:
            return {}
        key_mapping = {
            "Système d'exploitation": "os", "OS": "os", "Processeur": "processeur", "Processor": "processeur",
            "Mémoire vive": "memoire_vive", "Memory": "memoire_vive", "Graphiques": "graphiques", "Graphics": "graphiques",
            "DirectX": "directx", "Espace disque": "stockage", "Storage": "stockage", "Réseau": "reseau", "Network": "reseau",
            "Carte son": "carte_son", "Sound Card": "carte_son", "Notes supplémentaires": "notes_supplementaires",
            "Additional Notes": "notes_supplementaires", "Prise en charge VR": "support_vr", "VR Support": "support_vr"
        }
        parsed_reqs = {}
        soup = BeautifulSoup(html_content, 'lxml')
        list_items = soup.find_all('li')
        if not list_items: return {}
        for item in list_items:
            strong_tag = item.find('strong')
            if not strong_tag: continue
            raw_key = strong_tag.get_text(strip=True).replace(':', '').strip()
            value = strong_tag.next_sibling
            if value: value = str(value).strip()
            standard_key = next((mapped_key for key, mapped_key in key_mapping.items() if key in raw_key), None)
            if standard_key and value: parsed_reqs[standard_key] = value
        return parsed_reqs

    @staticmethod
    def _parse_user_tags_from_html(html_content: Optional[str]) -> List[str]:
        if not html_content: return []
        try:
            return [tag.get_text(strip=True) for tag in BeautifulSoup(html_content, 'lxml').find_all('a', class_='app_tag')]
        except Exception as e:
            logging.warning(f"Impossible de parser les tags utilisateurs: {e}")
            return []

    @staticmethod
    def _parse_supported_languages(languages_string: Optional[str]) -> Dict[str, List[str]]:
        if not languages_string:
            return {"support_audio_complet": [], "support_partiel": []}
        cleaned_text = BeautifulSoup(languages_string.split('<br>')[0], 'lxml').get_text()
        languages = [lang.strip() for lang in cleaned_text.split(',')]
        full_audio_support = [lang.replace('*', '').strip() for lang in languages if '*' in lang]
        partial_support = [lang for lang in languages if '*' not in lang and lang]
        return {"support_audio_complet": full_audio_support, "support_partiel": partial_support}

    def extract_and_structure_data(self, app_id: int, details_json: Dict[str, Any], reviews_json: Dict[str, Any], store_page_html: str) -> Optional[SteamAppData]:
        details_data = details_json.get(str(app_id), {}).get('data', {})
        if not details_data:
            if self.enable_logging: logging.warning(f"Aucune donnée de détail trouvée pour l'app_id {app_id}.")
            return None
        
        reviews_summary = reviews_json.get('query_summary', {})
        total_reviews = reviews_summary.get("total_reviews", 0)
        total_positive = reviews_summary.get("total_positive", 0)
        
        config_requise = {}
        for platform in ["pc", "mac", "linux"]:
            req_data = details_data.get(f"{platform}_requirements", {})
            if not isinstance(req_data, dict) or not req_data: continue
            platform_config = {}
            min_req_html = req_data.get("minimum")
            rec_req_html = req_data.get("recommended")
            if min_req_html:
                parsed_min = self._parse_single_requirement_block(min_req_html)
                if parsed_min: platform_config["minimum"] = parsed_min
            if rec_req_html:
                parsed_rec = self._parse_single_requirement_block(rec_req_html)
                if parsed_rec: platform_config["recommande"] = parsed_rec
            if platform_config: config_requise[platform] = platform_config
        
        developers = details_data.get("developers", [])
        publishers = details_data.get("publishers", [])
        genres = [g.get("description") for g in details_data.get("genres", []) if g]
        categories = [c.get("description") for c in details_data.get("categories", []) if c]

        return SteamAppData(
            app_id=app_id, nom=details_data.get("name"), image=details_data.get("header_image"),
            type="dlc" if details_data.get("type") == "dlc" else "jeu",
            description_courte=self._clean_html(details_data.get("short_description")),
            description_detaillee=self._clean_html(details_data.get("detailed_description")),
            est_gratuit=details_data.get("is_free", False), date_de_sortie=details_data.get("release_date", {}).get("date", ""),
            developpeurs=list(set(developers)) if developers else [],
            editeurs=list(set(publishers)) if publishers else [],
            franchise=details_data.get("franchise"), genres=list(set(genres)), categories=list(set(categories)),
            tags_utilisateurs=self._parse_user_tags_from_html(store_page_html),
            plateformes=[p for p, available in details_data.get("platforms", {}).items() if available],
            configuration_requise=config_requise, support_manette=details_data.get("controller_support"),
            langues=self._parse_supported_languages(details_data.get("supported_languages")),
            evaluations={
                "metacritic_score": details_data.get("metacritic", {}).get("score"),
                "recommandations_total": details_data.get("recommendations", {}).get("total"),
                "avis_utilisateurs": {
                    "total_positif": total_positive, "total": total_reviews, 
                    "pourcentage_positif": round((total_positive / total_reviews) * 100, 2) if total_reviews > 0 else 0
                }
            },
            donnees_commerciales={
                "prix_initial": details_data.get("price_overview", {}).get("initial", 0),
                "prix_final": details_data.get("price_overview", {}).get("final", 0),
                "pourcentage_reduction": details_data.get("price_overview", {}).get("discount_percent", 0),
                "devise": details_data.get("price_overview", {}).get("currency", "EUR"),
                "dlcs": details_data.get("dlc", [])
            },
            contenu_et_fonctionnalites={"nombre_succes": details_data.get("achievements", {}).get("total", 0)}
        )

    def process_and_validate_item(self, data: SteamAppData):
        if not data: return
        data_dict = asdict(data)
        data_dict.pop('_validation_error', None)
        if self.schema is None:
            self._valid_data_batch.append(data_dict)
            return
        try:
            validate(instance=data_dict, schema=self.schema)
            self._valid_data_batch.append(data_dict)
        except ValidationError as e:
            data_dict['_validation_error'] = {'message': e.message, 'path': list(e.path)}
            self._invalid_data_batch.append(data_dict)
            
    async def flush_batches_if_needed(self):
        async with self._lock:
            if len(self._valid_data_batch) >= self.batch_size:
                data_to_write = self._valid_data_batch[:]
                self._valid_data_batch.clear()
                await asyncio.to_thread(self._write_batch_to_file, data_to_write, self.output_filename)
            if len(self._invalid_data_batch) >= self.batch_size:
                data_to_write = self._invalid_data_batch[:]
                self._invalid_data_batch.clear()
                await asyncio.to_thread(self._write_batch_to_file, data_to_write, self.invalid_output_filename)

    def finalize_processing(self):
        if self._valid_data_batch:
            self._write_batch_to_file(self._valid_data_batch, self.output_filename)
            self._valid_data_batch.clear()
        if self._invalid_data_batch:
            self._write_batch_to_file(self._invalid_data_batch, self.invalid_output_filename)
            self._invalid_data_batch.clear()

    def _write_batch_to_file(self, data_batch: List[Dict], filename: str):
        if self.enable_logging: logging.info(f"Ajout de {len(data_batch)} entrées dans '{filename}'...")
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                for item in data_batch:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            if self.enable_logging: logging.info(f"Écriture dans '{filename}' terminée.")
        except IOError as e:
            if self.enable_logging: logging.error(f"Erreur d'écriture dans le fichier '{filename}': {e}")