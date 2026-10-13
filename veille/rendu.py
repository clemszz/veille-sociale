"""Génère le site statique publié sur GitHub Pages :
- site/index.html : la page de veille (données embarquées, filtres côté navigateur) ;
- site/flux.xml   : flux RSS des éléments retenus, pour s'abonner dans Outlook.
"""
import base64
import json
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ASSETS_DIR, SITE_DIR, TEMPLATES_DIR


def _importance(item: dict) -> int:
    """Sans fiche IA, une importance approximative déduite du score mots-clés."""
    if item["ia"]["statut"] == "ok":
        return item["ia"]["importance"]
    return 2 if item["score"] >= 6 else 1


def _pour_affichage(item: dict, noms_sources: dict) -> dict:
    fiche = item["ia"] if item["ia"]["statut"] == "ok" else {}
    return {
        "id": item["id"],
        "url": item["url"],
        "source": noms_sources.get(item["source"], item["source"]),
        "date": item["date"],
        "collecte": item["collecte"],
        "titre": fiche.get("titre") or item["titre_officiel"],
        "titreOfficiel": item["titre_officiel"],
        "resume": fiche.get("resume") or item["extrait"],
        "aRetenir": fiche.get("a_retenir", ""),
        "dateEffet": fiche.get("date_effet", ""),
        "type": fiche.get("type", ""),
        "importance": _importance(item),
        "themes": item["themes"],
        "motsCles": item["mots_cles"],
        "pertinent": fiche.get("pertinent", True),
        "ia": bool(fiche),
    }


def _flux_rss(config: dict, elements: list[dict], url_site: str) -> str:
    entrees = []
    for e in elements:
        description = e["resume"] + (f"\n\nÀ retenir : {e['aRetenir']}" if e["aRetenir"] else "")
        publie = datetime.fromisoformat(e["collecte"])
        etoiles = "★" * e["importance"]
        entrees.append(
            "<item>"
            f"<title>{escape(etoiles + ' ' + e['titre'])}</title>"
            f"<link>{escape(e['url'])}</link>"
            f"<guid isPermaLink=\"false\">{e['id']}</guid>"
            f"<pubDate>{format_datetime(publie)}</pubDate>"
            f"<category>{escape(e['source'])}</category>"
            f"<description>{escape(description)}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape(config['site']['titre'])}</title>"
        f"<link>{escape(url_site)}</link>"
        f"<description>{escape(config['site']['sous_titre'])}</description>"
        "<language>fr-FR</language>"
        + "".join(entrees)
        + "</channel></rss>\n"
    )


def generer_site(config: dict, items: list[dict], etat: dict) -> None:
    noms = {s["id"]: s["nom"] for s in config["sources"]}
    elements = [_pour_affichage(i, noms) for i in items]
    elements.sort(key=lambda e: (e["date"], e["collecte"]), reverse=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html", "j2"]))
    page = env.get_template("index.html.j2").render(
        site=config["site"],
        themes={cle: t["libelle"] for cle, t in config["themes"].items()},
        etat=etat,
        sources=[s for s in config["sources"] if s.get("actif") is not False],
        genere_le=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Logo embarqué pour l'en-tête du PDF (un fichier local ne peut pas être
        # relu par le navigateur depuis une page ouverte en file://).
        logo_blanc="data:image/png;base64,"
        + base64.b64encode((ASSETS_DIR / "logo-aipals-blanc.png").read_bytes()).decode(),
        # "</" échappé pour qu'un titre contenant "</script>" ne casse pas la page.
        donnees_json=json.dumps(elements, ensure_ascii=False).replace("</", "<\\/"),
    )

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir()
    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copytree(ASSETS_DIR, SITE_DIR / "assets")

    retenus = sorted((e for e in elements if e["pertinent"]), key=lambda e: e["collecte"], reverse=True)
    (SITE_DIR / "flux.xml").write_text(
        _flux_rss(config, retenus[:80], config["site"].get("url", "")), encoding="utf-8")
    print(f"Site généré : {SITE_DIR / 'index.html'} ({len(elements)} éléments)")
