"""
Rejeu de l'année 2024 avec le code opérationnel du service.

Toutes les 5 minutes simulées, on reconstitue ce que le collecteur aurait reçu à cet instant, et on appelle
les MÊMES fonctions qu'en direct : analyse_l1, analyse_clf, analyse_cme (collecteur.py) et traiter (alertes.py).
Rien n'est envoyé : les appels à GitHub sont interceptés et enregistrés.

Ce que le collecteur aurait reçu à l'instant t :
  - vent solaire à L1 : OMNI 1 min ramené à l'instant de mesure à L1 (t_L1 = t_OMNI - Timeshift),
    disponible 2 min après la mesure (latence observée du flux temps réel) ;
  - Chambon : données définitives, disponibles 15 min après la mesure (latence du flux provisoire) ;
  - CME : simulations WSA-ENLIL terminées avant t, calculées dans les 7 jours précédents ;
  - Kp prévu : pas d'archive simple des prévisions NOAA ; la veille Kp n'est pas rejouée.

Différences avec le direct, à garder en tête : OMNI est une série retraitée (moins bruitée que le temps réel),
et Chambon définitif est plus propre que le provisoire. Le rejeu est donc un peu optimiste sur le bruit.

Usage : python rejeu_2024/rejeu.py   (une dizaine de minutes) -> rejeu_2024/resultats/
"""
import bisect
import csv
import gzip
import io
import json
import math
import os
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
import alertes                      # noqa: E402  (le code du service, tel quel)
import collecteur as C              # noqa: E402

DONNEES, SORTIE = ICI / "donnees", ICI / "resultats"
DEBUT, FIN = datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc)
PAS = timedelta(minutes=5)
LATENCE_L1, LATENCE_CLF = timedelta(minutes=2), timedelta(minutes=15)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def date_hapi(s):
    """'2024-01-01T00:00:00.000Z' (OMNI) ou '2024-01-01T00:00Z' (BGS)."""
    return C.date(s)


def lignes_csv(nom):
    with gzip.open(DONNEES / nom, "rt", encoding="utf-8") as f:
        texte = f.read()
    for l in csv.reader(io.StringIO(texte)):
        if l and l[0][:2] == "20":                                          # saute les en-têtes
            yield l


# ---------------------------------------------------------------- 1. Chargement
def charger_l1():
    """OMNI -> enregistrements au format du flux temps réel de la NOAA, datés à l'instant de mesure à L1.

    OMNI est daté au nez du choc d'étrave ; Timeshift (s) est le délai depuis le satellite. Ce délai varie de
    plusieurs minutes d'une minute à l'autre (orientation estimée des fronts) : soustrait tel quel, il disperse
    des minutes consécutives et laisse deux tiers des minutes L1 vides. On le lisse donc par une médiane
    glissante sur 31 min avant de l'appliquer (erreur de quelques minutes sur l'instant d'un choc)."""
    lignes = list(lignes_csv("omni_1min_2024.csv.gz"))
    ts = [float(l[1]) for l in lignes]
    valides = [i for i, v in enumerate(ts) if v < 999999]
    lisse = {}
    for k, i in enumerate(valides):
        fen = [ts[j] for j in valides[max(0, k - 15):k + 16] if abs(j - i) <= 15]
        lisse[i] = statistics.median(fen)
    mag, vent = {}, {}
    for i, (t, _, F, by, bz, V, n) in enumerate(lignes):
        if i not in lisse:
            continue
        tl1 = (date_hapi(t) - timedelta(seconds=lisse[i])).replace(second=0)
        F, by, bz, V, n = float(F), float(by), float(bz), float(V), float(n)
        if F < 9999 and abs(by) < 9999 and abs(bz) < 9999:
            mag[tl1] = {"time_tag": iso(tl1), "active": True, "source": "OMNI-L1", "bt": F, "by_gsm": by, "bz_gsm": bz}
        if V < 99999 and n < 999:
            vent[tl1] = {"time_tag": iso(tl1), "active": True, "source": "OMNI-L1", "proton_speed": V,
                         "proton_density": n}
    return sorted(mag.items()), sorted(vent.items())


def charger_clf():
    m = {}
    for t, X, Y, Z in lignes_csv("clf_1min_2024.csv.gz"):
        X, Y = float(X), float(Y)
        if abs(X) < 88888 and abs(Y) < 88888:
            m[date_hapi(t)] = (X, Y)
    return m


def charger_json(nom):
    with gzip.open(DONNEES / nom, "rt", encoding="utf-8") as f:
        return json.load(f)


def fenetre(serie, temps, debut, fin):
    """Éléments de serie (liste triée de (t, valeur)) avec debut < t <= fin."""
    return [v for _, v in serie[bisect.bisect_right(temps, debut):bisect.bisect_right(temps, fin)]]


# ---------------------------------------------------------------- 2. Rejeu
class GitHubFactice:
    """Remplace alertes.github : enregistre ce qui aurait été envoyé."""

    def __init__(self):
        self.appels, self.n = [], 0
        self.t = None

    def __call__(self, methode, chemin, donnees):
        self.appels.append({"t": iso(self.t), "methode": methode, "chemin": chemin,
                            "titre": donnees.get("title"), "etat": donnees.get("state"),
                            "texte": donnees.get("body") or ""})
        if methode == "POST" and chemin == "/issues":
            self.n += 1
            return {"number": self.n, "html_url": f"episode-{self.n}"}
        return {}


