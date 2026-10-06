"""
Validation en conditions réelles du modèle « L1 opérationnel » (chapitre 4 du rapport).

Lit docs/historique.json : une ligne par heure, avec la prévision émise en début d'heure (médiane et P90)
et le dB/dt maximal mesuré ensuite à Chambon pendant cette heure. Calcule les mêmes indicateurs que le
rapport, pour pouvoir les comparer directement :
  - r       : corrélation entre log10(prévu médian) et log10(mesuré) ;
  - RMSE    : écart quadratique moyen en log10 (« dex ») ; 0,30 dex = facteur 2 ;
  - biais   : moyenne de log10(mesuré / prévu), donnée comme un facteur (> 1 : le modèle sous-estime) ;
  - couverture P90 : part des heures où le mesuré reste sous le P90 (90 % attendus) ;
  - POD / FAR pour l'alerte « P90 prévu >= 30 nT/min » :
      POD = heures >= 30 nT/min qui avaient été annoncées / toutes les heures >= 30 nT/min ;
      FAR = annonces suivies d'une heure < 30 nT/min / toutes les annonces.

Usage : python validation.py   (affiche le bilan) ; collecteur.py l'appelle aussi à chaque collecte.
"""
import json
import math
from pathlib import Path

SEUIL_ALERTE = 30.0                     # nT/min, seuil utilisé dans le rapport
RAPPORT = {"r": 0.79, "rmse": 0.325, "couverture_p90": 0.94, "pod": 0.87, "far": 0.60}   # validation croisée, 11 orages


def bilan(hist, retard_max=None):
    """hist : {heure: {prevu_med, prevu_p90, observe, emise_min}}. retard_max : ne garder que les prévisions
    émises au plus tant de minutes après le début de l'heure (les plus tardives ont déjà vu une partie de l'heure)."""
    L = [v for v in hist.values() if v.get("observe") and v.get("prevu_med")
         and (retard_max is None or v.get("emise_min", 0) <= retard_max)]
    n = len(L)
    if n == 0:
        return {"n": 0}
    x = [math.log10(v["prevu_med"]) for v in L]
    y = [math.log10(max(v["observe"], 0.1)) for v in L]
    e = [b - a for a, b in zip(x, y)]
    biais = sum(e) / n
    rmse = math.sqrt(sum(d * d for d in e) / n)
    r = None
    if n >= 3:
        mx, my = sum(x) / n, sum(y) / n
        sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
        sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
        r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None
    obs = [v["observe"] >= SEUIL_ALERTE for v in L]
    ann = [v["prevu_p90"] >= SEUIL_ALERTE for v in L]
    n_obs, n_ann = sum(obs), sum(ann)
    succes = sum(o and a for o, a in zip(obs, ann))
    return {
        "n": n,
        "r": None if r is None else round(r, 2),
        "rmse": round(rmse, 3),
        "biais_facteur": round(10 ** biais, 2),
        "couverture_p90": round(sum(v["observe"] <= v["prevu_p90"] for v in L) / n, 2),
        "n_obs_30": n_obs, "n_annonces_30": n_ann,
        "pod": round(succes / n_obs, 2) if n_obs else None,
        "far": round((n_ann - succes) / n_ann, 2) if n_ann else None,
        "mesure_max": max(v["observe"] for v in L),
    }


def tout(hist):
    return {"toutes": bilan(hist), "emises_a_l_heure": bilan(hist, retard_max=15), "rapport": RAPPORT}


if __name__ == "__main__":
    h = json.loads((Path(__file__).resolve().parent / "docs" / "historique.json").read_text())
    for nom, b in tout(h).items():
        print(f"{nom:18s}", b)
