"""
Bilan du rejeu 2024 (à lancer après rejeu.py) : ce qu'un exploitant demanderait.

  1. Scores horaires de la prévision L1, avec les indicateurs du chapitre 4 (+ seuil orange).
  2. Épisodes d'alerte : combien, ouverts par quel signal, combien suivis d'un vrai dépassement.
  3. Dépassements observés à Chambon (>= 68 nT/min, l'orange) : annoncés ou non, avec quel préavis.
  4. Détecteur de chocs : comparé aux chocs interplanétaires du catalogue DONKI (IPS observés à L1).
  5. CME : erreur sur l'heure d'arrivée (dernière simulation WSA-ENLIL avant le choc), CME manquées, fausses
     annonces, Kp prévu contre Kp observé.

Usage : python rejeu_2024/bilan.py  -> rejeu_2024/resultats/bilan_2024.json (+ affichage)
"""
import bisect
import csv
import gzip
import io
import json
import math
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
import validation                    # noqa: E402
from collecteur import date          # noqa: E402

R, D = ICI / "resultats", ICI / "donnees"
ORANGE, ALERTE30 = 68.0, 30.0


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def gz(chemin):
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- chargement
collectes = list(csv.DictReader(io.StringIO(gz(R / "collectes_2024.csv.gz"))))
for c in collectes:
    c["t"] = date(c["t"])
    c["sig"] = [s.rsplit(":", 1) for s in c["signaux"].split("|") if s]
tcol = [c["t"] for c in collectes]
horaire = json.loads((R / "horaire_2024.json").read_text())
appels = json.loads((R / "appels_github_2024.json").read_text())
h = {}
for l in gz(R / "dbdt_chambon_2024.csv.gz").splitlines()[1:]:
    t, v = l.split(",")
    h[date(t)] = float(v)
th = sorted(h)
ips = [e for e in json.loads(gz(D / "donki_ips_2024.json.gz"))
       if e.get("location") == "Earth" and e["eventTime"].startswith("2024")]
sims = json.loads(gz(D / "donki_enlil_2024.json.gz"))
kp = json.loads(gz(D / "kp_gfz_2024.json.gz"))
kp = sorted((date(t), k) for t, k in zip(kp["datetime"], kp["Kp"]))
import rejeu                         # noqa: E402  (même reconstitution des instants à L1 que le rejeu)
plasma = {t for t, _ in rejeu.charger_l1()[1]}


def hmax(a, b):
    """dB/dt maximal mesuré à Chambon entre a et b."""
    v = [h[t] for t in th[bisect.bisect_left(th, a):bisect.bisect_right(th, b)]]
    return max(v) if v else None


def kp_max(a, b):
    v = [k for t, k in kp if a <= t + timedelta(hours=3) and t <= b]          # créneaux de 3 h qui recoupent [a, b]
    return max(v) if v else None


def type_signal(cle):
    return cle.split()[0]                                                     # choc, l1, clf, cme, kp


res = {}

# ---------------------------------------------------------------- 1. scores horaires
hist = {r["heure"]: {**r, "emise_min": 0} for r in horaire if r.get("observe") is not None}
b = validation.bilan(hist)
L = list(hist.values())
obs68 = [v["observe"] >= ORANGE for v in L]
ann68 = [v["prevu_p90"] >= ORANGE for v in L]
succ = sum(o and a for o, a in zip(obs68, ann68))
b.update({"n_obs_68": sum(obs68), "n_annonces_68": sum(ann68),
          "pod_68": round(succ / sum(obs68), 2) if sum(obs68) else None,
          "far_68": round((sum(ann68) - succ) / sum(ann68), 2) if sum(ann68) else None})
# par niveau d'activité observé
for nom, a, z in (("calme (< 10 nT/min)", 0, 10), ("actif (10-30)", 10, 30), ("orageux (>= 30)", 30, 1e9)):
    sel = {k: v for k, v in hist.items() if a <= v["observe"] < z}
    b[f"strate {nom}"] = validation.bilan(sel)
res["horaire"] = b

