"""Chemins, paramètres (config.yaml) et secrets (variables d'environnement).

En local, les secrets peuvent être placés dans un fichier .env à la racine
(voir .env.example). Sur GitHub, ils viennent des "Secrets" du dépôt
(Settings > Secrets and variables > Actions), injectés par le workflow.
"""
import os
import shutil
import sys
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

FICHIERS_DE_TRAVAIL = ["config.yaml", ".env", "templates", "assets", "data"]


def _dossier_de_travail() -> Path:
    """Dossier des fichiers de travail (config, .env, data/, site/...).

    - En développement : la racine du projet.
    - En .exe (PyInstaller, voir lanceur.py) : le dossier de l'exe s'il
      contient config.yaml (cas normal, dossier décompressé). Sinon l'exe a été
      lancé seul, typiquement par double-clic DANS le zip : Windows ne copie
      alors que l'exe dans un dossier temporaire jetable. On travaille dans un
      dossier stable du profil, initialisé avec les fichiers embarqués dans
      l'exe (sys._MEIPASS/defaut) sans jamais écraser l'existant.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    pres_exe = Path(sys.executable).resolve().parent
    if (pres_exe / "config.yaml").exists():
        return pres_exe
    dossier = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Veille juridique AIPALS"
    defaut = Path(getattr(sys, "_MEIPASS", "")) / "defaut"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom in FICHIERS_DE_TRAVAIL:
        source, cible = defaut / nom, dossier / nom
        if source.exists() and not cible.exists():
            if source.is_dir():
                shutil.copytree(source, cible)
            else:
                shutil.copy2(source, cible)
    return dossier


BASE_DIR = _dossier_de_travail()
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
# Flash-Lite par défaut : rapide et au quota gratuit le plus large (Flash
# n'autorise que 20 requêtes/jour en offre gratuite).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"
GEMINI_MODELES_REPLI = ["gemini-3.8-flash", "gemini-flash-latest"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 VeilleSocialeAIPALS/1.0"
)


def charger_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
