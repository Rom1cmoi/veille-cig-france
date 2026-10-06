# Veille CIG France, version en direct

Cette version de l'outil se nourrit **toute seule** des données du moment :

| Horizon | Source | Ce qu'on en tire |
|---|---|---|
| Veille (24 h) | Kp prévu à 3 jours par la NOAA | dB/dt attendu (modèle Kp du rapport) |
| Pré-alerte (20 à 60 min) | Vent solaire mesuré à L1 par la NOAA (SOLAR-1, DSCOVR, ACE, IMAP), à la minute | dB/dt de l'heure qui commence (modèle vent solaire du rapport), détection des chocs et heure d'arrivée |
| Constat (maintenant) | Magnétomètre de Chambon-la-Forêt, INTERMAGNET (environ 15 min de retard) | dB/dt réellement mesuré, direction et période |

Chaque heure, la prévision est aussi comparée au dB/dt mesuré ensuite : l'outil se valide lui-même au fil des jours.

## Comment ça marche

```
NOAA (L1, Kp) ─┐
               ├─> collecteur.py ──> docs/etat_courant.json ──> docs/index.html (la page)
Chambon ───────┘     (toutes les 5 min)   docs/historique.json
```

**Pourquoi un collecteur ?** Une page web n'a pas le droit d'aller lire n'importe quel site (sécurité des navigateurs). Le collecteur, lui, est un programme : il va chercher les données, applique les modèles du rapport et écrit un petit fichier JSON. La page lit ce fichier, qui est rangé à côté d'elle, et calcule la carte avec les coefficients du réseau déjà intégrés.

| Fichier | Rôle |
|---|---|
| `collecteur.py` | Lit les trois sources, calcule les dB/dt prévus et mesurés, écrit `docs/etat_courant.json` et `docs/historique.json`. Bibliothèque Python standard uniquement : rien à installer. |
| `docs/index.html` | La page Veille CIG France complète (tous les modes + le mode Direct). |
| `docs/etat_demo.json` | Une démonstration : le 10 mai 2024 à 16 h 35 UTC, quand le choc est déjà mesuré à L1 mais pas encore arrivé. La page l'affiche si le vrai fichier n'existe pas encore. |
| `demo/` | Les données qui ont servi à fabriquer la démonstration (`python collecteur.py --demo`). |
| `.github/workflows/collecte.yml` | La tâche planifiée de GitHub : lance le collecteur toutes les 5 minutes. |
| `en_continu.py` | Pour tout faire tourner sur ton ordinateur, sans GitHub. |

## Option 1 : sur ton ordinateur (le plus simple pour essayer)

Il faut Python 3.9 ou plus récent.

1. Ouvre un terminal dans ce dossier.
2. Lance `python en_continu.py` (ou `python3 en_continu.py` sur Mac).
3. Ouvre http://localhost:8000 dans ton navigateur et clique **Direct**.

La page se met à jour toute seule chaque minute ; le collecteur tourne toutes les 5 minutes. Ctrl+C pour arrêter.

## Option 2 : en ligne avec GitHub (gratuit, tourne même quand ton PC est éteint)

GitHub héberge la page (GitHub Pages) et lance le collecteur toutes les 5 minutes (GitHub Actions). Gratuit pour un dépôt public.

1. **Compte.** Crée un compte sur https://github.com si tu n'en as pas.
2. **Dépôt.** En haut à droite : **+** → **New repository**. Nom : `veille-cig-france`. Coche **Public**. Clique **Create repository**.
3. **Fichiers.** Sur la page du dépôt : **Add file** → **Upload files**. Glisse `collecteur.py`, `en_continu.py`, `README.md`, et les dossiers `docs` et `demo`. Clique **Commit changes**.
4. **La tâche planifiée.** Le dossier `.github` est souvent caché par Windows et macOS, donc on le crée à la main : **Add file** → **Create new file**. Dans le nom, tape exactement `.github/workflows/collecte.yml` (les `/` créent les dossiers). Colle le contenu du fichier `collecte.yml` fourni, puis **Commit changes**.
5. **Autoriser le robot à écrire.** **Settings** → **Actions** → **General** → en bas, **Workflow permissions** → coche **Read and write permissions** → **Save**.
6. **Publier la page.** **Settings** → **Pages** → **Source** : *Deploy from a branch* → branche **main**, dossier **/docs** → **Save**. Après une ou deux minutes, l'adresse s'affiche : `https://<ton-pseudo>.github.io/veille-cig-france/`.
7. **Premier lancement.** Onglet **Actions** → accepte d'activer les workflows si on te le demande → clique **collecte** → **Run workflow**. Au bout d'une minute, une coche verte apparaît, et le fichier `docs/etat_courant.json` est créé.
8. Ouvre ton adresse GitHub Pages et clique **Direct**.

### Si quelque chose ne marche pas

- **Croix rouge dans Actions** : clique dessus pour lire le message. « Permission denied » ou « 403 » au moment du `git push` : refais l'étape 5.
- **La page affiche encore la démonstration** : le vrai fichier n'existe pas encore. Lance la collecte à la main (étape 7), puis attends 1 à 2 minutes que GitHub Pages se mette à jour.
- **« Attention : dernière mise à jour il y a … min »** : les lancements automatiques de GitHub peuvent prendre 5 à 15 minutes de retard aux heures chargées. Au-delà de 30 minutes, regarde l'onglet Actions.
- **GitHub désactive parfois les tâches planifiées** d'un dépôt resté sans activité pendant 60 jours : il suffit de la réactiver dans l'onglet Actions.
- **Une source en panne** (NOAA, INTERMAGNET) n'arrête pas les autres : la page indique « sources en erreur » en bas du bloc Direct.

## Ce qu'il faut savoir sur les données

- **Vent solaire.** La NOAA mélange plusieurs satellites ; le collecteur garde, minute par minute, celui que la NOAA marque comme actif (aujourd'hui SOLAR-1). Les modèles du rapport ont été ajustés sur OMNI, une série retraitée : en temps réel, les mesures sont plus bruitées.
- **Chambon.** Les données en direct sont provisoires (« variation ») et arrivent avec environ 15 minutes de retard ; les minutes manquantes valent 99999 et sont ignorées.
- **Pression dynamique.** Calculée comme P = 2·10⁻⁶ n V² (nPa), à quelques pour cent de la valeur OMNI.
- **Démonstration.** Les instants « à L1 » y sont reconstitués en reculant les données OMNI du délai L1 → Terre : l'heure d'arrivée affichée retombe donc en partie par construction sur la vraie (17 h 07). Le Kp « prévu » de la démonstration est le Kp observé ensuite.
- **Ce que l'outil ne fait toujours pas** : il n'est pas validé contre des courants mesurés (il faut RTE), et les paramètres des postes restent supposés.

## Mettre à jour la page

La page `docs/index.html` est produite par les scripts du projet (`build_outil.py`). Si tu modifies l'outil, régénère-la et remplace ce fichier. Les coefficients des modèles de prévision sont en haut de `collecteur.py`.
