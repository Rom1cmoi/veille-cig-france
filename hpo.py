"""
Indice ap30 (et Hp30) du GFZ : outil de lecture pour l'exploitant, en plus du Kp (qui reste l'entrée des prévisions).

ap30 / Hp30 (Yamazaki et al., 2024 ; GFZ, licence CC BY 4.0) : comme le Kp, une mesure de l'agitation magnétique de la
planète, mais par demi-heure au lieu de 3 h, et sans plafond à 9. ap30 est la version linéaire de Hp30.

Ce que l'ap30 veut dire à Chambon : table établie sur les 46 tempêtes de Kp >= 8- depuis 2000 (4 421 demi-heures,
calc/ap30_dbdt.py). Pour chaque classe d'ap30 : dB/dt maximal de la demi-heure à Chambon (médiane et P90), et part des
demi-heures au-delà des seuils jaune (6,8 nT/min, soit 1 A au poste le plus exposé dans la pire direction), 30 nT/min et
orange (68 nT/min, 10 A). L'ap30 est un indice planétaire, mesuré après coup : il situe la tempête, il ne la prévoit
pas, et ne peut pas annoncer l'orange à lui seul (au mieux 1 demi-heure sur 10 au-delà de 300).

Bibliothèque standard uniquement.
"""
import json
from datetime import datetime, timedelta, timezone

URL = "https://kp.gfz.de/app/json/?start={a}&end={b}&index={i}"
CACHE_MIN = 10                        # le GFZ publie une valeur par demi-heure : inutile d'interroger plus souvent
# borne basse d'ap30, libellé Hp30, dB/dt médian et P90 sur 30 min (nT/min), % de demi-heures >= jaune, >= 30, >= orange
CLASSES = [
    (0, "Hp30 < 4", 1.7, 3.7, 1, 0, 0),
    (27, "Hp30 4 à 5-", 3.7, 7.7, 15, 0, 0),
    (48, "Hp30 5 à 6-", 5.7, 12.4, 39, 0.2, 0),
    (80, "Hp30 6 à 7-", 7.7, 16.9, 61, 1, 0),
    (132, "Hp30 7 à 8-", 13.0, 30.0, 85, 10, 1),
    (207, "Hp30 8 à 9", 18.8, 47.9, 97, 22, 4),
    (300, "Hp30 > 9", 33.5, 67.6, 100, 56, 10),
]


def classe(ap30):
    """La ligne de CLASSES qui contient cet ap30, sous forme de dict."""
    c = [x for x in CLASSES if ap30 >= x[0]][-1]
    i = CLASSES.index(c)
    haut = CLASSES[i + 1][0] if i + 1 < len(CLASSES) else None
    return {"ap30_min": c[0], "ap30_max": haut, "hp30": c[1], "dbdt_med": c[2], "dbdt_p90": c[3],
            "pct_jaune": c[4], "pct_30": c[5], "pct_orange": c[6]}


def lire_series(maintenant, lire_url):
    """Hp30 et ap30 des dernières 24 h -> liste de {t, Hp30, ap30} (t = début de la demi-heure, UTC)."""
    a = (maintenant - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:00Z")
    b = maintenant.strftime("%Y-%m-%dT%H:%M:00Z")
    val = {}
    for i in ("Hp30", "ap30"):
        d = json.loads(lire_url(URL.format(a=a, b=b, i=i)))
        for t, v in zip(d["datetime"], d[i]):
            if v is not None and v >= 0:                                 # -1 : valeur manquante
                val.setdefault(t, {})[i] = v
    return [{"t": t, **v} for t, v in sorted(val.items()) if "Hp30" in v and "ap30" in v]


def analyse_hpo(maintenant, precedent, lire_url):
    """Point d'entrée du collecteur. Réutilise le résultat précédent s'il a moins de CACHE_MIN minutes."""
    if precedent and precedent.get("lu") and \
            maintenant - datetime.fromisoformat(precedent["lu"].replace("Z", "+00:00")) < timedelta(minutes=CACHE_MIN):
        return precedent
    serie = lire_series(maintenant, lire_url)
    if not serie:
        raise ValueError("aucune valeur Hp30 / ap30 sur 24 h")
    der = serie[-1]
    fin = datetime.fromisoformat(der["t"].replace("Z", "+00:00")) + timedelta(minutes=30)
    pic = max(serie[-6:], key=lambda x: x["ap30"])                       # plus forte des 3 dernières heures
    return {"lu": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"), "serie": serie, "dernier": der,
            "retard_min": round((maintenant - fin).total_seconds() / 60), "classe": classe(der["ap30"]),
            "max_3h": pic, "classe_max_3h": classe(pic["ap30"]),
            "table": [classe(x[0]) for x in CLASSES],
            "source": "GFZ Potsdam, indices Hp30/ap30 (nowcast, CC BY 4.0)"}
