"""Pré-filtre par mots-clés : rattache chaque élément collecté à un ou plusieurs
thèmes de config.yaml, avant le jugement fin (et facultatif) par Gemini.

Règles de correspondance (pensées pour être éditées par un non-développeur
dans config.yaml) :
- accents, majuscules et apostrophes typographiques sont ignorés
  ("Invalidité" == "invalidite") ;
- un mot-clé est cherché comme mot entier ("rsa" ne matche pas "versant"),
  pluriel en -s/-x toléré ("arrêt de travail" matche "arrêts de travail") ;
- un mot-clé terminé par * est un préfixe ("handicap*" matche "handicapés") ;
- un mot-clé entièrement en MAJUSCULES est un sigle cherché en respectant la
  casse ("AME" ne matche pas "âme", "ASS" ne matche pas "assurance").
"""
import re
import unicodedata


def sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.replace("’", "'").replace(" ", " ")
    return re.sub(r"\s+", " ", texte)


def _est_sigle(mot_cle: str) -> bool:
    lettres = [c for c in mot_cle if c.isalpha()]
    return bool(lettres) and all(c.isupper() for c in lettres)


def _motif(mot_cle: str) -> str:
    if mot_cle.endswith("*"):
        return r"(?<!\w)" + re.escape(mot_cle[:-1])
    if _est_sigle(mot_cle):
        return r"(?<!\w)" + re.escape(mot_cle) + r"(?!\w)"
    # Chaque mot de 3 lettres ou plus peut prendre la marque du pluriel.
    morceaux = re.split(r"(\w+)", mot_cle)
    motif = "".join(
        re.escape(m) + ("[sx]?" if m.isalpha() and len(m) >= 3 and m[-1] not in "sx" else "")
        if i % 2 else re.escape(m)
        for i, m in enumerate(morceaux)
    )
    return r"(?<!\w)" + motif + r"(?!\w)"


def _compiler(mot_cle: str):
    return re.compile(_motif(mot_cle), 0 if _est_sigle(mot_cle) else re.IGNORECASE)


class FiltreThemes:
    def __init__(self, themes: dict):
        # {thème: [(regex, mot-clé tel qu'écrit dans config.yaml)]} : une regex
        # par mot-clé (quelques centaines, négligeable) pour pouvoir afficher
        # "arrêt de travail" quel que soit le texte trouvé ("arrets de travail").
        self._regles = {}
        for cle, theme in themes.items():
            regles = []
            for brut in theme.get("mots_cles") or []:
                mot = sans_accents(str(brut)).strip()
                if mot:
                    regles.append((_compiler(mot), str(brut).strip().rstrip("*")))
            self._regles[cle] = regles

    def analyser(self, titre: str, texte: str = "") -> tuple[list[str], list[str], int]:
        """Renvoie (thèmes trouvés, mots-clés trouvés, score).

        Le score compte les mots-clés distincts, avec un bonus quand le titre
        lui-même en contient (un mot-clé en titre est un signal bien plus fort
        qu'une mention au détour d'un paragraphe)."""
        titre_n = sans_accents(titre)
        complet = titre_n + " \n " + sans_accents(texte)
        themes, trouves, dans_titre = [], set(), False
        for cle, regles in self._regles.items():
            mots_theme = {libelle for regex, libelle in regles if regex.search(complet)}
            if mots_theme:
                themes.append(cle)
                trouves |= mots_theme
                dans_titre = dans_titre or any(regex.search(titre_n) for regex, _ in regles)
        score = len(trouves) + (3 if dans_titre else 0)
        return themes, sorted(trouves, key=str.lower), score
