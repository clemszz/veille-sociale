"""Relais local : lit depuis ce PC les sources qui bloquent les serveurs de
GitHub mais pas une connexion ordinaire (ameli, dont le robots.txt autorise les
robots à 10 s d'intervalle), et dépose le relevé dans le dépôt (data/relais/).
Le dépôt relance alors le passage GitHub, qui l'intègre comme une source normale
(voir sources.collecter_relais).

Lancé par la tâche planifiée Windows « Veille AIPALS - relais ameli » (voir
installer_relais.ps1), sans fenêtre (pythonw). Travaille dans un clone dédié
(%LOCALAPPDATA%\\VeilleRelais\\depot) pour ne jamais toucher au dossier de
développement. Journal : %LOCALAPPDATA%\\VeilleRelais\\relais.log
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from veille import ia, sources

DEPOT_URL = "https://github.com/clemszz/veille-sociale.git"
DOSSIER = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VeilleRelais"
CLONE = DOSSIER / "depot"
JOURNAL = DOSSIER / "relais.log"
# Échouer tout de suite plutôt qu'attendre une saisie invisible si git
# réclame une authentification (tâche planifiée sans fenêtre).
ENV_GIT = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


def journal(message: str) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")


def git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(CLONE), *args], capture_output=True, text=True,
                       encoding="utf-8", env=ENV_GIT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} : {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def preparer_clone() -> None:
    if not (CLONE / ".git").exists():
        DOSSIER.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "20", DEPOT_URL, str(CLONE)], check=True,
                       capture_output=True, env=ENV_GIT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    git("fetch", "--depth", "20", "origin", "main")
    git("reset", "--hard", "origin/main")


def relever(source: dict) -> dict:
    """Relève la source et y joint le texte de chaque page (pour la rédaction
    IA côté GitHub, qui ne peut pas lire ces pages). Les pages déjà lues lors
    d'un relevé précédent ne sont pas relues."""
    chemin = CLONE / "data" / "relais" / f"{source['id']}.json"
    precedent = {}
    if chemin.exists():
        precedent = {e["url"]: e for e in json.loads(chemin.read_text(encoding="utf-8"))["elements"]}
    elements = []
    for e in sources.collecter(source, direct=True):
        texte = (precedent.get(e["url"]) or {}).get("texte_ia", "")
        if not texte and source.get("lire_page"):
            texte = ia.texte_page(e["url"])
        elements.append({**e, "date": e["date"].isoformat() if e["date"] else None, "texte_ia": texte})
    return {"source": source["id"], "releve_le": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elements": elements}


def publier() -> bool:
    git("add", "data/relais")
    if not git("status", "--porcelain", "data/relais").strip():
        return False
    git("-c", "user.name=Relais ameli (PC Clément)", "-c", "user.email=duran.clement74@gmail.com",
        "commit", "-m", f"Relais ameli du {datetime.now():%Y-%m-%d %H:%M}")
    for tentative in range(3):  # le passage GitHub peut avoir poussé entre-temps
        try:
            git("push", "origin", "HEAD:main")
            return True
        except RuntimeError:
            if tentative == 2:
                raise
            git("pull", "--rebase", "origin", "main")
    return False


def main() -> None:
    preparer_clone()
    config = yaml.safe_load((CLONE / "config.yaml").read_text(encoding="utf-8"))
    a_relayer = [s for s in config["sources"] if s.get("relais_local") and s.get("actif") is not False]
    (CLONE / "data" / "relais").mkdir(parents=True, exist_ok=True)
    for source in a_relayer:
        try:
            releve = relever(source)
        except Exception as e:  # on garde le relevé précédent : GitHub verra qu'il vieillit
            journal(f"{source['id']} : ÉCHEC {e}")
            continue
        (CLONE / "data" / "relais" / f"{source['id']}.json").write_text(
            json.dumps(releve, ensure_ascii=False, indent=1), encoding="utf-8")
        journal(f"{source['id']} : {len(releve['elements'])} actualités relevées")
    journal("relevé publié sur GitHub" if publier() else "rien de nouveau à publier")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        journal(f"ERREUR : {e}")
        raise
