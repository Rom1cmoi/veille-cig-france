"""
Alertes de Veille CIG France.

collecteur.py appelle traiter() après chaque collecte. Ce module décide s'il faut prévenir, puis prévient
par deux canaux :
  1. une « issue » GitHub dans le dépôt : elle sert de journal des épisodes, et GitHub envoie une
     notification (e-mail, appli GitHub) au propriétaire du dépôt ;
  2. une notification push via ntfy (https://ntfy.sh), seulement si le secret NTFY_TOPIC est défini.
Hors de GitHub (sur ton ordinateur, ou avec --demo), rien n'est envoyé : les messages sont affichés.

Un ÉPISODE s'ouvre au premier signal. Chaque signal nouveau ou plus grave ajoute un commentaire (donc une
notification). L'épisode se ferme après 3 h sans aucun signal, avec un bilan. Entre deux collectes,
l'état de l'épisode est gardé dans docs/alertes.json.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

# dB/dt à Chambon (nT/min) qui donne 10 A (orange) et 75 A (rouge) par phase au poste le plus exposé, dans la
# direction la plus défavorable et pour une période de 20 min. Le coefficient de ce poste dans l'outil vaut
# 0,147 A par nT/min, d'où 10 / 0,147 = 68 et 75 / 0,147 = 509. Ce sont les seuils de la carte en mode pessimiste.
SEUIL_ORANGE = 68.0
SEUIL_ROUGE = 509.0
FIN_EPISODE = timedelta(hours=3)
GRAVITE = {"choc": 1, "orange": 2, "rouge": 3}
PRIORITE_NTFY = {"choc": 4, "orange": 4, "rouge": 5}                        # 5 = urgent (sonne même en silencieux)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def lire_date(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def hm(s):
    """'2026-10-06T12:36:00Z' -> '12 h 36 UTC'"""
    return f"{s[11:13]} h {s[14:16]} UTC" if s else "?"


def niveau(dbdt):
    if dbdt is None:
        return None
    return "rouge" if dbdt >= SEUIL_ROUGE else "orange" if dbdt >= SEUIL_ORANGE else None


# ---------------------------------------------------------------- 1. Quels signaux dans l'état actuel ?
def signaux(etat):
    """Liste des raisons de prévenir. Chaque signal a une clé : on ne prévient qu'une fois par clé et par épisode."""
    l1, kp, clf = etat.get("l1"), etat.get("kp"), etat.get("clf")
    s = []
    if l1 and l1.get("choc"):
        c = l1["choc"]
        s.append({"cle": "choc " + c["vu_a_L1"], "niveau": niveau(l1["dbdt_p90"]) or "choc",
                  "titre": f"Choc détecté à L1, arrivée sur Terre vers {hm(c['arrivee_estimee'])}",
                  "texte": f"Saut de pression et de vitesse (+{c.get('saut_V', '?')} km/s) vu à L1 à {hm(c['vu_a_L1'])}. "
                           f"dB/dt attendu dans l'heure à Chambon : {l1['dbdt_med']} nT/min (P90 {l1['dbdt_p90']})."})
    if l1 and niveau(l1["dbdt_p90"]):
        n = niveau(l1["dbdt_p90"])
        s.append({"cle": "l1 " + n, "niveau": n, "titre": f"Pré-alerte {n} : vent solaire à L1",
                  "texte": f"dB/dt attendu dans l'heure à Chambon : {l1['dbdt_med']} nT/min, P90 {l1['dbdt_p90']} nT/min "
                           f"(V = {l1['V']} km/s, Bz = {l1['Bz']} nT, arrivée vers {hm(l1['arrivee'])})."})
    pic = kp and kp.get("pic_24h")
    if pic and niveau(pic["dbdt_p90"]):
        n = niveau(pic["dbdt_p90"])
        s.append({"cle": "kp " + n, "niveau": n, "titre": f"Veille {n} : Kp {pic['kp']} prévu par la NOAA",
                  "texte": f"Kp {pic['kp']} prévu pour le créneau du {pic['t'][8:10]}/{pic['t'][5:7]} à {hm(pic['t'])}. "
                           f"dB/dt attendu : {pic['dbdt_med']} nT/min, P90 {pic['dbdt_p90']} nT/min."})
    if clf and niveau(clf.get("dbdt_max_1h")):
        n = niveau(clf["dbdt_max_1h"])
        s.append({"cle": "clf " + n, "niveau": n, "titre": f"Constat {n} : {clf['dbdt_max_1h']} nT/min à Chambon",
                  "texte": f"dB/dt mesuré à Chambon-la-Forêt : {clf['dbdt_max_1h']} nT/min à {hm(clf['heure_max'])} "
                           f"(données provisoires, {clf['retard_min']} min de retard)."})
    return s


# ---------------------------------------------------------------- 2. Les deux canaux d'envoi
def github(methode, chemin, donnees):
    """Appel à l'API GitHub avec le jeton fourni automatiquement aux tâches planifiées. None hors de GitHub."""
    jeton, depot = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (jeton and depot):
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{depot}{chemin}", method=methode,
                                 data=json.dumps(donnees).encode(),
                                 headers={"Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "veille-cig-france"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def ntfy(titre, texte, niv, lien):
    """Notification push. Envoyée en JSON pour que les accents passent sans souci."""
    sujet = os.environ.get("NTFY_TOPIC")
    if not sujet:
        return
    corps = {"topic": sujet, "title": titre, "message": texte, "priority": PRIORITE_NTFY.get(niv, 3),
             "tags": ["warning" if niv != "rouge" else "rotating_light"], "click": lien}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(corps).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "veille-cig-france"})
    urllib.request.urlopen(req, timeout=20).read()


