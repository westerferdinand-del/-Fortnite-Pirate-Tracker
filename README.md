# 🏴‍☠️ Pirate Tracker — compteur automatique de coffres Fortnite

Pirate Tracker compte **tout seul** les coffres que vous ouvrez dans Fortnite, en lisant les
**replays** que le jeu enregistre à la fin de chaque partie. Le total de coffres ouverts s'affiche
dans un petit widget au-dessus du jeu et se met à jour **à la fin de chaque partie**. Une page
complète montre vos statistiques : coffres de la dernière partie, total, historique, récompenses
obtenues.

Aucun bouton à presser, aucune capture d'écran, aucune interaction avec le jeu.

![Tableau de bord](docs/dashboard.png)

| Widget pendant la partie | Notification de fin de partie |
|---|---|
| ![Widget](docs/widget.png) | ![Notification](docs/toast.png) |

---

## Installation

1. Sur GitHub : onglet **Actions** → dernière exécution réussie de **Windows build** →
   téléchargez l'artefact **PirateTracker-Windows**.
2. Lancez `PirateTracker-Setup-1.0.0.exe` (aucun droit administrateur requis).
   Une version portable (`PirateTracker-portable.zip`) est aussi fournie.

> Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » car l'exécutable n'est
> pas signé : *Informations complémentaires → Exécuter quand même*.

## ⚠️ Étape indispensable : activer les replays dans Fortnite (une seule fois)

1. Fortnite → menu (en haut à droite) → **Réglages** ⚙.
2. Onglet **Jeu** → section **Replays**.
3. Activez **« Enregistrer les replays »** (*Record Replays*). Sur PC, activez aussi l'option
   Battle Royale si elle est proposée.

Ensuite, jouez normalement. À la fin de chaque partie, Fortnite écrit le replay dans
`%LOCALAPPDATA%\FortniteGame\Saved\Demos`. Pirate Tracker l'analyse (environ 2 secondes) et met
à jour le widget, avec une notification « +N coffres cette partie ».

Vos parties d'avant l'installation peuvent être importées : page **Replays → Importer les anciens
replays**, tant que Fortnite ne les a pas encore effacées.

---

## Comment ça marche

Un replay Fortnite contient les données réseau de la partie. Pour chaque coffre, le jeu enregistre
**qui l'a fouillé** (`SearchingPawn`). Pirate Tracker :

1. repère **votre** personnage, c'est-à-dire celui du joueur qui a enregistré le replay ;
2. compte les coffres fouillés par votre personnage, **une seule fois chacun**. Les coffres
   ouverts par vos coéquipiers ou par les adversaires ne comptent pas, pas plus que les caisses
   de munitions ;
3. relève les objets que vous avez ramassés (page Récompenses) et détecte le **jeton pirate**
   d'après le nom de l'objet.

Garde-fous contre les erreurs de comptage :
- un replay n'est jamais lu pendant la partie, seulement quand Fortnite a fini de l'écrire
  (fichier stable 30 s, et marqué terminé) ;
- si un replay déjà compté change, la partie est **remplacée**, jamais comptée deux fois ;
- un replay illisible est signalé et ne compte rien.

Pendant que vous jouez, l'application ne fait rien d'autre qu'attendre, donc elle ne consomme rien.

### Le jeton pirate

Le nom interne exact de l'objet « jeton pirate » dans les fichiers du jeu n'était pas connu pendant
le développement. Il est reconnu automatiquement si son nom contient *pirate* avec *token / coin /
doubloon / medal*. Sinon, ouvrez la page **Récompenses**, sélectionnez l'objet et cliquez sur
**« C'est le jeton pirate »** : toutes vos parties sont recalculées. À chaque découverte : une
notification Windows (« JETON PIRATE TROUVÉ ! Après N coffres ») et un son, sans animation ; les
deux se désactivent dans les Paramètres. Le nombre de jetons trouvés n'est volontairement pas
affiché.

---

## Ce qui a été testé — et ce qui ne l'a pas été