def rejouer():
    print("chargement...")
    mag, vent = charger_l1()
    tmag, tvent = [t for t, _ in mag], [t for t, _ in vent]
    clf = charger_clf()
    tclf = sorted(clf)
    sims = sorted(charger_json("donki_enlil_2024.json.gz"), key=lambda s: s.get("modelCompletionTime") or "")
    tsims = [C.date(s["modelCompletionTime"]) for s in sims]
    print(f"L1 : {len(mag)} min de champ, {len(vent)} min de plasma ; Chambon : {len(clf)} min ; "
          f"{len(sims)} simulations ENLIL")

    faux = GitHubFactice()
    alertes.github = faux
    alertes.ntfy = lambda *a, **k: None
    os.environ.update({"GITHUB_TOKEN": "rejeu", "GITHUB_REPOSITORY": "Rom1cmoi/veille-cig-france"})
    os.environ.pop("ALERTE_TEST", None)
    etat_alerte = Path(tempfile.mkdtemp()) / "alertes.json"

    collectes, horaire = [], []
    t = DEBUT
    while t < FIN:
        faux.t = t
        etat = {"l1": None, "kp": None, "clf": None, "cme": None}
        erreurs = []
        # vent solaire mesuré à L1 jusqu'à t - 2 min ; 3 h suffisent aux fenêtres du modèle
        fin_l1 = t - LATENCE_L1
        m = fenetre(mag, tmag, fin_l1 - timedelta(hours=3), fin_l1)
        w = fenetre(vent, tvent, fin_l1 - timedelta(hours=3), fin_l1)
        if m and w and C.date(m[-1]["time_tag"]) > fin_l1 - timedelta(minutes=30):
            try:
                etat["l1"] = C.analyse_l1(m, w)
            except Exception as e:
                erreurs.append(str(e))
        # Chambon jusqu'à t - 15 min ; la dernière heure suffit
        fin_c = t - LATENCE_CLF
        i0, i1 = bisect.bisect_right(tclf, fin_c - timedelta(minutes=70)), bisect.bisect_right(tclf, fin_c)
        if i1 - i0 >= 2:
            c = C.analyse_clf({tt: clf[tt] for tt in tclf[i0:i1]}, t)
            c.pop("_h"), c.pop("serie")
            etat["clf"] = c
        # CME : simulations terminées avant t, des 7 derniers jours
        j0, j1 = bisect.bisect_right(tsims, t - timedelta(days=7)), bisect.bisect_right(tsims, t)
        etat["cme"] = C.analyse_cme(sims[j0:j1], t)

        sig = alertes.signaux(etat, t)                                       # pour l'analyse (traiter refait le même calcul)
        resume = alertes.traiter(etat, t, etat_alerte, erreurs)
        l1, c = etat["l1"] or {}, etat["clf"] or {}
        collectes.append([iso(t), l1.get("dbdt_med"), l1.get("dbdt_p90"), (l1.get("choc") or {}).get("vu_a_L1"),
                          (l1.get("choc") or {}).get("saut_V"), c.get("dbdt_max_1h"),
                          len((etat["cme"] or {}).get("attendues", [])), (resume or {}).get("niveau"),
                          "|".join(f"{x['cle']}:{x['niveau']}" for x in sig)])
        if t.minute == 0 and l1:
            horaire.append({"heure": iso(t), "prevu_med": l1["dbdt_med"], "prevu_p90": l1["dbdt_p90"]})
        if t.day == 1 and t.hour == 0 and t.minute == 0:
            print(t.strftime("%Y-%m"), f"{len(faux.appels)} appels GitHub simulés")
        t += PAS

    # dB/dt mesuré, minute par minute, pour la vérification
    h = {}
    for a, b in zip(tclf[:-1], tclf[1:]):
        if b - a == timedelta(minutes=1):
            h[b] = math.hypot(clf[b][0] - clf[a][0], clf[b][1] - clf[a][1])
    for r in horaire:
        t0 = C.date(r["heure"])
        v = [h[t0 + timedelta(minutes=k)] for k in range(60) if t0 + timedelta(minutes=k) in h]
        r["observe"] = round(max(v), 1) if len(v) >= 54 else None

    SORTIE.mkdir(exist_ok=True)
    with gzip.open(SORTIE / "collectes_2024.csv.gz", "wt", encoding="utf-8") as f:
        f.write("t,dbdt_med,dbdt_p90,choc_vu_a_L1,choc_saut_V,clf_max_1h,cme_attendues,alerte,signaux\n")
        for l in collectes:
            f.write(",".join("" if x is None else str(x) for x in l) + "\n")
    (SORTIE / "horaire_2024.json").write_text(json.dumps(horaire))
    (SORTIE / "appels_github_2024.json").write_text(json.dumps(faux.appels, ensure_ascii=False, indent=0))
    with gzip.open(SORTIE / "dbdt_chambon_2024.csv.gz", "wt") as f:
        f.write("t,h\n" + "".join(f"{iso(k)},{v:.2f}\n" for k, v in sorted(h.items())))
    print(f"terminé : {len(collectes)} collectes, {len(horaire)} heures, {len(faux.appels)} appels GitHub simulés")


if __name__ == "__main__":
    rejouer()
