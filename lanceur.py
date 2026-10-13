"""Point d'entrée de « Veille juridique.exe » : met la veille à jour (une fois
par jour au plus) puis ouvre le site dans le navigateur."""
import json
import sys
import webbrowser
from datetime import datetime

from veille.config import ETAT_PATH, SITE_DIR
from veille.run import executer


def deja_a_jour_aujourdhui() -> bool:
    try:
        derniere = json.loads(ETAT_PATH.read_text(encoding="utf-8"))["derniere_execution"]
    except (OSError, KeyError, ValueError):
        return False
    return datetime.fromisoformat(derniere).astimezone().date() == datetime.now().date()


def main() -> None:
    print("=== Veille juridique sociale AIPALS ===\n")
    if deja_a_jour_aujourdhui() and "--forcer" not in sys.argv:
        print("Veille déjà mise à jour aujourd'hui : ouverture du site.")
        executer(rendu_seul=True)
    else:
        print("Mise à jour en cours (1 à 5 minutes), ne fermez pas cette fenêtre...\n")
        executer()
    webbrowser.open((SITE_DIR / "index.html").as_uri())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nErreur : {e}")
        input("\nAppuyez sur Entrée pour fermer.")