| Élément | Statut |
|---|---|
| Comptage sur un **vrai replay Fortnite** (Chapitre 5, v32.00, novembre 2024) : 5 coffres pour le joueur, sur 86 ouverts dans la partie, y compris 2 coffres qui disparaissent après ouverture | ✅ Testé (`tests/test_replays.py`), sous Linux et dans la CI Windows |
| Chaîne complète : replay déposé dans le dossier → attente de fin d'écriture → analyse → 5 coffres en base, sans double comptage | ✅ Testé, y compris avec **l'application `.exe` installable** dans la CI Windows |
| Replays en cours d'écriture, déjà comptés, illisibles ; dossier absent ; relecture d'un replay modifié | ✅ Testé |
| Base de données, niveaux, records, jetons, export/sauvegarde/restauration, interface | ✅ Testé |
| **Replays de la saison actuelle (fin 2026)** | ⚠️ Non testé : je n'ai pas de replay récent. La bibliothèque utilisée est maintenue (mise à jour en septembre 2026). Si Epic change la structure des coffres, l'application l'indique (« nouveaux types de coffres non pris en charge ») au lieu de compter faux. **Envoyez un de vos replays avec le nombre de coffres ouverts pour valider.** |
| Nom exact du jeton pirate dans les replays | ⚠️ Inconnu : reconnaissance par motif, ou désignation manuelle une fois (voir ci-dessus) |

---

## Limites connues

| Situation | Effet | Solution |
|---|---|---|
| Replays désactivés dans Fortnite | Rien n'est compté | Activer « Enregistrer les replays » |
| Le compteur ne bouge pas pendant la partie | Normal : il se met à jour à la fin de la partie | — |
| Fortnite efface ses vieux replays | Aucun impact sur les parties déjà analysées | — |
| Fortnite en **plein écran exclusif** | Le widget peut être masqué par le jeu | Mode **Plein écran fenêtré** |
| Replays très anciens (2020) | Ne contiennent pas « qui a ouvert » : 0 coffre + avertissement | — |

## Anti-triche : pourquoi c'est sans risque

Pirate Tracker **lit des fichiers que Fortnite écrit lui-même** sur votre disque, après la partie.
Ce sont les mêmes que lisent les sites et outils d'analyse de replays. Il ne lit pas la mémoire
du jeu, n'injecte rien, ne modifie aucun fichier du jeu et n'envoie aucune touche. Pendant la
partie, il ne fait que regarder si un nouveau fichier est apparu dans le dossier des replays.

---

## Pages

- **Widget en jeu** : uniquement le total de coffres ouverts (taille, position et opacité
  réglables ; clic droit pour le menu, double-clic pour le tableau de bord).
- **Tableau de bord** : total, dernière partie, moyenne par partie, coffres depuis le dernier
  jeton, aujourd'hui, record, temps de jeu analysé, graphiques.
- **Historique** : toutes les parties (date, durée, mode, classement, éliminations, coffres),
  avec les objets obtenus dans chacune.
- **Récompenses** : tout ce que vous avez obtenu (armes par rareté, soins, objets…), combien de
  fois, depuis quand. C'est aussi ici que l'on désigne le jeton pirate.
- **Étoiles & niveaux** : 5 étoiles par niveau, paliers personnalisables, historique.
- **Replays** : état de l'analyse, aide à l'activation, import des anciennes parties.
- **Paramètres** : widget (taille, position, opacité), notifications, sons,
  sauvegarde/export/restauration, réinitialisation, lancement au démarrage de Windows.

| | |
|---|---|
| ![Historique](docs/history.png) | ![Récompenses](docs/rewards.png) |
| ![Replays](docs/replays.png) | ![Progression](docs/progress.png) |

Données : `%APPDATA%\PirateTracker\` (base SQLite, réglages, sauvegardes automatiques).

---

## Développement

```
pirate_tracker/          application (Python, PySide6)
  replays.py             surveillance du dossier Demos + appel du lecteur
  tracker.py             parties, niveaux, records, jetons
  database.py            SQLite
  items.py               noms lisibles et rareté des objets
  ui/                    widget, pages, effets
replay_reader/           lecteur de replays en C# (voir replay_reader/README.md)
tests/                   tests (dont replay réel téléchargé par la CI)
packaging/               PyInstaller + Inno Setup
```

```bash
pip install -r requirements-dev.txt
dotnet build replay_reader/PirateReplayReader -c Release   # .NET 10
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m pirate_tracker
```

Pour les tests sur replay réel, placez `chapter5season5.replay` (adresse et empreinte dans
`.github/workflows/windows-build.yml`) dans `tests/data/`.

*Projet de fan non affilié à Epic Games. Fortnite est une marque d'Epic Games, Inc. Lecture des
replays : FortniteReplayDecompressor (MIT). Toutes les illustrations sont dessinées en code.*
