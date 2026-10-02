"""python -m veille [--sans-ia] [--rendu-seul]"""
import argparse

from .run import executer

parser = argparse.ArgumentParser(description="Veille juridique sociale AIPALS")
parser.add_argument("--sans-ia", action="store_true", help="collecter sans appeler Gemini")
parser.add_argument("--rendu-seul", action="store_true",
                    help="régénérer le site depuis data/ sans rien collecter (après une retouche du modèle de page)")
args = parser.parse_args()
executer(sans_ia=args.sans_ia, rendu_seul=args.rendu_seul)
