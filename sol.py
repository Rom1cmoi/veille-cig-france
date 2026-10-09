"""
Courant induit « maintenant » dans chaque poste 400 kV, calculé à partir de 6 magnétomètres (même méthode que les
rejeux de la page) au lieu du seul Chambon-la-Forêt.

Méthode (filtres préparés une fois par calc/filtres_sol.py, fichier filtres_sol.json) :
  I_k(t) = Σ_o Σ_c Σ_j h[k][o][c][j] · b_oc(t - j)
  k : poste ; o : observatoire (HAD, DOU, CLF, FUR, EBR, SPT) ; c : composante X ou Y ; j : retard de 0 à 239 min ;
  b : variation du champ depuis le début de la fenêtre (nT). Les filtres h contiennent toute la chaîne des rejeux :
  pondération des observatoires en 1/d², sol EURHOM, lignes 400 kV, résolution nodale (cas de base). Causaux, ils
  n'utilisent que le passé : c'est ce qui permet de les appliquer en direct.

Données manquantes : plusieurs observatoires publient avec des heures, voire des jours de retard. Pour chaque minute
où un observatoire n'a pas de mesure, on prend la variation (B(t) - B(t-1)) de l'observatoire disponible le plus
proche, y compris WNG (Wingst) et SFS (San Fernando), qui publient vite. La part de minutes réellement mesurées par
observatoire est indiquée dans la sortie.

Bibliothèque standard uniquement.
"""
import json
import math
import operator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent
URL = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002"
       "&observatoryIagaCode={o}&samplesPerDay=minute&dataStartDate={debut}&dataDuration=1"
       "&publicationState=best-avail&orientation=native")
REMPLACANTS = {"WNG": (53.743, 9.073), "SFS": (36.665, -6.209)}   # ne servent qu'à combler les trous
FENETRE = 60                                                      # minutes : maximum sur la dernière heure
CACHE_MIN = 10                                                    # on ne recalcule que toutes les 10 min

_F = None


def filtres():
    """Charge filtres_sol.json une fois ; filtres retournés (pour un produit scalaire direct avec le passé)."""
    global _F
    if _F is None:
        d = json.loads((ICI / "filtres_sol.json").read_text())
        e = d["echelle"]
        d["h"] = [[[[x * e for x in reversed(hc)] for hc in ho] for ho in hk] for hk in d["h"]]
        _F = d
    return _F


def dist_km(a, b):
    p1, p2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371 * math.acos(max(-1.0, min(1.0, c)))


def lire_xy(texte):
    """IAGA-2002 -> {minute (datetime UTC): (X, Y) en nT} ; convertit H, D (minutes d'arc) si l'observatoire publie en HDZ."""
    hdz = any("Reported" in l and l.split()[1].startswith("HDZ") for l in texte.splitlines()[:30] if len(l.split()) > 1)
    out = {}
    for l in texte.splitlines():
        p = l.split()
        if len(p) < 6 or len(p[0]) != 10 or p[0][4] != "-":
            continue
        try:
            a, b = float(p[3]), float(p[4])
        except ValueError:
            continue
        if abs(a) >= 88888 or abs(b) >= 88888:
            continue
        if hdz:
            d = math.radians(b / 60)
            a, b = a * math.cos(d), a * math.sin(d)
        t = datetime.fromisoformat(p[0] + "T" + p[1][:5]).replace(tzinfo=timezone.utc)
        out[t] = (a, b)
    return out


def telecharger(codes, debut, lire_url):
    def un(o):
        try:
            return o, lire_xy(lire_url(URL.format(o=o, debut=debut)))
        except Exception:
            return o, {}
    with ThreadPoolExecutor(max_workers=len(codes)) as ex:
        return dict(ex.map(un, codes))


