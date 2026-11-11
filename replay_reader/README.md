# PirateReplayReader

Petit programme en C# qui lit un replay Fortnite (`.replay`) et écrit en JSON, sur une ligne :

- `chests` : les coffres **ouverts ou cassés par le joueur qui a enregistré le replay** (instant,
  identifiant, classe, `how` = `ouvert` / `cassé`, `special`, niveau de butin) ;
- `items` : les objets qu'il a ramassés (nom interne, quantité, instant) ;
- la partie : date, durée, mode, classement, éliminations, nom du joueur ;
- des diagnostics : `owner_found`, `chests_seen`, `special_chest_classes`, `warnings`.

```bash
dotnet publish PirateReplayReader -c Release -r win-x64 --self-contained true \
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o ../build/reader
../build/reader/PirateReplayReader.exe partie.replay
```

## Comment un coffre est attribué au joueur

Dans le replay, chaque coffre (`Tiered_Chest_Athena` et variantes) réplique la propriété
`SearchingPawn` : le personnage qui l'a fouillé. Le propriétaire du replay est identifié par
`RecorderPlayerState` ; ses personnages sont ceux dont `PlayerState` pointe vers lui. Un coffre est
compté si `SearchingPawn` désigne un de ces personnages, une seule fois par coffre.

Vérifié sur un vrai replay du Chapitre 5 (v32.00) : 86 coffres ouverts dans la partie, 58 avec un
`SearchingPawn` répliqué, et chacun de ces 58 a aussi `SearchAnimationCount > 0` (aucune
recherche « annulée » ne fixe `SearchingPawn`). 5 sont attribués au propriétaire, dont 2 coffres
détruits juste après l'ouverture, qui ne passent jamais par `bAlreadySearched` ; compter seulement
`bAlreadySearched` en aurait donc oublié 2.

**Coffres cassés** : quand un joueur détruit un coffre, Fortnite fixe aussi `SearchingPawn` sur ce
joueur, dans la même mise à jour que `bDestroyed` / `bInstantDeath` (vie à 0). Dans le replay de
test, 2 des 5 coffres du joueur ont été cassés : ils sont comptés et marqués `cassé`. Un coffre
cassé après avoir été ouvert n'est compté qu'une fois, pour celui qui l'a ouvert.

**Coffres spéciaux** : toute classe dont le nom contient « Chest » (hors meubles `/Props/`, caisses
de munitions, composants…) est lue automatiquement comme un coffre grâce à un alias générique
(`NetFieldParser.PathAlias`). Vérifié sur le replay réel : les classes `Tiered_Chest_6_Parent` et
`Tiered_Chest_Athena_FactionChest_Generic_Parent` sont prises en charge sans être déclarées
(résultat identique). Les classes non standard rencontrées sont listées dans `special_chest_classes`.

**Coffres qui se remplissent (saison Treasure Hunters, nov. 2026)** : un coffre peut être rouvert
après s'être rempli. Chaque ouverture compte (et chacune est une chance d'obtenir l'accès à la
Boutique Pirate). `SearchingPawn` n'étant transmis que lorsqu'il change, une réouverture par le même
joueur n'est visible que par l'augmentation de `SearchAnimationCount` : chaque augmentation est une
ouverture, attribuée au joueur transmis ou au dernier connu. Vérification : `--selftest` (11 scénarios
simulés : réouverture par soi / par un autre, coffre déjà ouvert avant d'être visible, joueur transmis
dans une mise à jour séparée, coffre cassé…), exécuté par les tests et la CI.

**Types de coffres** : `category` = `standard`, `trésor` (chasse au trésor), `rare`, `enterré`,
`faction`, `spécial`, d'après le nom de la classe. Seuls rare / enterré / faction / spécial sont
marqués `special` : les coffres normaux d'une nouvelle saison ne le sont plus (bug corrigé en 2.1).

**Architecture de l'analyse (lecteur 1.4)**
1. Lecture : bibliothèque intégrée (`vendor/`).
2. Résolution des classes : toute classe inconnue est lue avec une description générique
   (`PathAliasWithFields`). Les propriétés d'une classe ne sont déclarées dans le replay qu'à leur
   première transmission : on ne peut donc pas trier sur les propriétés à la première apparition.
   Le rôle (coffre / autre conteneur / personnage) est décidé sur les données réellement observées
   (`class_decisions` donne le rôle et la preuve de chaque classe).
3. Identité du joueur : `RecorderPlayerState`, puis tous les `PlayerPawn` dont `PlayerState` pointe
   vers lui (plusieurs personnages en cas de réapparition), et en secours `PawnForReplayRelevancy`.
4. Interactions : ouverture = augmentation de `SearchAnimationCount` ; joueur transmis dans la même
   mise à jour (`direct`) ou dernier ouvreur connu (`direct: false`, signalé). Cassé = ouverture
   accompagnée de `bDestroyed`/`bInstantDeath`. Un coffre détruit après ouverture n'est pas recompté.
