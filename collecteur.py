"""
Collecteur temps réel de Veille CIG France.

Toutes les 5 minutes (GitHub Actions), ce script :
  1. lit le vent solaire mesuré à L1 (NOAA SWPC, flux RTSW à la minute : SOLAR-1, DSCOVR, ACE, IMAP) ;
  2. lit le Kp observé et prévu à 3 jours (NOAA SWPC) ;
  3. lit le magnétomètre de Chambon-la-Forêt en quasi temps réel (INTERMAGNET, serveur BGS) ;
  4. applique les modèles du rapport (chapitre 4) : vent solaire -> dB/dt et Kp -> dB/dt ;
  5. écrit docs/etat_courant.json (lu par la page) et tient docs/historique.json
     (prévision de chaque heure comparée au dB/dt mesuré ensuite : auto-validation).

Bibliothèque standard uniquement : rien à installer.
Usage :
  python collecteur.py                  # mode normal (internet)
  python collecteur.py --demo           # rejoue le 10 mai 2024 à 16:35 UTC (fichiers de demo/)
"""
import json
import math
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "docs"

URL_MAG = "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"
URL_VENT = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
URL_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
URL_CLF = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002"
           "&observatoryIagaCode=CLF&samplesPerDay=minute&dataStartDate={debut}&dataDuration=1"
           "&publicationState=best-avail&orientation=native")

# ---------------------------------------------------------------- modèles du rapport (chapitre 4)
# Vent solaire (version « opérationnelle » : seules les données disponibles à l'instant de la prévision)
# log10(max dB/dt sur l'heure) = c0 + c1 log10(Newell moyen 2 h) + c2 saut de sqrt(P) sur 10 min + c3 sqrt(P) moyen 1 h
COEF_L1 = [-0.7237, 0.2942, 0.2668, 0.1258]
SIGMA_L1 = 0.3249                      # écart type en validation croisée (dex)
# Kp : log10(max dB/dt sur 3 h) = a + b Kp
KP_A, KP_B, KP_SIGMA = -0.1123, 0.2124, 0.2642
SIGMA_KP_PREVU = 1.0                   # incertitude supposée d'un Kp prévu (± 1 point)
Z90 = 1.2816                           # quantile 90 % de la loi normale
SEUIL_CHOC = 0.6                       # saut de sqrt(P) sur 10 min (nPa^0.5) qui signale un choc