def calculer(mesures, ntap=None):
    """mesures : {code: {minute: (X, Y)}}. Renvoie le résultat (dict) ou lève ValueError si rien d'exploitable."""
    F = filtres()
    obs = F["obs"]
    ntap = F["ntap"]
    positions = {**{o: tuple(v) for o, v in obs.items()}, **REMPLACANTS}
    dernieres = {o: max(m) for o, m in mesures.items() if m}
    if not dernieres:
        raise ValueError("aucun magnétomètre disponible")
    t_fin = dernieres.get("CLF") or max(dernieres.values())
    n = ntap + FENETRE
    temps = [t_fin - timedelta(minutes=n - 1 - i) for i in range(n)]

    def increment(o, t):
        m = mesures.get(o) or {}
        a, b = m.get(t), m.get(t - timedelta(minutes=1))
        return None if a is None or b is None else (a[0] - b[0], a[1] - b[1])

    b, reel, remplace = {}, {}, {}
    for o in obs:
        voisins = sorted((dist_km(positions[o], positions[v]), v) for v in positions if v != o)
        x = y = 0.0
        bx, by, nr = [], [], 0
        for i, t in enumerate(temps):
            d = increment(o, t) if i else (0.0, 0.0)
            if d is None:
                for _, v in voisins:
                    d = increment(v, t)
                    if d is not None:
                        remplace[o] = remplace.get(o) or v
                        break
            elif i >= ntap:
                nr += 1
            d = d or (0.0, 0.0)
            x += d[0]; y += d[1]
            bx.append(x); by.append(y)
        b[o] = (bx, by)
        reel[o] = round(nr / FENETRE, 2)

    I_max, k_max, i_nat, t_nat = [], None, 0.0, None
    serie_nat = [0.0] * FENETRE
    for k, hk in enumerate(F["h"]):
        best, t_best = 0.0, None
        for j in range(FENETRE):
            fin = ntap + j + 1
            v = 0.0
            for o, ho in zip(obs, hk):
                bx, by = b[o]
                v += sum(map(operator.mul, ho[0], bx[fin - ntap:fin])) + sum(map(operator.mul, ho[1], by[fin - ntap:fin]))
            v = abs(v)
            serie_nat[j] = max(serie_nat[j], v)
            if v > best:
                best, t_best = v, temps[ntap + j]
        I_max.append(round(best, 2))
        if best > i_nat:
            i_nat, k_max, t_nat = best, k, t_best
    return {"t_fin": t_fin.strftime("%Y-%m-%dT%H:%M:%SZ"), "fenetre_min": FENETRE,
            "I": I_max, "max": round(i_nat, 2), "poste_max": k_max, "lieu_max": F["lieux"][k_max] if k_max is not None else None,
            "heure_max": t_nat.strftime("%Y-%m-%dT%H:%M:%SZ") if t_nat else None,
            "serie_max": [round(v, 2) for v in serie_nat],
            "part_mesuree": reel, "remplacants": remplace,
            "dernieres": {o: t.strftime("%Y-%m-%dT%H:%M:%SZ") for o, t in dernieres.items()}}


def analyse_sol(texte_clf, maintenant, precedent, lire_url):
    """Point d'entrée du collecteur. Réutilise le calcul précédent s'il a moins de CACHE_MIN minutes."""
    if precedent and precedent.get("calcule") and \
            maintenant - datetime.fromisoformat(precedent["calcule"].replace("Z", "+00:00")) < timedelta(minutes=CACHE_MIN):
        return precedent
    F = filtres()
    debut = (maintenant - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:00Z")
    codes = [o for o in list(F["obs"]) + list(REMPLACANTS) if o != "CLF"]
    mesures = telecharger(codes, debut, lire_url)
    mesures["CLF"] = lire_xy(texte_clf) if texte_clf else telecharger(["CLF"], debut, lire_url)["CLF"]
    r = calculer(mesures)
    r["calcule"] = maintenant.strftime("%Y-%m-%dT%H:%M:%SZ")
    return r
