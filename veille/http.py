"""Requêtes HTTP communes, avec un délai minimal entre deux requêtes vers un
même site (certains l'exigent dans leur robots.txt, ex. ameli : 10 s)."""
import time
from urllib.parse import urlsplit

import requests

from .config import USER_AGENT

DELAI_DEFAUT_S = 1.0
_delais: dict[str, float] = {}
_derniere_requete: dict[str, float] = {}


def regler_delai(url: str, secondes: float) -> None:
    _delais[urlsplit(url).netloc] = secondes


def get(url: str, timeout: float = 45) -> requests.Response:
    hote = urlsplit(url).netloc
    attente = _delais.get(hote, DELAI_DEFAUT_S) - (time.monotonic() - _derniere_requete.get(hote, -1e9))
    if attente > 0:
        time.sleep(attente)
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr"}, timeout=timeout)
    finally:
        _derniere_requete[hote] = time.monotonic()
    r.raise_for_status()
    return r