def adresse_page():
    depot = os.environ.get("GITHUB_REPOSITORY", "Rom1cmoi/veille-cig-france")
    proprio, nom = depot.split("/")
    return f"https://{proprio.lower()}.github.io/{nom}/"


def corps_message(liste, maintenant):
    proprio = os.environ.get("GITHUB_REPOSITORY_OWNER")
    lignes = [f"**{x['titre']}**\n{x['texte']}\n" for x in liste]
    lignes.append(f"Collecte du {maintenant:%d/%m/%Y à %H h %M} UTC · [ouvrir la page]({adresse_page()}) (mode Direct)")
    lignes.append("Seuils : orange = 10 A par phase au poste le plus exposé (68 nT/min à Chambon), rouge = 75 A (509 nT/min).")
    if proprio:
        lignes.append(f"\n@{proprio}")                                     # la mention garantit la notification
    return "\n".join(lignes)


# ---------------------------------------------------------------- 3. Gestion des épisodes
def traiter(etat, maintenant, fichier, erreurs):
    """Met à jour l'épisode, envoie ce qu'il faut. Renvoie un petit résumé pour la page (ou None)."""
    if os.environ.get("ALERTE_TEST") == "true":
        envoyer_test(maintenant, erreurs)                                   # puis traitement normal
    ep = json.loads(fichier.read_text()) if fichier and fichier.exists() else {}
    sig = signaux(etat)
    lien = adresse_page()
    try:
        if sig:
            nouveaux = [x for x in sig if x["cle"] not in ep.get("deja", [])]
            pire = max(nouveaux or sig, key=lambda x: GRAVITE[x["niveau"]])
            if not ep:                                                       # ouverture d'un épisode
                ep = {"debut": iso(maintenant), "niveau": pire["niveau"], "issue": None, "lien": lien, "deja": [],
                      "max_prevu": 0, "max_mesure": 0}
                titre = f"[{pire['niveau'].upper()}] {pire['titre']}"
                print("ALERTE :", titre)
                r = github("POST", "/issues", {"title": titre, "body": corps_message(sig, maintenant)})
                if r:
                    ep["issue"], ep["lien"] = r["number"], r["html_url"]
                ntfy(titre, "\n".join(x["texte"] for x in sig), pire["niveau"], ep["lien"])
            elif nouveaux:                                                   # nouveau signal pendant l'épisode
                titre = f"[{pire['niveau'].upper()}] {pire['titre']}"
                print("ALERTE (suite) :", titre)
                if ep["issue"]:
                    github("POST", f"/issues/{ep['issue']}/comments", {"body": corps_message(nouveaux, maintenant)})
                    if GRAVITE[pire["niveau"]] > GRAVITE[ep["niveau"]]:      # aggravation : on change le titre
                        github("PATCH", f"/issues/{ep['issue']}", {"title": titre})
                ntfy(titre, "\n".join(x["texte"] for x in nouveaux), pire["niveau"], ep["lien"])
            ep["deja"] += [x["cle"] for x in nouveaux]
            ep["niveau"] = max([ep["niveau"]] + [x["niveau"] for x in sig], key=GRAVITE.get)
            ep["dernier_signal"] = iso(maintenant)

        if ep:                                                               # suivi des maxima pendant l'épisode
            l1, clf = etat.get("l1") or {}, etat.get("clf") or {}
            ep["max_prevu"] = max(ep["max_prevu"], l1.get("dbdt_p90") or 0)
            ep["max_mesure"] = max(ep["max_mesure"], clf.get("dbdt_max_1h") or 0)
            if not sig and maintenant - lire_date(ep["dernier_signal"]) >= FIN_EPISODE:
                bilan = (f"Fin de l'épisode : aucun signal depuis 3 h.\n\nDébut : {ep['debut']} · niveau maximal : "
                         f"{ep['niveau']} · dB/dt prévu maximal (P90, L1) : {ep['max_prevu']} nT/min · dB/dt mesuré "
                         f"maximal à Chambon : {ep['max_mesure']} nT/min.")
                print("FIN D'ÉPISODE :", bilan)
                if ep["issue"]:
                    github("POST", f"/issues/{ep['issue']}/comments", {"body": bilan})
                    github("PATCH", f"/issues/{ep['issue']}", {"state": "closed", "state_reason": "completed"})
                ep = {}
    except Exception as e:                                                   # un envoi raté ne bloque pas la collecte
        erreurs.append(f"alerte : {e}")

    if fichier:
        fichier.write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    if not ep:
        return None
    return {"niveau": ep["niveau"], "depuis": ep["debut"], "lien": ep["lien"],
            "signaux": [x["titre"] for x in sig]}


def envoyer_test(maintenant, erreurs):
    """Bouton « Run workflow » avec la case « test » cochée : vérifie que les deux canaux arrivent jusqu'à toi."""
    titre = "[TEST] Veille CIG France : les alertes fonctionnent"
    texte = "Message de test envoyé à la main. Aucune activité géomagnétique n'est signalée."
    try:
        r = github("POST", "/issues", {"title": titre, "body": corps_message([{"titre": titre, "texte": texte}], maintenant)})
        if r:
            github("PATCH", f"/issues/{r['number']}", {"state": "closed", "state_reason": "completed"})
        ntfy(titre, texte, "choc", adresse_page())
        print("Test envoyé :", "issue n°" + str(r["number"]) if r else "pas de GitHub",
              "+ ntfy" if os.environ.get("NTFY_TOPIC") else "(ntfy non configuré)")
    except Exception as e:
        erreurs.append(f"alerte (test) : {e}")