# ---------------------------------------------------------------- petites fonctions utilitaires
def lire_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def date(s):
    """Texte ISO -> datetime UTC (accepte '2026-10-06T11:11:02', '...Z', '2026-10-06 11:11:00.000')."""
    s = s.strip().replace("Z", "").replace(" ", "T")
    return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def moyenne(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def arrondi(x, n=2):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- 1. vent solaire à L1
def minutes_actives(enregistrements, champs):
    """Garde, minute par minute, le satellite marqué « actif » par la NOAA (sinon le premier disponible)."""
    par_minute = {}
    for e in enregistrements:
        if any(e.get(c) is None for c in champs):
            continue
        t = date(e["time_tag"]).replace(second=0)
        deja = par_minute.get(t)
        if deja is None or (e.get("active") and not deja.get("active")):
            par_minute[t] = e
    return par_minute


def blocs_5min(serie):
    """{minute: valeur} -> {début de bloc de 5 min: moyenne}, comme les données OMNI du rapport."""
    blocs = {}
    for t, v in serie.items():
        b = t.replace(minute=t.minute - t.minute % 5)
        blocs.setdefault(b, []).append(v)
    return {b: sum(v) / len(v) for b, v in sorted(blocs.items())}


def newell(V, by, bz):
    """Fonction de couplage de Newell et al. (2007)."""
    bt = math.hypot(by, bz)
    theta = math.atan2(by, bz)
    return V ** (4 / 3) * bt ** (2 / 3) * abs(math.sin(theta / 2)) ** (8 / 3)


def analyse_l1(mag, vent):
    m = minutes_actives(mag, ["by_gsm", "bz_gsm"])
    w = minutes_actives(vent, ["proton_speed", "proton_density"])
    communes = sorted(set(m) & set(w))
    if not communes:
        raise ValueError("pas de minute commune champ magnétique / plasma")
    t_fin = communes[-1]
    V = {t: w[t]["proton_speed"] for t in communes}
    n = {t: w[t]["proton_density"] for t in communes}
    by = {t: m[t]["by_gsm"] for t in communes}
    bz = {t: m[t]["bz_gsm"] for t in communes}
    P = {t: 2e-6 * n[t] * V[t] ** 2 for t in communes}                    # pression dynamique (nPa)
    phi = {t: newell(V[t], by[t], bz[t]) for t in communes}

    # Prédicteurs du rapport, calculés sur des moyennes de 5 min (comme OMNI)
    P5, phi5 = blocs_5min(P), blocs_5min(phi)
    sqP5 = {t: math.sqrt(p) for t, p in P5.items()}
    fen2h = [v for t, v in phi5.items() if t > t_fin - timedelta(hours=2)]
    fen1h = [v for t, v in sqP5.items() if t > t_fin - timedelta(hours=1)]
    sauts = []                                                              # saut de sqrt(P) sur ~10 min
    for t, v in sqP5.items():
        if t <= t_fin - timedelta(hours=1):
            continue
        # valeur de référence : le bloc le plus récent situé 5 à 20 min avant (tolère les trous de données)
        avant = [u for tb, u in sqP5.items() if t - timedelta(minutes=20) <= tb <= t - timedelta(minutes=5)]
        if avant:
            sauts.append((v - avant[-1], t))
    saut, t_saut = max(sauts) if sauts else (0.0, None)
    phi_moy = max(100.0, moyenne(fen2h))
    mu = (COEF_L1[0] + COEF_L1[1] * math.log10(phi_moy) + COEF_L1[2] * max(0.0, saut)
          + COEF_L1[3] * moyenne(fen1h))

    # Délai L1 -> Terre (1,4 million de km jusqu'au choc d'étrave), vitesse moyenne des 30 dernières minutes
    V30 = moyenne([v for t, v in V.items() if t > t_fin - timedelta(minutes=30)])
    delai = min(60.0, max(15.0, 1.4e6 / V30 / 60))
    choc = None
    if saut >= SEUIL_CHOC:
        choc = {"vu_a_L1": iso(t_saut), "arrivee_estimee": iso(t_saut + timedelta(minutes=delai)),
                "saut_racine_P": arrondi(saut)}

    derniere = m[t_fin]
    serie = [{"t": iso(t), "V": arrondi(V[t], 0), "n": arrondi(n[t], 1), "Bz": arrondi(bz[t], 1),
              "P": arrondi(P[t], 2)} for t in communes if t > t_fin - timedelta(hours=6)]
    return {
        "source": derniere.get("source"), "derniere_mesure": iso(t_fin),
        "V": arrondi(V30, 0), "n": arrondi(moyenne([n[t] for t in communes[-30:]]), 1),
        "Bz": arrondi(bz[t_fin], 1), "By": arrondi(by[t_fin], 1), "P": arrondi(P[t_fin], 2),
        "newell_2h": arrondi(phi_moy, 0), "delai_min": round(delai),
        "arrivee": iso(t_fin + timedelta(minutes=delai)), "choc": choc,
        "dbdt_med": arrondi(10 ** mu, 1), "dbdt_p90": arrondi(10 ** (mu + Z90 * SIGMA_L1), 1),
        "serie": serie[::5],                                                # une valeur toutes les 5 min
    }


# ---------------------------------------------------------------- 2. Kp observé et prévu
def analyse_kp(donnees, maintenant):
    lignes = []
    for e in donnees:
        if isinstance(e, dict):
            t, kp, statut = e.get("time_tag"), e.get("kp"), e.get("observed")
        else:                                                               # ancien format : listes
            if e[0] == "time_tag":
                continue
            t, kp, statut = e[0], e[1], e[2]
        if t is None or kp is None:
            continue
        lignes.append({"t": date(t), "kp": float(kp), "statut": statut})
    obs = [l for l in lignes if l["statut"] in ("observed", "estimated") and l["t"] <= maintenant]
    futur = [l for l in lignes if l["t"] + timedelta(hours=3) > maintenant]

    def dbdt(kp, sigma_kp):
        mu = KP_A + KP_B * kp
        s = math.sqrt(KP_SIGMA ** 2 + (KP_B * sigma_kp) ** 2)
        return arrondi(10 ** mu, 1), arrondi(10 ** (mu + Z90 * s), 1)

    def pic(heures):
        f = [l for l in futur if l["t"] < maintenant + timedelta(hours=heures)]
        if not f:
            return None
        l = max(f, key=lambda x: x["kp"])
        med, p90 = dbdt(l["kp"], 0.0 if l["statut"] == "observed" else SIGMA_KP_PREVU)
        return {"t": iso(l["t"]), "kp": l["kp"], "statut": l["statut"], "dbdt_med": med, "dbdt_p90": p90}

    dernier = obs[-1] if obs else None
    return {
        "observe": {"t": iso(dernier["t"]), "kp": dernier["kp"]} if dernier else None,
        "pic_24h": pic(24), "pic_72h": pic(72),
        "serie": [{"t": iso(l["t"]), "kp": l["kp"], "statut": l["statut"]}
                  for l in lignes if l["t"] > maintenant - timedelta(hours=24)],
    }


# ---------------------------------------------------------------- 3. Chambon-la-Forêt
def lire_iaga(texte):
    """Format IAGA-2002 : DATE TIME DOY X Y Z G. Les minutes manquantes valent 99999."""
    mesures = {}
    for ligne in texte.splitlines():
        p = ligne.split()
        if len(p) >= 6 and len(p[0]) == 10 and p[0][4] == "-" and p[0][7] == "-":
            try:
                X, Y = float(p[3]), float(p[4])
            except ValueError:
                continue
            if abs(X) < 88888 and abs(Y) < 88888:
                mesures[date(p[0] + "T" + p[1])] = (X, Y)
    return mesures


def analyse_clf(mesures, maintenant):
    if len(mesures) < 2:
        raise ValueError("pas de données récentes à Chambon")
    temps = sorted(mesures)
    h = {}                                                                  # dB/dt horizontal (nT/min)
    for a, b in zip(temps[:-1], temps[1:]):
        if b - a == timedelta(minutes=1):
            dX, dY = mesures[b][0] - mesures[a][0], mesures[b][1] - mesures[a][1]
            h[b] = (math.hypot(dX, dY), dX, dY)
    t_fin = temps[-1]
    recents = {t: v for t, v in h.items() if t > t_fin - timedelta(hours=1)}
    t_max = max(recents, key=lambda t: recents[t][0]) if recents else None
    theta, periode = None, None
    if t_max is not None:
        hmax, dX, dY = recents[t_max]
        theta = math.degrees(math.atan2(dY, dX)) % 180                       # 0° = variation nord-sud
        if hmax >= 5:                                                       # période de Rice sur l'heure
            fen = [t for t in temps if t > t_fin - timedelta(hours=1)]
            c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
            b = [mesures[t][0] * c + mesures[t][1] * s for t in fen]
            k = list(range(len(b)))
            km, bm = moyenne(k), moyenne(b)
            pente = sum((x - km) * (y - bm) for x, y in zip(k, b)) / max(1e-9, sum((x - km) ** 2 for x in k))
            r = [y - bm - pente * (x - km) for x, y in zip(k, b)]
            d = [r2 - r1 for r1, r2 in zip(r[:-1], r[1:])]
            vb, vd = moyenne([x * x for x in r]), moyenne([x * x for x in d])
            if vd and vd > 0:
                periode = 2 * math.pi * math.sqrt(vb / vd)
    return {
        "derniere_mesure": iso(t_fin), "retard_min": round((maintenant - t_fin).total_seconds() / 60),
        "dbdt_max_1h": arrondi(recents[t_max][0], 1) if t_max else None, "heure_max": iso(t_max),
        "theta": arrondi(theta, 0), "periode_min": arrondi(periode, 1),
        "serie": [{"t": iso(t), "h": arrondi(v[0], 1)} for t, v in sorted(h.items())
                  if t > t_fin - timedelta(hours=6)],
        "_h": {t: v[0] for t, v in h.items()},                              # usage interne (historique)
    }


# ---------------------------------------------------------------- 4. auto-validation
def mettre_a_jour_historique(hist, maintenant, l1, clf_h):
    """Une ligne par heure : prévision émise au début de l'heure, puis dB/dt maximal mesuré pendant l'heure."""
    heure = maintenant.replace(minute=0, second=0, microsecond=0)
    cle = iso(heure)
    # GitHub retarde souvent ses lancements de 10 à 20 min : on accepte la première collecte
    # des 30 premières minutes de l'heure, et on note avec quel retard la prévision a été émise.
    if l1 and cle not in hist and maintenant - heure < timedelta(minutes=30):
        hist[cle] = {"prevu_med": l1["dbdt_med"], "prevu_p90": l1["dbdt_p90"], "observe": None,
                     "emise_min": int((maintenant - heure).total_seconds() // 60)}
    for k, ligne in hist.items():
        debut = date(k)
        if ligne["observe"] is None and clf_h and debut + timedelta(hours=1) <= maintenant:
            valeurs = [v for t, v in clf_h.items() if debut <= t < debut + timedelta(hours=1)]
            if len(valeurs) >= 54:                                          # au moins 90 % de l'heure
                ligne["observe"] = round(max(valeurs), 1)
    limite = maintenant - timedelta(days=14)
    return {k: v for k, v in sorted(hist.items()) if date(k) > limite}


# ---------------------------------------------------------------- programme principal
def main():
    demo = "--demo" in sys.argv
    SORTIE.mkdir(exist_ok=True)
    if demo:
        d = ICI / "demo"
        maintenant = datetime(2024, 5, 10, 16, 35, tzinfo=timezone.utc)
        sources = {"mag": json.loads((d / "rtsw_mag_1m.json").read_text()),
                   "vent": json.loads((d / "rtsw_wind_1m.json").read_text()),
                   "kp": json.loads((d / "kp.json").read_text()),
                   "clf": (d / "clf.iaga").read_text()}
    else:
        maintenant = datetime.now(timezone.utc)
        debut = (maintenant - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:00Z")  # le serveur BGS refuse les secondes
        sources, erreurs_lecture = {}, []
        for cle, url, est_json in (("mag", URL_MAG, True), ("vent", URL_VENT, True), ("kp", URL_KP, True),
                                    ("clf", URL_CLF.format(debut=debut), False)):
            try:
                texte = lire_url(url)
                sources[cle] = json.loads(texte) if est_json else texte
            except Exception as e:                                          # une source en panne ne bloque pas les autres
                erreurs_lecture.append(f"{cle} : {e}")

    erreurs = [] if demo else erreurs_lecture
    etat = {"genere": iso(maintenant), "demo": demo, "l1": None, "kp": None, "clf": None}
    for cle, besoins, fonction in (("l1", ("mag", "vent"), lambda: analyse_l1(sources["mag"], sources["vent"])),
                                   ("kp", ("kp",), lambda: analyse_kp(sources["kp"], maintenant)),
                                   ("clf", ("clf",), lambda: analyse_clf(lire_iaga(sources["clf"]), maintenant))):
        if any(k not in sources for k in besoins):                          # source illisible : déjà signalée
            continue
        try:
            etat[cle] = fonction()
        except Exception as e:
            erreurs.append(f"{cle} : {e}")
    clf_h = etat["clf"].pop("_h") if etat["clf"] else None

    fichier_hist = SORTIE / ("historique_demo.json" if demo else "historique.json")
    hist = json.loads(fichier_hist.read_text()) if fichier_hist.exists() else {}
    hist = mettre_a_jour_historique(hist, maintenant, etat["l1"], clf_h)
    fichier_hist.write_text(json.dumps(hist, indent=0))
    etat["historique"] = [{"heure": k, **v} for k, v in list(hist.items())[-48:]]
    etat["erreurs"] = erreurs

    nom = "etat_demo.json" if demo else "etat_courant.json"
    (SORTIE / nom).write_text(json.dumps(etat, ensure_ascii=False, separators=(",", ":")))
    l1, clf = etat["l1"] or {}, etat["clf"] or {}
    print(f"{nom} écrit à {iso(maintenant)} | L1 {l1.get('source')} {l1.get('derniere_mesure')} "
          f"dB/dt prévu {l1.get('dbdt_med')} (P90 {l1.get('dbdt_p90')}) | Chambon {clf.get('dbdt_max_1h')} nT/min, "
          f"retard {clf.get('retard_min')} min | erreurs : {erreurs or 'aucune'}")


if __name__ == "__main__":
    main()
