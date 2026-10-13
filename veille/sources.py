"""Collecte des éléments bruts depuis les sources déclarées dans config.yaml.

Chaque source a un "type" :
- rss  : flux RSS/Atom (le cas général, le plus robuste) ;
- html : page liste sans flux, lue avec des sélecteurs CSS (plus fragile : à
         revoir si le site change sa mise en page) ;
- dila : archives open data de la DILA (echanges.dila.gouv.fr), sans compte :
         fonds JORFSIMPLE (Journal officiel) ou CASS (arrêts publiés de la
         Cour de cassation). Légifrance bloquant les robots, c'est la voie
         officielle pour suivre le JO et la jurisprudence.

Chaque collecteur renvoie une liste de dicts {url, titre, date, extrait} et,
facultativement, texte_ia (texte plus long réservé à la rédaction par l'IA).
Une source en échec n'arrête pas la veille : l'erreur est consignée dans
data/etat.json et signalée en pied de page du site.
"""
import calendar
import io
import re
import tarfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from . import http

MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def texte_brut(html: str, max_car: int = 700) -> str:
    texte = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return tronquer(texte, max_car)


def tronquer(texte: str, max_car: int) -> str:
    texte = re.sub(r"\s+", " ", texte or "").strip()
    if len(texte) > max_car:
        texte = texte[:max_car].rsplit(" ", 1)[0] + "…"
    return texte


def date_fr(texte: str) -> date | None:
    """'2 octobre 2026', '1er octobre 2026', '02/10/2026', '02.10.2026' ou '2026-10-02'."""
    if not texte:
        return None
    t = texte.lower()
    try:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", t)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
        m = re.search(r"(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})", t)
        if m and m[2] in MOIS:
            return date(int(m[3]), MOIS[m[2]], int(m[1]))
    except ValueError:
        pass
    return None


def collecter_rss(source: dict) -> list[dict]:
    r = http.get(source["url"])
    if r.headers.get("Content-Type", "").startswith("text/html") and b"<rss" not in r.content[:2000]:
        raise ValueError("le site a renvoyé une page web au lieu du flux (blocage anti-robots, "
                         "souvent temporaire)")
    # lstrip : certains flux (ex. Présanse) ont des espaces avant <?xml.
    flux = feedparser.parse(r.content.lstrip())
    if flux.bozo and not flux.entries:
        raise ValueError(f"flux illisible : {flux.bozo_exception}")
    elements = []
    for e in flux.entries:
        lien = e.get("link") or ""
        titre = texte_brut(e.get("title", ""), 400)
        if not lien or not titre:
            continue
        struct = e.get("published_parsed") or e.get("updated_parsed")
        jour = (
            datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc).date()
            if struct else date_fr(e.get("published", "") or e.get("updated", ""))
        )
        resume = e.get("summary", "")
        if not resume and e.get("content"):
            resume = e["content"][0].get("value", "")
        elements.append({"url": lien, "titre": titre, "date": jour, "extrait": texte_brut(resume)})
    return elements


def collecter_html(source: dict) -> list[dict]:
    """Page liste : source["selecteurs"] = {item, titre?, lien?, date?, resume?}.
    - lien par défaut : l'item lui-même si c'est un <a>, sinon son premier <a> ;
    - date par défaut : première date trouvée dans le texte de l'item."""
    sel = source["selecteurs"]
    soup = BeautifulSoup(http.get(source["url"]).content, "html.parser")
    elements = []
    for bloc in soup.select(sel["item"]):
        noeud_titre = bloc.select_one(sel["titre"]) if sel.get("titre") else bloc
        noeud_lien = bloc.select_one(sel["lien"]) if sel.get("lien") else (
            bloc if bloc.name == "a" else bloc.find("a"))
        if not noeud_titre or not noeud_lien or not noeud_lien.get("href"):
            continue
        noeud_date = bloc.select_one(sel["date"]) if sel.get("date") else None
        noeud_resume = bloc.select_one(sel["resume"]) if sel.get("resume") else None
        jour = None
        if noeud_date:
            jour = date_fr(noeud_date.get("datetime") or noeud_date.get_text(" ", strip=True))
        if not jour:
            jour = date_fr(bloc.get_text(" ", strip=True))
        elements.append({
            "url": urljoin(source["url"], noeud_lien["href"]),
            "titre": tronquer(noeud_titre.get_text(" ", strip=True), 400),
            "date": jour,
            "extrait": texte_brut(str(noeud_resume)) if noeud_resume else "",
        })
    if not elements:
        raise ValueError("aucun élément trouvé : la mise en page du site a peut-être changé")
    return elements


