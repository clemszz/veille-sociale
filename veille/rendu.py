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


def _regrouper(items: list[dict], elements: list[dict], rang_source: dict) -> list[dict]:
    """Réunit chaque groupe de doublons (voir run.regrouper_doublons) en une
    fiche : rien n'est perdu, la fiche liste les autres sources avec leur lien,
    leur titre et leur résumé, et prend l'importance la plus haute et l'union
    des thèmes du groupe. La fiche principale est celle de la source placée le
    plus haut dans config.yaml (sources officielles avant la presse)."""
    doublon_de = {i["id"]: i.get("doublon_de") for i in items}
    source_de = {i["id"]: i["source"] for i in items}
    par_id = {e["id"]: e for e in elements}
    groupes = {}
    for e in elements:
        racine, vus = e["id"], set()
        while doublon_de.get(racine) and racine not in vus:
            vus.add(racine)
            racine = doublon_de[racine]
        if racine not in par_id:
            racine = e["id"]  # fiche d'origine purgée de l'historique : l'élément reste seul
        groupes.setdefault(racine, []).append(e)
    resultat = []
    for membres in groupes.values():
        membres.sort(key=lambda e: (rang_source.get(source_de[e["id"]], len(rang_source)), e["date"]))
        principal = membres[0]
        principal["autres"] = []
        for e in membres[1:]:
            principal["autres"].append({k: e[k] for k in ("source", "url", "titre", "date", "resume", "aRetenir")})
            principal["importance"] = max(principal["importance"], e["importance"])
            principal["themes"] += [t for t in e["themes"] if t not in principal["themes"]]
            principal["motsCles"] += [m for m in e["motsCles"] if m not in principal["motsCles"]]
            principal["dateEffet"] = principal["dateEffet"] or e["dateEffet"]
        resultat.append(principal)
    return resultat


def _flux_rss(config: dict, elements: list[dict], url_site: str) -> str:
    entrees = []
    for e in elements:
        description = e["resume"] + (f"\n\nÀ retenir : {e['aRetenir']}" if e["aRetenir"] else "")
        description += "".join(f"\nAussi publié par {a['source']} : {a['url']}" for a in e["autres"])
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
    rang_source = {s["id"]: n for n, s in enumerate(config["sources"])}
    elements = _regrouper(items, [_pour_affichage(i, noms) for i in items], rang_source)
    elements.sort(key=lambda e: (e["date"], e["collecte"]), reverse=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html", "j2"]))
    page = env.get_template("index.html.j2").render(
        site=config["site"],
        themes={cle: t["libelle"] for cle, t in config["themes"].items()},
        etat=etat,
        # Une source « alerte: false » en échec n'est pas affichée (elle reste
        # tentée chaque jour et son erreur est consignée dans data/etat.json).
        sources=[s for s in config["sources"] if s.get("actif") is not False
                 and not (s.get("alerte") is False
                          and not (etat.get("sources") or {}).get(s["id"], {}).get("ok", True))],
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