# ---------------------------------------------------------------- 2. épisodes
episodes, ouverts = [], {}
for a in appels:
    t = date(a["t"])
    if a["methode"] == "POST" and a["chemin"] == "/issues":
        ouverts[len(ouverts) + 1] = {"debut": t, "titre": a["titre"]}
    elif a["methode"] == "PATCH" and a.get("etat") == "closed":
        n = int(a["chemin"].split("/")[2])
        ouverts[n]["fin"] = t
for n, e in ouverts.items():
    e["fin"] = e.get("fin", datetime(2025, 1, 1, tzinfo=timezone.utc))
    i0, i1 = bisect.bisect_left(tcol, e["debut"]), bisect.bisect_right(tcol, e["fin"])
    premier = {}
    for c in collectes[i0:i1]:
        for cle, niv in c["sig"]:
            premier.setdefault(type_signal(cle), c["t"])
    e["ouvert_par"] = sorted(k for k, t in premier.items() if t == e["debut"])
    e["signaux"] = {k: iso(t) for k, t in premier.items()}
    e["mesure_max"] = hmax(e["debut"], e["fin"])
    e["duree_h"] = round((e["fin"] - e["debut"]).total_seconds() / 3600, 1)
    episodes.append(e)
classe = lambda m: "orange observé" if (m or 0) >= ORANGE else ("30 à 68 nT/min" if (m or 0) >= ALERTE30 else "< 30 nT/min")
res["episodes"] = {
    "nombre": len(episodes),
    "duree_mediane_h": st.median(e["duree_h"] for e in episodes) if episodes else None,
    "par_ouverture": {}, "par_issue": {},
    "liste": [{"debut": iso(e["debut"]), "fin": iso(e["fin"]), "titre": e["titre"], "ouvert_par": e["ouvert_par"],
               "signaux": e["signaux"], "mesure_max": e["mesure_max"], "issue": classe(e["mesure_max"])}
              for e in episodes],
}
for e in res["episodes"]["liste"]:
    k = "+".join(e["ouvert_par"]) or "?"
    res["episodes"]["par_ouverture"][k] = res["episodes"]["par_ouverture"].get(k, 0) + 1
    res["episodes"]["par_issue"][e["issue"]] = res["episodes"]["par_issue"].get(e["issue"], 0) + 1

# ---------------------------------------------------------------- 3. dépassements observés
def evenements(seuil):
    ev, dernier = [], None
    for t in th:
        if h[t] >= seuil:
            if dernier is None or t - dernier > timedelta(hours=3):
                ev.append({"debut": t, "fin": t, "max": h[t]})
            else:
                ev[-1]["fin"], ev[-1]["max"] = t, max(ev[-1]["max"], h[t])
            dernier = t
    return ev


def preavis(ev):
    out = []
    for x in ev:
        T = x["debut"]
        ep = next((e for e in episodes if e["debut"] <= T <= e["fin"]), None)
        r = {"debut": iso(T), "max": round(x["max"], 1), "annonce": ep is not None}
        if ep:
            r["preavis_min"] = round((T - ep["debut"]).total_seconds() / 60)
            r["ouvert_par"] = ep["ouvert_par"]
            for k in ("cme", "choc", "l1", "clf"):
                if k in ep["signaux"] and date(ep["signaux"][k]) <= T:
                    r[f"preavis_{k}_min"] = round((T - date(ep["signaux"][k])).total_seconds() / 60)
        out.append(r)
    return out


res["depassements_orange"] = preavis(evenements(ORANGE))
res["depassements_30"] = preavis(evenements(ALERTE30))

# ---------------------------------------------------------------- 4. détecteur de chocs
det = []
for c in collectes:
    if c["choc_vu_a_L1"]:
        t = date(c["choc_vu_a_L1"])
        if not det or t - det[-1] > timedelta(minutes=60):
            det.append(t)
