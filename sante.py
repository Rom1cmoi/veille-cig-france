"""
Surveillance des sources de données : prévient quand une source ne donne plus rien depuis trop longtemps.

Pourquoi : du 21/10/2026 au 03/11/2026, Chambon-la-Forêt n'a plus été publié par le serveur BGS, et personne ne s'en est
aperçu pendant 13 jours. Le constat (la mesure au sol, qui rattrape les tempêtes que le satellite ne voit pas venir) était
coupé.

À chaque collecte, on note pour chaque source l'instant de sa dernière donnée valide (docs/sources.json). Si cet instant
a plus de SEUILS[source] heures, une issue GitHub « [SOURCE] … » s'ouvre (donc un e-mail), une seule fois ; quand la
source revient, l'issue reçoit un commentaire et se ferme. Ces issues sont séparées des épisodes de tempête : elles
ne comptent ni dans les alertes ni dans les messages CAP.
"""
import json
from datetime import datetime, timedelta, timezone

import alertes

# source : (nom affiché, délai en heures au-delà duquel on prévient)
SEUILS = {
    "l1": ("Vent solaire à L1 (NOAA)", 1),
    "clf": ("Magnétomètre de Chambon-la-Forêt (BGS)", 6),
    "magnetometres": ("Magnétomètres voisins", 24),
    "kp": ("Kp observé (NOAA)", 12),
    "cme": ("Simulations de CME (NASA DONKI)", 24),
    "ap30": ("Indice ap30 (GFZ)", 6),
}


def lire_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def dernieres_donnees(etat, maintenant, donki):
    """Instant de la dernière donnée valide de chaque source dans cette collecte (None si rien de neuf)."""
    l1, clf, kp, sol, hp = (etat.get(k) or {} for k in ("l1", "clf", "kp", "sol", "hpo"))
    d = {"l1": l1.get("derniere_mesure"),
         "clf": clf.get("derniere_mesure") if (clf.get("observatoire") or "CLF") == "CLF" else None,
         "kp": (kp.get("observe") or {}).get("t"),
         "cme": donki.get("lu") if donki else None,
         "ap30": (hp.get("dernier") or {}).get("t")}
    a_jour = sum(1 for v in (sol.get("part_mesuree") or {}).values() if v >= 0.5)
    d["magnetometres"] = iso(maintenant) if sol and a_jour >= 3 else None
    return d


def verifier(etat, maintenant, fichier, erreurs, donki=None):
    """Met à jour docs/sources.json, ouvre ou ferme les issues « [SOURCE] ». Renvoie les sources en panne."""
    suivi = json.loads(fichier.read_text()) if fichier.exists() else {}
    en_panne = []
    for cle, t in dernieres_donnees(etat, maintenant, donki).items():
        s = suivi.setdefault(cle, {"derniere": None, "issue": None})
        if t and (not s["derniere"] or lire_date(t) > lire_date(s["derniere"])):
            s["derniere"] = t
        if not s["derniere"]:                                     # jamais vue : le compteur part de maintenant
            s["derniere"] = iso(maintenant)
        nom, seuil_h = SEUILS[cle]
        age_h = (maintenant - lire_date(s["derniere"])).total_seconds() / 3600
        try:
            if age_h > seuil_h:
                en_panne.append(nom)
                if not s["issue"]:
                    titre = (f"[SOURCE] {nom} : moins de 3 sur 6 à jour depuis {age_h:.0f} h" if cle == "magnetometres"
                             else f"[SOURCE] {nom} : aucune donnée depuis {age_h:.0f} h")
                    corps = (f"Dernière donnée valide : {s['derniere']} (il y a {age_h:.0f} h ; seuil {seuil_h} h).\n\n"
                             "Le service continue avec les autres sources ; cette issue se fermera seule quand la "
                             "source reviendra.")
                    if cle == "clf":
                        corps += ("\n\nPendant ce temps, le constat se fait sur l'observatoire voisin le plus à jour "
                                  "(Dourbes, Fürstenfeldbruck ou Wingst) et la validation horaire de la prévision est "
                                  "suspendue.")
                    proprio = __import__("os").environ.get("GITHUB_REPOSITORY_OWNER")
                    r = alertes.github("POST", "/issues", {"title": titre, "body": corps + (f"\n\n@{proprio}" if proprio else "")})
                    s["issue"] = r["number"] if r else -1                 # -1 : hors de GitHub, déjà signalé
                    print("SOURCE EN PANNE :", titre)
            elif s["issue"]:
                if s["issue"] > 0:
                    alertes.github("POST", f"/issues/{s['issue']}/comments",
                                   {"body": f"Source revenue : donnée valide à {s['derniere']}."})
                    alertes.github("PATCH", f"/issues/{s['issue']}", {"state": "closed", "state_reason": "completed"})
                print("SOURCE REVENUE :", nom)
                s["issue"] = None
        except Exception as e:                                   # un envoi raté ne bloque pas la collecte
            erreurs.append(f"surveillance des sources : {e}")
    fichier.write_text(json.dumps(suivi, indent=1, ensure_ascii=False))
    return en_panne
