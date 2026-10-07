# Rejeu de l'année 2024

L'année 2024, rejouée toutes les 5 minutes avec le code du service (`collecteur.py`, `alertes.py`), pour répondre aux questions d'un exploitant : combien d'alertes, combien de fausses, quels orages ratés, quel préavis.

| Fichier | Rôle |
|---|---|
| `telecharger.py` | Télécharge les données (lancé par la tâche GitHub `rejeu-2024-donnees`) : OMNI 1 min, Chambon définitif, simulations WSA-ENLIL et chocs (DONKI), Kp (GFZ). |
| `rejeu.py` | Rejoue l'année : à chaque instant, reconstitue ce que le collecteur aurait reçu (L1 avec 2 min de retard, Chambon avec 15 min, simulations de CME déjà publiées), appelle les fonctions du service, intercepte les alertes. |
| `bilan.py` | Scores horaires, épisodes, dépassements, chocs, CME → `resultats/bilan_2024.json`. |
| `figures.py` | Figures 15 et 16 du rapport. |

Ordre : `python rejeu_2024/rejeu.py` (environ 6 min), puis `bilan.py`, puis `figures.py`.

Limites : OMNI est retraité (moins bruité que le flux temps réel) et ses instants à L1 sont reconstitués en lissant son décalage temporel (erreur de quelques minutes) ; Chambon définitif est plus propre que le provisoire ; la veille Kp n'est pas rejouée (pas d'archive simple des prévisions NOAA).