chocs = sorted(date(e["eventTime"]) for e in ips)
couverts = [t for t in chocs if sum(1 for k in range(-30, 31) if t + timedelta(minutes=k) in plasma) >= 40]
TOL = timedelta(minutes=30)
vus = [t for t in couverts if any(abs(d - t) <= TOL for d in det)]
fausses = [d for d in det if not any(abs(d - t) <= TOL for t in chocs)]
res["chocs"] = {"catalogue_DONKI": len(chocs), "avec_donnees_L1": len(couverts), "detectes": len(vus),
                "pod": round(len(vus) / len(couverts), 2) if couverts else None,
                "detections": len(det), "fausses_detections": len(fausses),
                "far": round(len(fausses) / len(det), 2) if det else None,
                "fausses_par_mois": round(len(fausses) / 12, 1),
                "manques": [iso(t) for t in couverts if t not in vus], "fausses": [iso(t) for t in fausses]}

# ---------------------------------------------------------------- 5. CME
def ids_de(s):
    return {c.get("CMEID") for c in s.get("cmeInputs") or [] if c.get("CMEID")}


sims_t = sorted(sims, key=lambda s: s["modelCompletionTime"])
cas, cme_avec_choc = [], set()
for e in ips:
    T = date(e["eventTime"])
    lies = {x["activityID"] for x in e.get("linkedEvents") or [] if "-CME-" in x["activityID"]}
    if not lies:
        continue
    cme_avec_choc |= lies
    avant = [s for s in sims_t if date(s["modelCompletionTime"]) < T and ids_de(s) & lies]
    impact = [s for s in avant if s.get("estimatedShockArrivalTime")]
    r = {"choc": iso(T), "cme": sorted(lies), "kp_observe_24h": kp_max(T, T + timedelta(hours=24)),
         "dbdt_max_24h": hmax(T, T + timedelta(hours=24))}
    if impact and impact[-1] is avant[-1]:                                     # la dernière simulation prévoit l'impact
        s = impact[-1]
        r.update({"statut": "annoncée", "erreur_h": round((date(s["estimatedShockArrivalTime"]) - T).total_seconds() / 3600, 1),
                  "preavis_h": round((T - date(impact[0]["modelCompletionTime"])).total_seconds() / 3600, 1),
                  "kp_prevu": [s.get("kp_90"), s.get("kp_180")], "effleurement": s.get("isEarthGB")})
    elif avant:
        r["statut"] = "simulée sans impact"
    else:
        r["statut"] = "non simulée"
    cas.append(r)
# fausses annonces : CME dont la dernière simulation de 2024 prévoit un impact en 2024, sans choc relié
derniere = {}
for s in sims_t:
    for i in ids_de(s):
        derniere[i] = s
fausses_cme = []
for i, s in derniere.items():
    a = s.get("estimatedShockArrivalTime")
    if a and datetime(2024, 1, 1, tzinfo=timezone.utc) <= date(a) < datetime(2025, 1, 1, tzinfo=timezone.utc) \
            and not (ids_de(s) & cme_avec_choc):
        fausses_cme.append({"cme": i, "arrivee_prevue": a, "kp_prevu": [s.get("kp_90"), s.get("kp_180")],
                            "effleurement": s.get("isEarthGB"),
                            "kp_observe": kp_max(date(a) - timedelta(hours=12), date(a) + timedelta(hours=24))})
err = [c["erreur_h"] for c in cas if c.get("statut") == "annoncée"]
res["cme"] = {
    "chocs_relies_a_une_cme": len(cas),
    "annoncees": len(err), "simulees_sans_impact": sum(c["statut"] == "simulée sans impact" for c in cas),
    "non_simulees": sum(c["statut"] == "non simulée" for c in cas),
    "erreur_moyenne_h": round(st.mean(err), 1) if err else None,
    "erreur_absolue_moyenne_h": round(st.mean(abs(x) for x in err), 1) if err else None,
    "erreur_mediane_h": round(st.median(err), 1) if err else None,
    "part_dans_10h": round(sum(abs(x) <= 10 for x in err) / len(err), 2) if err else None,
    "fausses_annonces": len(fausses_cme),
    "cas": cas, "fausses": fausses_cme,
}
kp_ok = [c for c in cas if c.get("statut") == "annoncée" and None not in c["kp_prevu"] and c["kp_observe_24h"] is not None]
res["cme"]["kp_dans_la_fourchette"] = round(sum(c["kp_prevu"][0] - 0.5 <= c["kp_observe_24h"] <= c["kp_prevu"][1] + 0.5
                                                for c in kp_ok) / len(kp_ok), 2) if kp_ok else None
