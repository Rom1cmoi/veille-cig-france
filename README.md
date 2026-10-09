# Veille CIG France, version en direct

Cette version de l'outil se nourrit **toute seule** des données du moment :

| Horizon | Source | Ce qu'on en tire |
|---|---|---|
| Veille CME (1 à 3 jours) | CME vues par les coronographes, simulées par WSA-ENLIL (NASA, base DONKI) | Heure d'arrivée du choc (±10 h) et Kp estimé selon l'orientation du champ : la force reste inconnue jusqu'à L1 |
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
| `validation.py` | Bilan de la prévision L1 en conditions réelles (mêmes indicateurs que le rapport). |
| `bulletins.py` | Bulletins grand public, prévisionniste et exploitant. |
| `cap.py` | Messages d'alerte au format CAP 1.2 et flux Atom. |
| `alertes.py` | Décide s'il faut prévenir et envoie les alertes (issue GitHub, ntfy). |
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

## CME en route (horizon 1 à 3 jours)

Les coronographes (SOHO, STEREO-A, GOES CCOR-1) voient partir les éjections de masse coronale (CME). La NASA (CCMC) en mesure la vitesse et la direction, puis simule leur propagation avec le modèle WSA-ENLIL. Le collecteur lit ces simulations dans la base DONKI (`https://ccmc.gsfc.nasa.gov/DONKI-API/`, nouvelle adresse depuis le 30 septembre 2026), toutes les 30 minutes au plus.

