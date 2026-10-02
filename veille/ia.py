"""Fiches de veille rédigées par Gemini (API Google AI Studio, offre gratuite).

Un appel traite un LOT d'éléments déjà retenus par le pré-filtre mots-clés
(voir filtre.py) : pertinence pour l'assistante sociale, importance, thèmes,
titre clair, résumé, point pratique, date d'effet. Les éléments déjà traités
ne sont jamais renvoyés au modèle (statut "ok" dans data/items.json), ce qui
tient la consommation largement sous les quotas gratuits.

Sans clé (GEMINI_API_KEY vide), ce module n'est pas appelé : le site affiche
alors les extraits officiels bruts et les thèmes trouvés par mots-clés.

Seules des actualités publiques sont envoyées à Google (aucune donnée sur les
salariés accompagnés). Sur l'offre gratuite, Google peut utiliser ces contenus
pour améliorer ses produits, ce qui est sans enjeu ici.
"""
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from . import http
from .config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODELES_REPLI

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

TYPES = [
    "Loi", "Décret", "Arrêté", "Ordonnance", "Circulaire / instruction",
    "Jurisprudence", "Revalorisation / barème", "Projet de loi / réforme",
    "Démarche / info pratique", "Actualité",
]

SYSTEM_PROMPT = """Tu es juriste en droit de la protection sociale et du travail. \
Tu prépares la veille juridique d'une assistante sociale du travail qui exerce \
dans un service de prévention et de santé au travail interentreprises (SPSTI) \
en France. Elle accompagne des salariés et leurs employeurs sur : le maintien \
dans l'emploi et la prévention de la désinsertion professionnelle, les arrêts \
de travail et indemnités journalières, l'inaptitude, l'invalidité, les AT/MP, \
le handicap (RQTH, MDPH, AAH, Agefiph), la retraite, et l'accès aux droits \
(RSA, prime d'activité, CAF, logement, surendettement, C2S...).

Pour CHAQUE élément fourni, rends une fiche JSON avec :
- id : recopie exactement l'id fourni.
- pertinent : true si l'élément peut changer ou éclairer concrètement \
l'accompagnement d'un salarié par cette assistante sociale (droits, montants, \
conditions, démarches, délais, dispositifs, obligations de l'employeur liées à \
la santé). false s'il est hors sujet pour elle : fonction publique uniquement, \
fiscalité des entreprises, santé publique sans lien avec les droits sociaux, \
communication institutionnelle sans contenu juridique, droit étranger.
- importance : 3 = à connaître absolument (nouveau droit, réforme, changement \
de conditions, de montants ou de procédure, suppression d'un dispositif) ; \
2 = utile (précision, revalorisation, nouvelle démarche, jurisprudence \
notable) ; 1 = information de contexte.
- themes : 1 ou 2 valeurs parmi la liste fermée fournie, la plus concernée en premier.
- type : une valeur de la liste fermée fournie.
- titre : titre clair et factuel de 15 mots maximum, compréhensible sans \
contexte (pas de copier-coller du titre officiel quand il est obscur, ex. \
"Décret n° 2026-xxx relatif à..." -> dis ce qu'il change).
- resume : 2 à 3 phrases simples : ce qui change concrètement, pour qui, à \
partir de quand.
- a_retenir : une phrase pratique pour l'accompagnement des salariés (ex. \
"Vérifier que...", "Informer les salariés en arrêt long que..."), uniquement si \
le texte le permet ; sinon chaîne vide.
- date_effet : date d'entrée en vigueur ou d'application au format AAAA-MM-JJ \
si elle figure explicitement dans le texte, sinon chaîne vide.

RÈGLES :
- N'invente RIEN : aucun montant, date, condition ou dispositif absent du \
texte fourni. Si l'extrait est trop pauvre pour un résumé fiable, écris \
"Extrait insuffisant : consulter la source." dans resume.
- Français courant, ton neutre et professionnel, texte brut (pas de Markdown).
- Une fiche par élément, dans le même ordre."""


def _schema(themes: list[str]) -> dict:
    return {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "STRING"},
                "pertinent": {"type": "BOOLEAN"},
                "importance": {"type": "INTEGER"},
                "themes": {"type": "ARRAY", "items": {"type": "STRING", "format": "enum", "enum": themes}},
                "type": {"type": "STRING", "format": "enum", "enum": TYPES},
                "titre": {"type": "STRING"},
                "resume": {"type": "STRING"},
                "a_retenir": {"type": "STRING"},
                "date_effet": {"type": "STRING"},
            },
            "required": ["id", "pertinent", "importance", "themes", "type",
                         "titre", "resume", "a_retenir", "date_effet"],
        },
    }


class QuotaAtteint(Exception):
    """Quota gratuit épuisé (HTTP 429 persistant) : on arrête l'IA pour ce
    passage, les éléments restants seront traités au prochain."""


