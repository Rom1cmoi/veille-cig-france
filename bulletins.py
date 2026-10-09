"""
Bulletins rédigés automatiquement à chaque collecte, pour trois lecteurs (chapitre 2 du rapport) :
  - grand public : la couleur et ce qu'elle veut dire, en heure de Paris, sans jargon ;
  - prévisionniste (Météo-France) : les mesures et les prévisions, avec leurs incertitudes ;
  - exploitant (RTE, EDF) : le courant estimé au poste le plus exposé et les mesures envisageables.

Le niveau est celui de la carte en mode pessimiste : P90 du dB/dt, direction la plus défavorable, période 20 min,
au poste le plus exposé. Ce poste (vallée du Rhône, poste d'évacuation probable de la centrale de Cruas) reçoit
0,147 A par phase pour 1 nT/min à Chambon ; la fourchette Monte-Carlo du rapport va de 0,40 à 1,19 fois cette
valeur (paramètres du poste inconnus).
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:                                                           # repli : heure d'été
    PARIS = timezone(timedelta(hours=2))

COEF_MAX, FOURCHETTE = 0.147, (0.40, 1.19)        # A par nT/min, poste le plus exposé ; facteurs Monte-Carlo
SEUILS_A = (("rouge", 75.0), ("orange", 10.0), ("jaune", 1.0))
# Gazoducs (calc/gaz_reseau.py) : potentiel tube-sol au point le plus exposé (Causses, au sud de Millau), en V par
# nT/min à Chambon, cas de base ; fourchette Monte-Carlo sur les tubes ; seuils provisoires (V), à calibrer.
COEF_GAZ, FOURCHETTE_GAZ = 0.37, (0.38, 1.7)
SEUILS_GAZ = (("rouge", 30.0), ("orange", 10.0), ("jaune", 2.0))
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def date(s):
    s = s.strip().replace("Z", "").replace(" ", "T")
    return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)


def niveau(dbdt):
    """dB/dt à Chambon (nT/min) -> couleur au poste le plus exposé."""
    if dbdt is None:
        return None
    courant = dbdt * COEF_MAX
    return next((n for n, s in SEUILS_A if courant >= s), "vert")


def paris(t, avec_jour=True):
    """'2026-10-09T20:00:00Z' -> 'vendredi 9 octobre vers 22 h' (heure de Paris)."""
    p = date(t).astimezone(PARIS)
    h = f"{p.hour} h" + (f" {p.minute:02d}" if p.minute else "")
    return f"{JOURS[p.weekday()]} {p.day} {MOIS[p.month - 1]} vers {h}" if avec_jour else f"vers {h}"


def utc(t):
    return f"{t[8:10]}/{t[5:7]} {t[11:13]} h {t[14:16]} UTC"


def f(x, n=0):
    return "?" if x is None else (f"{x:.{n}f}".replace(".", ","))


ORDRE = ["vert", "jaune", "orange", "rouge"]
VIGILANCE = {"vert": "verte", "jaune": "jaune", "orange": "orange", "rouge": "rouge"}   # accord : « vigilance verte »
PUBLIC = {
    "vert": "Aucun effet attendu sur le réseau électrique.",
    "jaune": "Activité géomagnétique faible à modérée : de faibles courants peuvent apparaître dans le réseau "
             "électrique, sans conséquence attendue pour les usagers.",
    "orange": "Tempête géomagnétique : des courants notables sont attendus dans le réseau électrique. Les "
              "gestionnaires de réseau sont prévenus ; aucune action n'est demandée au public.",
    "rouge": "Tempête géomagnétique majeure : des perturbations du réseau électrique sont possibles. Suivez les "
             "consignes des autorités.",
}
EXPLOITANT = {
    "vert": "Aucune mesure particulière.",
    "jaune": "Surveillance normale. Vérifier que les mesures de courant de neutre, si elles existent, sont "
             "disponibles et enregistrées.",
    "orange": "Mesures envisageables : reporter les consignations et manœuvres non urgentes sur les postes "
              "exposés ; surveiller la puissance réactive, les harmoniques, les alarmes de gaz dissous et les "
              "déclenchements de protections ; garder une réserve de puissance réactive.",
    "rouge": "En plus des mesures orange : mobiliser les astreintes et préparer des reconfigurations du réseau "
             "pour limiter les longues lignes vers les postes exposés.",
}


def rediger(etat):
    l1, kp, clf, cme = etat.get("l1") or {}, etat.get("kp") or {}, etat.get("clf") or {}, etat.get("cme") or {}
    n_l1, n_clf = niveau(l1.get("dbdt_p90")), niveau(clf.get("dbdt_max_1h"))
    maintenant = max((n for n in (n_l1, n_clf) if n), key=ORDRE.index, default=None)
    attendues = [c for c in cme.get("attendues", []) if (c.get("dans_h") or 0) > -12]
    pic = kp.get("pic_24h") or {}
    n_kp = niveau(pic.get("dbdt_p90"))
    choc = l1.get("choc")

    # ---------------------------------------------------------- grand public
    pub = []
    if maintenant:
        pub.append(f"Vigilance {VIGILANCE[maintenant]} pour l'heure à venir. {PUBLIC[maintenant]}")
    else:
        pub.append("Données insuffisantes pour l'heure à venir.")
    if choc:
        pub.append(f"Les satellites ont mesuré un choc dans le vent solaire : il atteindra la Terre "
                   f"{paris(choc['arrivee_estimee'], avec_jour=False)} (heure de Paris).")
    for k, c in enumerate(attendues[:3]):
        lo, hi = niveau(c["dbdt_p90"].get("90")), niveau(c["dbdt_p90"].get("180"))
        effet = f"de {lo} à {hi}" if lo != hi else lo
        if k == 0:
            pub.append(f"Une éruption solaire (éjection de masse coronale) devrait atteindre la Terre "
                       f"{paris(c['arrivee'])} (heure de Paris), à environ {c['erreur_h']} heures près. Effet attendu "
                       f"sur le réseau : {effet}, selon l'orientation de son champ magnétique, qui ne sera connue "
                       f"qu'une heure avant.")
        else:
            pub.append(f"Une autre éruption devrait arriver {paris(c['arrivee'])} (effet : {effet}).")
    if n_kp in ("orange", "rouge") and not attendues:
        pub.append(f"La NOAA prévoit une activité forte (Kp {f(pic.get('kp'), 1)}) dans les 24 heures.")

    # ---------------------------------------------------------- prévisionniste
    pre = []
    if l1:
        pre.append(f"Vent solaire à L1 ({l1.get('source')}, mesure de {utc(l1['derniere_mesure'])}) : V = {f(l1.get('V'))} "
                   f"km/s, n = {f(l1.get('n'), 1)} cm⁻³, Bz = {f(l1.get('Bz'), 1)} nT, Pdyn = {f(l1.get('P'), 1)} nPa, "
                   f"couplage de Newell sur 2 h = {f(l1.get('newell_2h'))}. dB/dt maximal attendu à Chambon pour "
                   f"l'heure qui commence : {f(l1.get('dbdt_med'), 1)} nT/min en médiane, {f(l1.get('dbdt_p90'), 1)} au "
                   f"P90 (vigilance {VIGILANCE.get(n_l1, n_l1)} dans le cas pessimiste). Arrivée sur Terre de ce vent : {utc(l1['arrivee'])}.")
    else:
        pre.append("Vent solaire à L1 : indisponible.")
    if choc:
        pre.append(f"Choc détecté à L1 à {utc(choc['vu_a_L1'])} (saut de √Pdyn {f(choc.get('saut_racine_P'), 2)} nPa^½, "
                   f"de vitesse {f(choc.get('saut_V'))} km/s) ; arrivée estimée {utc(choc['arrivee_estimee'])}.")
    if kp:
        ob = kp.get("observe") or {}
        p72 = kp.get("pic_72h") or {}
        pre.append(f"Kp : observé {f(ob.get('kp'), 1)} ; maximum prévu sur 24 h {f(pic.get('kp'), 1)} (dB/dt P90 "
                   f"{f(pic.get('dbdt_p90'), 1)} nT/min, vigilance {VIGILANCE.get(n_kp, n_kp)}) ; sur 72 h {f(p72.get('kp'), 1)}.")
    for c in attendues:
        k, p = c["kp"], c["dbdt_p90"]
        details = " (effleurement)" if c.get("effleurement") else ""
        details += " (impact mineur)" if c.get("impact_mineur") else ""
        mp = f" Magnétopause comprimée jusqu'à {f(c['magnetopause_re'], 1)} RT." if c.get("magnetopause_re") else ""
        pre.append(f"CME : choc attendu le {utc(c['arrivee'])} ± {c['erreur_h']} h{details}. Kp WSA-ENLIL "
                   f"{k.get('90')} / {k.get('135')} / {k.get('180')} pour un angle d'horloge de 90° / 135° / 180° ; "
                   f"dB/dt P90 plein sud {f(p.get('180'), 1)} nT/min.{mp} (Simulation {c['simulation']}.)")
    if clf:
        pre.append(f"Constat à Chambon-la-Forêt (provisoire, {clf.get('retard_min')} min de retard) : dB/dt maximal "
                   f"{f(clf.get('dbdt_max_1h'), 1)} nT/min sur la dernière heure, axe {f(clf.get('theta'))}°"
                   f"{', période ' + f(clf.get('periode_min')) + ' min' if clf.get('periode_min') else ''}.")
    v = (etat.get("validation") or {}).get("toutes") or {}
    if v.get("n"):
        pre.append(f"Validation en direct : {v['n']} h vérifiées, couverture du P90 {round(100 * v['couverture_p90'])} %, "
                   f"rapport mesuré / prévu ×{f(v.get('biais_facteur'), 2)}.")

    # ---------------------------------------------------------- exploitant
    ex = []
    if l1.get("dbdt_p90") is not None:
        i = l1["dbdt_p90"] * COEF_MAX
        ex.append(f"Niveau {n_l1} pour l'heure qui commence (cas pessimiste). Courant continu estimé au poste le plus "
                  f"exposé (vallée du Rhône, poste d'évacuation probable de Cruas) : {f(i, 1)} A par phase et par "
                  f"transformateur (fourchette {f(i * FOURCHETTE[0], 1)} à {f(i * FOURCHETTE[1], 1)} A selon les "
                  f"paramètres du poste). Seuils : 1 A jaune (début de saturation), 10 A orange, 75 A rouge.")
    if l1.get("dbdt_p90") is not None:
        v = l1["dbdt_p90"] * COEF_GAZ
        ng = next((n for n, s in SEUILS_GAZ if v >= s), "vert")
        ex.append(f"Gazoducs (NaTran, Teréga) : potentiel tube-sol jusqu'à {f(v, 1)} V au point le plus exposé "
                  f"(Causses, au sud de Millau ; {f(v * FOURCHETTE_GAZ[0], 1)} à {f(v * FOURCHETTE_GAZ[1], 1)} V selon "
                  f"les tubes), niveau {ng} (seuils provisoires 2 / 10 / 30 V ; la protection cathodique tient le "
                  f"tube entre −0,85 et −1,2 V).")
    if clf.get("dbdt_max_1h") is not None:
        ex.append(f"Mesuré sur la dernière heure : {f(clf['dbdt_max_1h'], 1)} nT/min à Chambon, soit au plus "
                  f"{f(clf['dbdt_max_1h'] * COEF_MAX, 1)} A au même poste (direction la plus défavorable).")
    if choc:
        ex.append(f"Choc attendu {utc(choc['arrivee_estimee'])} : pic bref possible à l'arrivée.")
    for c in attendues[:2]:
        ex.append(f"CME attendue le {utc(c['arrivee'])} ± {c['erreur_h']} h : jusqu'à "
                  f"{f(c['dbdt_p90'].get('180', 0) * COEF_MAX, 1)} A si son champ arrive plein sud.")
    pire = max((n for n in (maintenant, n_kp, *(niveau(c["dbdt_p90"].get("180")) for c in attendues)) if n),
               key=ORDRE.index, default="vert")
    ex.append(EXPLOITANT[maintenant or "vert"] + (f" Pour les jours à venir, préparer le niveau {pire}."
                                                  if ORDRE.index(pire) > ORDRE.index(maintenant or "vert") else ""))
    ex.append("Courants estimés par le modèle du rapport (incertitude d'un facteur 3, non validés contre mesure) ; "
              "mesures à valider avec l'exploitant.")

    return {"niveau": maintenant, "niveau_a_venir": pire, "public": " ".join(pub), "previsionniste": "\n".join(pre),
            "exploitant": "\n".join(ex)}