Pour chaque CME attendue sur Terre, la page affiche :
- l'heure d'arrivée estimée du choc, avec une erreur typique de ±10 h (ordre de grandeur des bilans du CME Arrival Time Scoreboard de la CCMC) ;
- le Kp estimé par la simulation pour trois orientations du champ magnétique de la CME (angle d'horloge 90°, 135°, 180° : de « pas orienté sud » à « plein sud »), converti en dB/dt avec le modèle Kp du rapport ;
- la compression de la magnétopause (sous 6,6 rayons terrestres, elle passe sous l'orbite géostationnaire).

**Ce que ça montre :** on sait prévoir quand une CME arrive, pas avec quelle force. La force dépend surtout de l'orientation de son champ, qu'on ne mesure qu'à L1, 30 à 60 min avant l'impact. Une alerte « veille » est envoyée si le cas plein sud atteint l'orange.

Chaque simulation qui prévoit un impact est gardée dans `journal/cme_previsions.csv`. Comparée aux chocs détectés à L1 (journal des collectes), elle donnera l'erreur réelle sur l'heure d'arrivée.

## Collecte vraiment toutes les 5 minutes (déclencheur externe)

GitHub retarde les tâches planifiées des comptes gratuits : en pratique, 18 min en médiane entre deux collectes (jusqu'à 30 min). C'est gênant pour l'alerte de choc à L1, qui ne laisse que 30 à 60 min d'avance. Un lancement à la demande (« Run workflow »), lui, démarre en quelques secondes. On fait donc appuyer sur ce bouton toutes les 5 minutes par un service gratuit, cron-job.org. La tâche planifiée de GitHub reste en secours, toutes les 30 min (si cron-job.org s'arrête, la collecte continue, moins souvent).

1. **Jeton GitHub limité.** GitHub → photo de profil → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**. Nom : `cron veille-cig`. Expiration : une date après la soutenance. **Repository access** : *Only select repositories* → `veille-cig-france`. **Permissions** → **Repository permissions** → **Actions** : *Read and write*. **Generate token**, puis copie-le (il ne s'affiche qu'une fois). Ce jeton ne permet que de lancer les tâches de ce dépôt : il ne donne accès ni au code des autres dépôts ni au compte.
2. **Compte** sur https://cron-job.org (gratuit).
3. **Create cronjob** :
   - URL : `https://api.github.com/repos/Rom1cmoi/veille-cig-france/actions/workflows/collecte.yml/dispatches`
   - Exécution : toutes les 5 minutes.
4. Onglet **Advanced** :
   - Request method : `POST`
   - Headers : `Authorization` = `Bearer <ton jeton>` ; `Accept` = `application/vnd.github+json` ; `Content-Type` = `application/json`
   - Request body : `{"ref":"main"}`
5. **Test run** : la réponse doit être `204 No Content` (= GitHub a accepté). Dans l'onglet **Actions** du dépôt, une collecte « workflow_dispatch » apparaît aussitôt.

Erreurs possibles : `401` = jeton mal copié (vérifier le mot `Bearer` et l'espace) ; `403` ou `404` = jeton sans la permission Actions *Read and write*, ou pas limité au bon dépôt ; `422` = corps de requête incorrect.

## Gazoducs

En mode Gaz (bouton au-dessus de la carte), les 33 600 km du réseau de transport (NaTran, Teréga) sont colorés selon le potentiel tube-sol (PSP) induit, pour le même dB/dt que la carte électrique. Le calcul (dossier `calc` du projet, `gaz_reseau.py`) suit la méthode de Boteler (ligne de transmission à sources distribuées, schéma en pi, résolution nodale), avec le même sol EURHOM que pour le réseau électrique. Les paramètres des tubes ne sont pas publiés : cas de base DN 600, 12 mm, revêtement 10 µS/m², fourchette Monte-Carlo ×0,38 à ×1,7. Seuils provisoires : 2 V (jaune), 10 V (orange), 30 V (rouge), à calibrer avec les exploitants ; la protection cathodique tient le tube entre −0,85 et −1,2 V. Tracés : ODRÉ, Licence Ouverte (NaTran 2025, Teréga 2021).

## Bulletins et flux CAP

À chaque collecte, `bulletins.py` rédige trois bulletins, affichés en mode Direct et joints aux alertes :
- **grand public** : la couleur et ce qu'elle veut dire, en heure de Paris, sans jargon ;
- **prévisionniste** : mesures et prévisions avec leurs incertitudes (vent solaire, choc, Kp, CME, Chambon, validation) ;
- **exploitant** : courant estimé au poste le plus exposé (Cruas probable, avec la fourchette Monte-Carlo) et mesures envisageables selon le niveau, à valider avec l'exploitant.

Chaque ouverture, aggravation ou fin d'épisode produit aussi un message **CAP 1.2** (Common Alerting Protocol, le format des systèmes d'alerte), dans `docs/cap/`, listé par le flux Atom `docs/cap.atom` (comme Meteoalarm). Statut « Exercise » : ce démonstrateur n'est pas un service officiel.

## Alertes

Le collecteur prévient tout seul quand il se passe quelque chose (fichier `alertes.py`).

**Quand ?** Dès qu'un de ces signaux apparaît :

| Signal | Condition |
|---|---|
| CME en route | Simulation WSA-ENLIL : Kp « plein sud » qui donnerait l'orange (Kp 8 ou plus) |
| Choc à L1 | Saut brutal de pression ET de vitesse (≥ 20 km/s) du vent solaire : arrivée sur Terre dans 15 à 60 min |
| Veille, Pré-alerte ou Constat orange | dB/dt (P90 prévu, ou mesuré) ≥ 68 nT/min, soit 10 A par phase au poste le plus exposé |
| Rouge | dB/dt ≥ 509 nT/min, soit 75 A |

**Comment ?** Un épisode s'ouvre au premier signal : une *issue* GitHub est créée dans le dépôt (onglet **Issues**), et GitHub t'envoie une notification (e-mail, appli GitHub). Chaque nouveau signal ou aggravation ajoute un commentaire, donc une nouvelle notification. Après 3 h sans signal, l'épisode se ferme avec un bilan (dB/dt prévu et mesuré maximaux). L'onglet Issues devient ainsi le journal des épisodes.

**Tester :** onglet **Actions** → **collecte** → **Run workflow** → coche **Envoyer une alerte de test** → **Run workflow**. Une issue « [TEST] » est créée puis fermée aussitôt.

**Option : notifications push sur téléphone ou iPad (ntfy)**

1. Installe l'appli gratuite **ntfy** (App Store ou Google Play).
2. Dans l'appli : **+** → choisis un nom de sujet difficile à deviner (par exemple `veille-cig-` suivi de lettres au hasard) → **Subscribe**. Toute personne qui connaît ce nom peut lire les messages : ne le publie pas.
3. Sur GitHub : **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Nom : `NTFY_TOPIC`. Valeur : le nom du sujet. **Add secret**.
4. Lance le test ci-dessus : la notification arrive sur l'appareil.

Sur ton ordinateur (`en_continu.py`), rien n'est envoyé : les alertes sont seulement affichées dans le terminal.

## Journal et validation sur la durée

Chaque collecte laisse une trace dans le dossier `journal/` :

| Fichier | Contenu |
|---|---|
| `journal/collectes_AAAA-MM.csv` | Une ligne par collecte : ce que l'outil disait à cet instant (vent solaire, choc, dB/dt prévus, Kp, Chambon, alerte). |
| `journal/l1/l1_AAAA-MM-JJ.csv` | Les mesures brutes à la minute du satellite actif à L1. La NOAA ne les garde en ligne que quelques jours, et OMNI (utilisé dans le rapport) est une série retraitée : ce sont ces données temps réel, avec leur bruit, qu'il faut garder pour juger l'outil. |
| `docs/historique.json` | Une ligne par heure : prévision L1 émise en début d'heure, puis dB/dt maximal mesuré à Chambon. Rien n'est effacé : c'est le jeu de validation. |

`validation.py` calcule sur cet historique les mêmes indicateurs que le chapitre 4 du rapport (corrélation, RMSE, biais, couverture du P90, POD et FAR de l'alerte à 30 nT/min). Le bilan s'affiche dans le bloc « Auto-validation » du mode Direct, à côté des valeurs du rapport. Pour l'afficher dans un terminal : `python validation.py`.

Les données de Chambon ne sont pas archivées : les données définitives se récupèrent plus tard sur INTERMAGNET.

## Ce qu'il faut savoir sur les données

- **Vent solaire.** La NOAA mélange plusieurs satellites ; le collecteur garde, minute par minute, celui que la NOAA marque comme actif (aujourd'hui SOLAR-1). Les modèles du rapport ont été ajustés sur OMNI, une série retraitée : en temps réel, les mesures sont plus bruitées.
- **Chambon.** Les données en direct sont provisoires (« variation ») et arrivent avec environ 15 minutes de retard ; les minutes manquantes valent 99999 et sont ignorées.
- **Pression dynamique.** Calculée comme P = 2·10⁻⁶ n V² (nPa), à quelques pour cent de la valeur OMNI.
- **Démonstration.** Les instants « à L1 » y sont reconstitués en reculant les données OMNI du délai L1 → Terre : l'heure d'arrivée affichée retombe donc en partie par construction sur la vraie (17 h 07). Le Kp « prévu » de la démonstration est le Kp observé ensuite.
- **Ce que l'outil ne fait toujours pas** : il n'est pas validé contre des courants mesurés (il faut RTE), et les paramètres des postes restent supposés.

## Mettre à jour la page

La page `docs/index.html` est produite par les scripts du projet (`build_outil.py`). Si tu modifies l'outil, régénère-la et remplace ce fichier. Les coefficients des modèles de prévision sont en haut de `collecteur.py`.