# --- Open data DILA ----------------------------------------------------------

DILA_URL = "https://echanges.dila.gouv.fr/OPENDATA/{fonds}/"


def _texte_xml(noeud) -> str:
    return re.sub(r"\s+", " ", "".join(noeud.itertext())).strip() if noeud is not None else ""


def _jorf(racine, jour_archive: date, depuis: date) -> dict | None:
    """Un texte du Journal officiel (fichier JORFTEXT*.xml)."""
    if racine.tag != "TEXTE":
        return None
    publie = date_fr(racine.findtext("DATE_PUBLI") or "")
    if not publie or publie < depuis:  # les archives contiennent aussi des mises à jour de vieux textes
        return None
    titre = racine.findtext("TITREFULL") or racine.findtext("TITRE") or ""
    notice = _texte_xml(racine.find("NOTICE"))
    articles = _texte_xml(racine.find("STRUCT"))
    ministere = racine.findtext("MINISTERE") or ""
    return {
        "url": f"https://www.legifrance.gouv.fr/jorf/id/{racine.findtext('ID')}",
        "titre": tronquer(titre, 400),
        "date": publie,
        # Le pré-filtre mots-clés ne porte que sur le titre et la notice : les
        # articles citent quantité de codes (dont celui de la sécurité
        # sociale) et feraient remonter des textes sans rapport.
        "extrait": tronquer(notice, 700),
        "texte_ia": tronquer(f"Ministère : {ministere}\nNotice : {notice}\nArticles : {articles}", 5000),
    }


def _cass(racine, jour_archive: date, depuis: date, chambres: list[str]) -> dict | None:
    """Un arrêt publié de la Cour de cassation (fichier JURITEXT*.xml)."""
    if racine.tag != "TEXTE_JURI_JUDI" or racine.findtext(".//FORMATION") not in chambres:
        return None
    sommaire = _texte_xml(racine.find(".//SOMMAIRE"))
    decision = _texte_xml(racine.find(".//TEXTE/BLOC_TEXTUEL"))
    return {
        "url": f"https://www.legifrance.gouv.fr/juri/id/{racine.findtext('.//ID')}",
        "titre": tronquer(racine.findtext(".//TITRE") or "", 400),
        # Les arrêts arrivent dans l'open data quelques semaines après avoir
        # été rendus : on date l'élément du jour de mise à disposition (la
        # date de l'arrêt figure dans son titre).
        "date": jour_archive,
        "extrait": tronquer(sommaire, 700),
        "texte_ia": tronquer(f"Sommaire : {sommaire}\nDécision : {decision[-3500:]}", 5000),
    }


def collecter_dila(source: dict) -> list[dict]:
    fonds = source["fonds"]
    depuis = date.today() - timedelta(days=source.get("jours", 5))
    index = http.get(DILA_URL.format(fonds=fonds)).text
    archives = sorted(set(re.findall(rf"({fonds}_(\d{{8}})-\d{{6}}\.tar\.gz)", index)))
    archives = [(nom, datetime.strptime(j, "%Y%m%d").date()) for nom, j in archives]
    archives = [(nom, j) for nom, j in archives if j >= depuis]
    elements = {}
    for nom, jour_archive in archives:
        contenu = http.get(DILA_URL.format(fonds=fonds) + nom, timeout=180).content
        with tarfile.open(fileobj=io.BytesIO(contenu), mode="r:gz") as tar:
            for membre in tar:
                if not membre.isfile() or not membre.name.endswith(".xml"):
                    continue
                fichier = membre.name.rsplit("/", 1)[-1]
                if fonds == "JORFSIMPLE" and not fichier.startswith("JORFTEXT"):
                    continue
                if fonds == "CASS" and not fichier.startswith("JURITEXT"):
                    continue
                try:
                    racine = ET.fromstring(tar.extractfile(membre).read())
                except ET.ParseError:
                    continue
                if fonds == "JORFSIMPLE":
                    element = _jorf(racine, jour_archive, depuis)
                else:
                    element = _cass(racine, jour_archive, depuis, source.get("chambres", []))
                if element:
                    elements[element["url"]] = element
    return list(elements.values())


COLLECTEURS = {"rss": collecter_rss, "html": collecter_html, "dila": collecter_dila}


def collecter(source: dict) -> list[dict]:
    if source.get("delai_s"):
        http.regler_delai(source["url"] if "url" in source else DILA_URL, source["delai_s"])
    return COLLECTEURS[source.get("type", "rss")](source)