5. Statistiques : `total_openings` (réouvertures comprises) et `unique_chests` (coffres différents).
6. Journal : `decisions` (chaque événement de coffre du joueur : compté / ignoré, pourquoi).

Tests : `--selftest` (28 vérifications simulées : ouvert, rouvert ×3, cassé, ouvert puis cassé,
adversaire, plusieurs joueurs, changement de personnage, déjà ouvert, classification) + replay réel
du Chapitre 5 en non-régression.

**Vérifié sur un vrai replay du Chapitre 7** (v43.00, Treasure Hunters, escouade, 11 nov. 2026,
`replays_a_analyser/UnsavedReplay-2026.11.11-11.50.29.replay`, joueur mort et revenu deux fois) :
- Classes de coffres observées : `Tiered_Chest_Athena`, `AlwaysSpawn_NormalChest`,
  `AlwaysSpawn_RareChest`, `B_TieredChest_Relics`, `B_Athena_BuriedChest_Chest`,
  `Tiered_Chest_5_Child`, `BGA_LootCannon_StandardChest_Pirate`, `BGA_ExtractionPointGameplay_Chest`.
- **Bug corrigé (lecteur 1.4)** : à la mort d'un personnage, son `PlayerState` repasse à 0 ; le lecteur
  remplaçait le lien personnage → joueur par 0 et « oubliait » le personnage d'après la relance.
  Résultat : 1 coffre au lieu de 4. Le dernier joueur non nul est désormais conservé.
- **Faux positifs évités (lecteur 1.4)** : en v43, `SearchingPawn` est aussi fixé sans aucune ouverture
  (42 cas sur des coffres dans ce replay : fouille commencée puis abandonnée, ou un même personnage
  sur 8 coffres en 0,5 s). Toutes les vraies ouvertures (165) arrivent avec une augmentation de
  `SearchAnimationCount`. `SearchingPawn` seul ne compte donc plus que dans les vieux replays qui ne
  transmettent jamais ce compteur.
- Les parties analysées par un lecteur plus ancien sont recomptées automatiquement (sans double
  comptage) tant que le fichier replay existe encore.
- Diagnostic brut : variable d'environnement `PIRATE_DUMP=fichier.tsv` (toutes les mises à jour de
  coffres, personnages, ramassages).

Non vérifié faute de données : coffres qui se remplissent puis sont rouverts (aucun dans ce replay).

**Signaux étudiés puis écartés (v3, mesurés sur le replay réel)**
- Butin qui apparaît (`FortPickup.LootInitialPosition`, `bTossedFromContainer`) : `bTossedFromContainer`
  n'est jamais renseigné (0 sur 2 645 objets) ; 3 des 5 ouvertures n'ont aucun objet apparu dans les
  2,5 s, et de nombreuses « rafales » d'objets près du joueur ne viennent d'aucun coffre (butin de
  joueurs éliminés). Trop bruité pour compter.
- Position du coffre : absente du replay (0 sur 92 coffres ; ce sont des objets de la carte).
- Comptage en direct pendant la partie : impossible. Un replay en cours est chiffré et sa clé n'est
  écrite qu'à la fin (`IsLive` + `IsEncrypted` sans clé ; la bibliothèque le refuse).

**En-tête du replay** (`pirate_tracker/replay_header.py`) : quelques octets lus sans décompression
donnent `IsLive` et la présence de la clé. Un replay en cours n'est jamais lu (corrige un faux
« échec » quand Fortnite cessait d'écrire 30 s en pleine partie) ; un replay terminé est lu 3 s
après sa dernière écriture au lieu de 30 s.

Limite : les replays très anciens (2020, v11) ne contiennent pas `SearchingPawn` → aucun coffre
compté, avec un avertissement.

## Bibliothèque intégrée

`vendor/` contient [FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor)
(licence MIT, © 2020-2026 Shiqan, voir `vendor/LICENSE`), commit
`76f74c1f640069afdba71b6468e2f819327893c2`, projets `Unreal.Core`, `Unreal.Encryption`, `OozSharp`,
`FortniteReplayReader`. Modifications, toutes marquées `[PirateTracker]` :

1. `Unreal.Core/ReplayReader.cs` : propriété `CurrentTime` (horodatage de la trame en cours).
2. `FortniteReplayReader/Models/NetFieldExports/Items/BaseContainer.cs` : ajout de `SearchingPawn` ;
   `bAlreadySearched` rendu nullable (distinguer « non modifié » de « faux »).
3. `FortniteReplayReader/Models/NetFieldExports/Items/Chest.cs` : coffres lus en mode `Normal`
   (au lieu de `Debug` uniquement).
4. `Unreal.Core/NetFieldParser.cs` : `PathAlias`, pour lire une classe inconnue avec la description
   d'une classe connue.
5. `Unreal.Core/ReplayReader.cs` : `CurrentExportPath` (classe réelle de l'objet lu).
