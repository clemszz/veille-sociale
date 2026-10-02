"""Chemins, paramètres (config.yaml) et secrets (variables d'environnement).

En local, les secrets peuvent être placés dans un fichier .env à la racine
(voir .env.example). Sur GitHub, ils viennent des "Secrets" du dépôt
(Settings > Secrets and variables > Actions), injectés par le workflow.
"""
import os
from pathlib import Path

import yaml

try:
    # Sur un poste Windows derrière un proxy d'entreprise avec inspection TLS,
    # fait utiliser à Python le magasin de certificats du système plutôt que
    # le bundle certifi. Sans effet gênant ailleurs (GitHub Actions).
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SITE_DIR = BASE_DIR / "site"
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"
ITEMS_PATH = DATA_DIR / "items.json"
ETAT_PATH = DATA_DIR / "etat.json"
VUS_PATH = DATA_DIR / "vus.json"

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Modèle principal, puis replis si le modèle n'existe plus/n'est pas ouvert à
# l'offre gratuite du projet Google (voir ia.py). Surchargeable sans toucher au
# code via la variable de dépôt GEMINI_MODEL.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"
GEMINI_MODELES_REPLI = ["gemini-flash-latest", "gemini-3.5-flash-lite"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 VeilleSocialeAIPALS/1.0"
)


def charger_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
