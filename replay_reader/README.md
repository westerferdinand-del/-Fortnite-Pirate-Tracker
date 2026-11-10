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
