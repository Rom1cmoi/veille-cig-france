"""
Flux d'alerte au format CAP 1.2 (Common Alerting Protocol, norme OASIS ; recommandation UIT-T X.1303), le format
que lisent les systèmes d'alerte : sécurité civile, opérateurs, agrégateurs comme Meteoalarm.

Un message par événement d'un épisode d'alerte (alertes.py) :
  - ouverture      -> msgType « Alert » ;
  - signal nouveau ou plus grave -> « Update », qui référence les messages précédents ;
  - fin d'épisode  -> « Cancel » (responseType « AllClear »).
Chaque message est écrit dans docs/cap/<identifiant>.xml ; docs/cap.atom liste les 30 derniers (flux Atom,
comme Meteoalarm).

Statut « Exercise » : la norme le réserve aux messages qui ne sont pas des alertes réelles. C'est le cas d'un
démonstrateur étudiant non officiel, et ça évite qu'un système le confonde avec une alerte de la sécurité civile.
"""
import re
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

STATUT = "Exercise"
SEVERITE = {"choc": "Minor", "jaune": "Moderate", "orange": "Severe", "rouge": "Extreme"}   # échelle Meteoalarm
COULEUR = {"choc": "2; yellow; Moderate", "jaune": "2; yellow; Moderate", "orange": "3; orange; Severe",
           "rouge": "4; red; Extreme"}
# France métropolitaine continentale, contour grossier (lat,lon ; le premier point est répété à la fin)
POLYGONE = ("51.1,2.5 49.4,8.2 47.6,7.6 46.4,6.2 45.9,7.0 44.1,7.7 43.7,7.5 43.0,6.0 43.3,3.2 42.4,3.1 "
            "42.8,-1.8 43.4,-1.8 46.3,-1.3 47.3,-2.5 48.0,-4.8 48.7,-4.6 48.8,-1.6 49.7,-1.9 49.4,0.1 "
            "50.9,1.6 51.1,2.5")


def heure_cap(t):
    """La norme interdit « Z » : l'UTC s'écrit -00:00."""
    return t.strftime("%Y-%m-%dT%H:%M:%S-00:00")


def caracteriser(sig):
    """Urgence, certitude et réponse attendues, d'après le signal le plus grave du message."""
    types = {s["cle"].split()[0] for s in sig}
    if "clf" in types:
        return "Immediate", "Observed", "Monitor"
    if "l1" in types or "choc" in types:
        return "Expected", "Likely", "Prepare"
    return "Future", "Possible", "Prepare"                                    # CME, Kp prévu


def ecrire(dossier, page, ep, sig, maintenant, type_msg, niveau, titre, bulletins):
    """Écrit un message CAP et met à jour le flux Atom. Renvoie la référence « sender,identifiant,sent »."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    expediteur = page.rstrip("/").replace("https://", "")
    ident = f"veille-cig-france.{maintenant:%Y%m%dT%H%M%SZ}.{type_msg.lower()}"
    sent = heure_cap(maintenant)
    refs = " ".join(ep.get("cap", []))
    b = bulletins or {}
    titre_cap = re.sub(r"^\[[A-Z]+\] ", "", titre)                         # la gravité est déjà codée à part
    if type_msg == "Cancel":
        urgence, certitude, reponse = "Past", "Observed", "AllClear"
    else:
        urgence, certitude, reponse = caracteriser(sig)
    x = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">',
        f"  <identifier>{ident}</identifier>",
        f"  <sender>{escape(expediteur)}</sender>",
        f"  <sent>{sent}</sent>",
        f"  <status>{STATUT}</status>",
        f"  <msgType>{type_msg}</msgType>",
        "  <scope>Public</scope>",
        "  <note>Démonstrateur étudiant (IPSA, ELIOS-SPACE), non officiel. Courants estimés par modèle, non "
        "validés contre mesure.</note>",
    ]
    if refs:
        x.append(f"  <references>{escape(refs)}</references>")
    x += [
        "  <info>",
        "    <language>fr-FR</language>",
        "    <category>Met</category>",
        "    <category>Infra</category>",
        "    <event>Courants géomagnétiquement induits dans le réseau électrique</event>",
        f"    <responseType>{reponse}</responseType>",
        f"    <urgency>{urgence}</urgency>",
        f"    <severity>{SEVERITE.get(niveau, 'Unknown') if type_msg != 'Cancel' else 'Minor'}</severity>",
        f"    <certainty>{certitude}</certainty>",
        f"    <expires>{heure_cap(maintenant + timedelta(hours=3 if type_msg != 'Cancel' else 1))}</expires>",
        "    <senderName>Veille CIG France (démonstrateur)</senderName>",
        f"    <headline>{escape(titre_cap)}</headline>",
        f"    <description>{escape((b.get('public', '') + chr(10) + chr(10) + b.get('previsionniste', '')).strip())}</description>",
        f"    <instruction>{escape(b.get('exploitant', ''))}</instruction>",
        f"    <web>{escape(page)}</web>",
        "    <parameter>",
        "      <valueName>awareness_level</valueName>",
        f"      <value>{COULEUR.get(niveau, '1; green; Minor') if type_msg != 'Cancel' else '1; green; Minor'}</value>",
        "    </parameter>",
        "    <area>",
        "      <areaDesc>France métropolitaine continentale</areaDesc>",
        f"      <polygon>{POLYGONE}</polygon>",
        "    </area>",
        "  </info>",
        "</alert>",
    ]
    (dossier / f"{ident}.xml").write_text("\n".join(x) + "\n", encoding="utf-8")
    flux_atom(dossier, page, maintenant)
    return f"{expediteur},{ident},{sent}"


def flux_atom(dossier, page, maintenant):
    """docs/cap.atom : les 30 derniers messages, du plus récent au plus ancien."""
    messages = []
    for p in Path(dossier).glob("*.xml"):
        t = p.read_text(encoding="utf-8")
        champ = lambda nom: (re.search(f"<{nom}>(.*?)</{nom}>", t, re.S) or [None, ""])[1]
        messages.append((champ("sent"), p.name, champ("headline"), champ("msgType")))
    messages.sort(reverse=True)
    url = page.rstrip("/") + "/"
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<feed xmlns="http://www.w3.org/2005/Atom">',
         "  <title>Veille CIG France : alertes CAP (démonstrateur)</title>",
         f"  <id>{url}cap.atom</id>",
         f'  <link rel="self" href="{url}cap.atom"/>',
         f"  <updated>{maintenant:%Y-%m-%dT%H:%M:%SZ}</updated>",
         "  <author><name>Veille CIG France</name></author>"]
    for sent, nom, titre, type_msg in messages[:30]:
        x += ["  <entry>",
              f"    <id>{url}cap/{nom}</id>",
              f"    <title>{titre} ({type_msg})</title>",
              f"    <updated>{sent.replace('-00:00', 'Z')}</updated>",
              f'    <link rel="alternate" type="application/cap+xml" href="{url}cap/{nom}"/>',
              "  </entry>"]
    x.append("</feed>")
    (Path(dossier).parent / "cap.atom").write_text("\n".join(x) + "\n", encoding="utf-8")