class ClientGemini:
    def __init__(self, themes: dict, pause_s: float = 7.0):
        self.themes = themes
        self.pause_s = pause_s
        self.modeles = list(dict.fromkeys([GEMINI_MODEL] + GEMINI_MODELES_REPLI))
        self.modele_actif = None
        self.avec_schema = True
        self._dernier_appel = 0.0

    def _appel(self, modele: str, corps: dict) -> requests.Response:
        attente = self.pause_s - (time.monotonic() - self._dernier_appel)
        if attente > 0:
            time.sleep(attente)
        self._dernier_appel = time.monotonic()
        return requests.post(
            API_URL.format(modele=modele),
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json=corps,
            timeout=180,
        )

    def _generer(self, corps: dict) -> str:
        """Essaie les modèles dans l'ordre ; un modèle introuvable ou fermé à
        l'offre gratuite est écarté pour le reste du passage."""
        while self.modeles:
            modele = self.modeles[0]
            for tentative in range(3):
                r = self._appel(modele, corps)
                if r.status_code == 200:
                    self.modele_actif = modele
                    return _texte_reponse(r.json())
                # Modèle retiré, ou hors offre gratuite (Google répond alors
                # 429 avec un quota "limit: 0") : inutile d'insister dessus.
                if r.status_code == 404 or (r.status_code == 429 and "limit: 0" in r.text):
                    break
                if r.status_code == 429:
                    if tentative == 2:
                        raise QuotaAtteint(r.text[:300])
                    time.sleep(30 * (tentative + 1))
                    continue
                if r.status_code >= 500 and tentative < 2:
                    time.sleep(10)
                    continue
                raise RuntimeError(f"Gemini HTTP {r.status_code} : {r.text[:300]}")
            print(f"  [IA] modèle {modele} indisponible ({r.status_code}), repli sur le suivant")
            self.modeles.pop(0)
        raise RuntimeError("Aucun modèle Gemini disponible (voir GEMINI_MODEL)")

    def rediger_fiches(self, elements: list[dict]) -> dict[str, dict]:
        """elements : dicts avec id, source, date, titre, texte. Renvoie {id: fiche}."""
        blocs = []
        for e in elements:
            blocs.append(
                f"[ÉLÉMENT id={e['id']}]\nSource : {e['source']}\nDate : {e['date']}\n"
                f"Titre officiel : {e['titre']}\nTexte :\n{e['texte']}\n[FIN]"
            )
        consigne = (
            "Thèmes (liste fermée, utilise la clé) :\n"
            + "\n".join(f"- {cle} : {t['libelle']}" for cle, t in self.themes.items())
            + "\n\nTypes (liste fermée) : " + ", ".join(TYPES)
            + "\n\nÉléments à traiter :\n\n" + "\n\n".join(blocs)
        )
        corps = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": consigne}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        if self.avec_schema:
            corps["generationConfig"]["responseSchema"] = _schema(list(self.themes))
        try:
            reponse = self._generer(corps)
        except RuntimeError as e:
            # Filet de sécurité : si un futur modèle refuse le schéma JSON, on
            # se contente de la consigne (qui décrit déjà chaque champ).
            if not self.avec_schema or "HTTP 400" not in str(e):
                raise
            print(f"  [IA] schéma JSON refusé, nouvel essai sans : {e}")
            self.avec_schema = False
            del corps["generationConfig"]["responseSchema"]
            reponse = self._generer(corps)
        fiches = json.loads(_nettoyer_json(reponse))
        return {f["id"]: _valider(f, self.themes) for f in fiches if isinstance(f, dict) and "id" in f}


def _texte_reponse(donnees: dict) -> str:
    try:
        parts = donnees["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Réponse Gemini sans contenu : {json.dumps(donnees)[:300]}")
    # Les modèles "thinking" peuvent renvoyer des parts de réflexion avant la réponse.
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _nettoyer_json(texte: str) -> str:
    texte = texte.strip()
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte)
    return texte


def _valider(fiche: dict, themes: dict) -> dict:
    """Filet de sécurité si le modèle sort du schéma malgré la consigne."""
    try:
        importance = min(3, max(1, int(fiche.get("importance") or 1)))
    except (TypeError, ValueError):
        importance = 1
    date_effet = str(fiche.get("date_effet") or "")
    return {
        "pertinent": bool(fiche.get("pertinent", True)),
        "importance": importance,
        "themes": [t for t in fiche.get("themes") or [] if t in themes][:2],
        "type": fiche.get("type") if fiche.get("type") in TYPES else "Actualité",
        "titre": str(fiche.get("titre") or "").strip(),
        "resume": str(fiche.get("resume") or "").strip(),
        "a_retenir": str(fiche.get("a_retenir") or "").strip(),
        "date_effet": date_effet if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_effet) else "",
    }


def texte_page(url: str, max_car: int = 4000) -> str:
    """Texte principal d'une page web, pour donner au modèle plus que le court
    extrait du flux RSS. Chaîne vide en cas d'échec (on se rabat sur l'extrait)."""
    try:
        r = http.get(url, timeout=30)
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(r.content, "html.parser")
    for balise in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        balise.decompose()
    zone = soup.find("article") or soup.find("main") or soup.body or soup
    texte = re.sub(r"\s+", " ", zone.get_text(" ", strip=True))
    return texte[:max_car]