res["cme"]["n_kp"] = len(kp_ok)

(R / "bilan_2024.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))

# ---------------------------------------------------------------- affichage
print("== 1. Prévision L1 horaire ==")
for k, v in res["horaire"].items():
    print(f"  {k}: {v}")
print("== 2. Épisodes d'alerte ==", {k: v for k, v in res["episodes"].items() if k != "liste"})
print("== 3. Dépassements orange à Chambon ==")
for x in res["depassements_orange"]:
    print("  ", x)
print("   (>= 30 nT/min :", len(res["depassements_30"]), "événements, dont annoncés :",
      sum(x["annonce"] for x in res["depassements_30"]), ")")
print("== 4. Chocs ==", {k: v for k, v in res["chocs"].items() if k not in ("manques", "fausses")})
print("== 5. CME ==", {k: v for k, v in res["cme"].items() if k not in ("cas", "fausses")})


# ---------------------------------------------------------------- 6. analyses complémentaires
comp = {}
# 6a. dépassements >= 30 nT/min non annoncés : contexte
comp["non_annonces_30"] = []
for x in res["depassements_30"]:
    if x["annonce"]:
        continue
    T = date(x["debut"])
    i = bisect.bisect_left(tcol, T)
    avant = collectes[max(0, i - 12):i + 1]                                   # l'heure précédente
    p90 = [float(c["dbdt_p90"]) for c in avant if c["dbdt_p90"]]
    comp["non_annonces_30"].append({"debut": x["debut"], "max": x["max"], "p90_L1_heure_avant": max(p90) if p90 else None,
                                    "donnees_L1": len(p90), "kp": kp_max(T, T)})
# 6b. calibrage par classe de prévision (médiane prévue)
classes = [(0, 3), (3, 5), (5, 10), (10, 20), (20, 1e9)]
comp["calibrage"] = []
for a, z in classes:
    sel = [v for v in L if a <= v["prevu_med"] < z]
    if sel:
        rap = [math.log10(max(v["observe"], 0.1) / v["prevu_med"]) for v in sel]
        comp["calibrage"].append({"prevu_med": f"{a}-{z if z < 1e9 else '+'}", "n": len(sel),
                                  "mesure_sur_prevu": round(10 ** st.mean(rap), 2),
                                  "couverture_p90": round(sum(v["observe"] <= v["prevu_p90"] for v in sel) / len(sel), 2),
                                  "part_obs_30": round(sum(v["observe"] >= 30 for v in sel) / len(sel), 3)})
# 6c. chocs : effet au sol (Chambon, 15 à 120 min après le choc à L1)
def reponse(t):
    return hmax(t + timedelta(minutes=15), t + timedelta(minutes=120))
comp["chocs_detectes_reponse"] = sorted(round(reponse(t) or 0, 1) for t in couverts if t in vus)
comp["chocs_manques_reponse"] = sorted(round(reponse(t) or 0, 1) for t in couverts if t not in vus)
comp["fausses_detections_reponse"] = sorted(round(reponse(d) or 0, 1) for d in fausses)
# 6d. veilles CME orange : devenir
veilles = [e for e in res["episodes"]["liste"] if e["ouvert_par"] == ["cme"]]
comp["veilles_cme"] = [{"debut": e["debut"], "kp_observe": kp_max(date(e["debut"]), date(e["fin"])),
                        "mesure_max": e["mesure_max"]} for e in veilles]
comp["fausses_cme_effleurement"] = sum(bool(f["effleurement"]) for f in fausses_cme)
# 6e. alertes « pré-alerte orange » (P90 L1 >= 68) : épisodes concernés
comp["preavis_L1_30"] = [x.get("preavis_l1_min", x.get("preavis_choc_min")) for x in res["depassements_30"]
                         if x["annonce"] and (x.get("preavis_l1_min") is not None or x.get("preavis_choc_min") is not None)]
res["complements"] = comp
(R / "bilan_2024.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
print("== 6. Compléments ==")
for k, v in comp.items():
    print(f"  {k}: {v}")
