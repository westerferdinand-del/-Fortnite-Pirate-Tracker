# PirateReplayReader

Petit programme en C# qui lit un replay Fortnite (`.replay`) et écrit en JSON, sur une ligne :

- `chests` : les coffres **ouverts par le joueur qui a enregistré le replay** (instant, identifiant) ;
- `items` : les objets qu'il a ramassés (nom interne, quantité, instant) ;
- la partie : date, durée, mode, classement, éliminations, nom du joueur ;
- des diagnostics : `owner_found`, `chests_seen`, `unknown_chest_classes`, `warnings`.

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

Limites : les replays très anciens (2020, v11) ne contiennent pas `SearchingPawn` → aucun coffre
compté, avec un avertissement. Si une future saison introduit une nouvelle classe de coffre, elle
apparaît dans `unknown_chest_classes` et l'application affiche un avertissement.

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
