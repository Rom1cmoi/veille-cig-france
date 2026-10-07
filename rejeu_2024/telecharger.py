"""
Télécharge les données de l'année 2024 nécessaires au rejeu du service (lancé par GitHub Actions,
car l'environnement de développement n'a pas accès à ces serveurs).

  - OMNI 1 min (NASA CDAWeb, HAPI) : vent solaire + décalage temporel vers la Terre (Timeshift),
    qui permet de reconstituer les instants de mesure à L1 ;
  - Chambon-la-Forêt 1 min, données définitives (BGS, HAPI) ;
  - DONKI (NASA CCMC) : simulations WSA-ENLIL et chocs interplanétaires (IPS) observés ;
  - Kp définitif (GFZ Potsdam).

Bibliothèque standard uniquement. Les fichiers sont écrits, compressés, dans rejeu_2024/donnees/.
"""
import gzip
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "donnees"
DEBUT, FIN = datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc)

OMNI = ("https://cdaweb.gsfc.nasa.gov/hapi/data?id=OMNI_HRO_1MIN"
        "&parameters=Timeshift,F,BY_GSM,BZ_GSM,flow_speed,proton_density"
        "&time.min={a}&time.max={b}&format=csv")
CLF = ("https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?dataset=clf/definitive/PT1M/xyzf"
       "&parameters=Field_Vector&start={a}&stop={b}&format=csv")
ENLIL = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/WSAEnlilSimulations?startDate={a}&endDate={b}"
IPS = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/IPS?startDate={a}&endDate={b}"
KP = "https://kp.gfz.de/app/json/?start=2023-12-31T00:00:00Z&end=2025-01-01T00:00:00Z&index=Kp"


def lire(url, essais=4):
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  échec ({e}), nouvel essai dans {10 * (i + 1)} s")
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"impossible de lire {url}")


def mois():
    """Découpe 2024 en tranches d'un mois : [(début, fin), ...]."""
    t = DEBUT
    while t < FIN:
        suivant = (t.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield t, min(suivant, FIN)
        t = suivant


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def ecrire(nom, texte):
    SORTIE.mkdir(parents=True, exist_ok=True)
    with gzip.open(SORTIE / nom, "wt", encoding="utf-8") as f:
        f.write(texte)
    print(f"{nom} : {len(texte) / 1e6:.1f} Mo avant compression")


def series_mensuelles(modele, entete, nom):
    morceaux = [entete]
    for a, b in mois():
        print(nom, a.strftime("%Y-%m"))
        texte = lire(modele.format(a=iso(a), b=iso(b)))
        morceaux.append(texte.strip())
    ecrire(nom, "\n".join(morceaux) + "\n")


def donki(modele, nom):
    """DONKI limite la durée d'une requête : on interroge par tranches de 30 jours, du 1er décembre 2023
    (pour avoir les CME parties avant le 1er janvier) au 31 décembre 2024."""
    tout, vus = [], set()
    t = datetime(2023, 12, 1, tzinfo=timezone.utc)
    while t < FIN:
        b = min(t + timedelta(days=29), FIN - timedelta(days=1))
        print(nom, t.date(), b.date())
        texte = lire(modele.format(a=t.strftime("%Y-%m-%d"), b=b.strftime("%Y-%m-%d")))
        for e in (json.loads(texte) if texte.strip() else []):
            cle = e.get("simulationID") or e.get("activityID")
            if cle not in vus:
                vus.add(cle)
                tout.append(e)
        t = b + timedelta(days=1)
    ecrire(nom, json.dumps(tout, separators=(",", ":")))


if __name__ == "__main__":
    series_mensuelles(OMNI, "t,timeshift_s,F,By_gsm,Bz_gsm,V,n", "omni_1min_2024.csv.gz")
    series_mensuelles(CLF, "t,X,Y,Z", "clf_1min_2024.csv.gz")
    donki(ENLIL, "donki_enlil_2024.json.gz")
    donki(IPS, "donki_ips_2024.json.gz")
    ecrire("kp_gfz_2024.json.gz", lire(KP))
    print("terminé")
