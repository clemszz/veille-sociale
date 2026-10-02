"""Un passage de veille : collecte -> pré-filtre -> fiches Gemini -> site.

Lancé chaque matin par GitHub Actions (.github/workflows/veille.yml), ou à la
main : `python -m veille` (voir README.md pour les options).

L'historique vit dans data/items.json (versionné dans le dépôt par le
workflow) : un élément déjà vu n'est jamais recollecté ni renvoyé à l'IA.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import ia, rendu
from .config import DATA_DIR, ETAT_PATH, GEMINI_API_KEY, ITEMS_PATH, VUS_PATH, charger_config
from .filtre import FiltreThemes, sans_accents
from .sources import collecter


def _url_canonique(url: str) -> str:
    p = urlsplit(url.strip())
    requete = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "xtor", "at_"))]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(requete), ""))


def _identifiant(url: str) -> str:
    return hashlib.sha1(_url_canonique(url).encode()).hexdigest()[:16]


def _cle_titre(titre: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sans_accents(titre).lower())


def charger_json(chemin, defaut):
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    return defaut


def ecrire_json(chemin, donnees):
    DATA_DIR.mkdir(exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def collecter_tout(config: dict, items: dict, etat: dict, vus: dict, maintenant: datetime) -> int:
    """vus : {source: [identifiants des éléments SANS DATE déjà rencontrés]}.
    Un élément sans date ne peut pas être situé dans le temps : au premier
    passage d'une source, ses éléments sans date servent de référence (non
    affichés, sinon d'anciennes pages apparaîtraient comme nouvelles) ; ensuite
    seul un élément sans date jamais vu est retenu, daté du jour."""
    filtre = FiltreThemes(config["themes"])
    reglages = config["collecte"]
    fenetre = reglages["fenetre_jours"] if items else reglages["premiere_collecte_jours"]
    plus_ancien = maintenant.date() - timedelta(days=fenetre)
    titres_connus = {_cle_titre(i["titre_officiel"]) for i in items.values()}
    total = 0

    for source in config["sources"]:
        if source.get("actif") is False:
            continue
        sid = source["id"]
        print(f"[{sid}] {source['nom']}")
        try:
            bruts = collecter(source)
        except Exception as e:  # une source en panne ne doit pas bloquer les autres
            print(f"  ÉCHEC : {e}")
            etat["sources"][sid] = {"nom": source["nom"], "ok": False, "erreur": str(e)[:300]}
            continue

        exclusions = [sans_accents(x).lower() for x in source.get("exclure") or []]
        premiere_fois = sid not in vus
        deja_vus = set(vus.get(sid, []))
        sans_date = []
        nouveaux = 0
        for b in bruts:
            iid = _identifiant(b["url"])
            if b["date"] is None:
                sans_date.append(iid)
                if premiere_fois or iid in deja_vus:
                    continue
            jour = b["date"] or maintenant.date()
            cle_titre = _cle_titre(b["titre"])
            if iid in items or cle_titre in titres_connus or jour < plus_ancien:
                continue
            titre_bas = sans_accents(b["titre"]).lower()
            if any(x in titre_bas for x in exclusions):
                continue
            themes, mots, score = filtre.analyser(b["titre"], b["extrait"])
            if source.get("filtrer", True) and not themes:
                continue
            items[iid] = {
                "id": iid,
                "url": b["url"],
                "source": sid,
                "date": jour.isoformat(),
                "collecte": maintenant.isoformat(timespec="seconds"),
                "titre_officiel": b["titre"],
                "extrait": b["extrait"],
                "themes": themes,
                "mots_cles": mots,
                "score": score,
                "ia": {"statut": "en_attente", "essais": 0},
            }
            if b.get("texte_ia"):
                # Texte long (JO, arrêts) gardé seulement le temps de la rédaction IA.
                items[iid]["texte_ia"] = b["texte_ia"]
            titres_connus.add(cle_titre)
            nouveaux += 1
        vus[sid] = list(dict.fromkeys(sans_date + vus.get(sid, [])))[:5000]
        total += nouveaux
        etat["sources"][sid] = {"nom": source["nom"], "ok": True, "lus": len(bruts), "nouveaux": nouveaux}
        print(f"  {len(bruts)} lus, {nouveaux} retenus")
    return total


def rediger_avec_ia(config: dict, items: dict, etat: dict) -> None:
    reglages = config["ia"]
    en_attente = sorted(
        (i for i in items.values() if i["ia"]["statut"] == "en_attente"),
        key=lambda i: i["date"], reverse=True,
    )
    etat["ia"] = {"active": bool(GEMINI_API_KEY), "traites": 0, "restants": len(en_attente)}
    if not GEMINI_API_KEY:
        print("[IA] pas de clé GEMINI_API_KEY : fiches non rédigées (extraits bruts affichés)")
        return
    if not en_attente:
        return

    sources = {s["id"]: s for s in config["sources"]}
    client = ia.ClientGemini(config["themes"], pause_s=reglages["pause_entre_appels_s"])
    a_traiter = en_attente[: reglages["max_elements_par_passage"]]
    taille = reglages["taille_lot"]
    print(f"[IA] {len(a_traiter)} élément(s) à rédiger sur {len(en_attente)} en attente")

    for debut in range(0, len(a_traiter), taille):
        lot = a_traiter[debut: debut + taille]
        entrees = []
        for item in lot:
            source = sources.get(item["source"], {})
            texte = item.get("texte_ia") or (ia.texte_page(item["url"]) if source.get("lire_page") else "")
            entrees.append({
                "id": item["id"],
                "source": source.get("nom", item["source"]),
                "date": item["date"],
                "titre": item["titre_officiel"],
                "texte": texte or item["extrait"] or "(pas d'extrait)",
            })
        try:
            fiches = client.rediger_fiches(entrees)
        except ia.QuotaAtteint as e:
            print(f"[IA] quota gratuit atteint, suite au prochain passage : {e}")
            etat["ia"]["message"] = "Quota gratuit atteint : les éléments restants seront rédigés au prochain passage."
            break
        except Exception as e:
            print(f"[IA] échec du lot : {e}")
            etat["ia"]["message"] = f"Dernière erreur IA : {str(e)[:200]}"
            fiches = {}
        for item in lot:
            fiche = fiches.get(item["id"])
            if fiche:
                item["ia"] = {"statut": "ok", "modele": client.modele_actif, **fiche}
                if fiche["themes"]:
                    item["themes"] = fiche["themes"]
                etat["ia"]["traites"] += 1
            else:
                item["ia"]["essais"] += 1
                if item["ia"]["essais"] >= reglages["essais_max"]:
                    item["ia"]["statut"] = "echec"
            if item["ia"]["statut"] != "en_attente":
                item.pop("texte_ia", None)
    etat["ia"]["modele"] = client.modele_actif
    etat["ia"]["restants"] = sum(1 for i in items.values() if i["ia"]["statut"] == "en_attente")
    print(f"[IA] {etat['ia']['traites']} fiche(s) rédigée(s), {etat['ia']['restants']} en attente")


def purger(config: dict, items: dict) -> None:
    limite = (date.today() - timedelta(days=config["site"]["conserver_jours"])).isoformat()
    for iid in [iid for iid, i in items.items() if i["date"] < limite]:
        del items[iid]
    # Sans clé Gemini, les textes longs en attente ne serviraient jamais :
    # on ne les garde pas indéfiniment dans l'historique.
    limite_texte = (date.today() - timedelta(days=30)).isoformat()
    for item in items.values():
        if item["date"] < limite_texte:
            item.pop("texte_ia", None)


def executer(sans_ia: bool = False, rendu_seul: bool = False) -> None:
    config = charger_config()
    maintenant = datetime.now(timezone.utc)
    items = {i["id"]: i for i in charger_json(ITEMS_PATH, [])}
    etat = charger_json(ETAT_PATH, {})
    vus = charger_json(VUS_PATH, {})

    if not rendu_seul:
        etat = {"derniere_execution": maintenant.isoformat(timespec="seconds"), "sources": {}, "ia": {}}
        nouveaux = collecter_tout(config, items, etat, vus, maintenant)
        etat["nouveaux"] = nouveaux
        if not sans_ia:
            rediger_avec_ia(config, items, etat)
        purger(config, items)
        tries = sorted(items.values(), key=lambda i: (i["date"], i["collecte"]), reverse=True)
        ecrire_json(ITEMS_PATH, tries)
        ecrire_json(ETAT_PATH, etat)
        ecrire_json(VUS_PATH, vus)
        print(f"Terminé : {nouveaux} nouvel(s) élément(s), {len(items)} en historique")

    rendu.generer_site(config, list(items.values()), etat)
