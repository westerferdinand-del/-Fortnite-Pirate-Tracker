// PirateReplayReader : lit un replay Fortnite (.replay) et écrit en JSON :
//  - les coffres ouverts par le joueur qui a enregistré le replay,
//  - les objets qu'il a ramassés,
//  - les informations de la partie (date, durée, classement, éliminations).
//
// Usage : PirateReplayReader <fichier.replay> [<fichier2.replay> ...]
// Sortie : une ligne JSON par replay sur stdout.
//
// S'appuie sur FortniteReplayDecompressor (MIT, © Shiqan), copié dans ../vendor avec
// quelques modifications documentées dans ../README.md.
using System.Text.Json;
using System.Text.Json.Serialization;
using FortniteReplayReader.Models.NetFieldExports;
using FortniteReplayReader.Models.NetFieldExports.Items;
using Unreal.Core.Attributes;
using Unreal.Core.Contracts;
using Unreal.Core.Models;
using Unreal.Core.Models.Enums;

const string Version = "1.2.0";

var jsonOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
};

if (args.Length == 0 || args[0] is "-h" or "--help")
{
    Console.Error.WriteLine("Usage : PirateReplayReader <fichier.replay> [...]");
    return 2;
}
if (args[0] == "--selftest")
{
    return ChestReplayReader.SelfTest();
}
if (args[0] == "--version")
{
    Console.WriteLine(Version);
    return 0;
}

var exit = 0;
foreach (var path in args)
{
    MatchResult result;
    try
    {
        result = ChestReplayReader.Analyze(path);
    }
    catch (Exception ex)
    {
        result = new MatchResult { File = path, Ok = false, Error = $"{ex.GetType().Name}: {ex.Message}" };
        exit = 1;
    }
    result.ReaderVersion = Version;
    Console.WriteLine(JsonSerializer.Serialize(result, jsonOptions));
}
return exit;

public class ChestOpen
{
    public float T { get; set; }
    public uint Id { get; set; }
    /// <summary>Nom court de la classe du coffre (ex. Tiered_Chest_Athena).</summary>
    public string Kind { get; set; } = "";
    /// <summary>« ouvert » (fouillé) ou « cassé » (détruit par le joueur).</summary>
    public string How { get; set; } = "ouvert";
    /// <summary>standard, trésor (chasse au trésor), rare, enterré, faction, spécial.</summary>
    public string Category { get; set; } = "standard";
    /// <summary>Coffre spécial : rare, enterré, de faction, de coffre-fort… (pas les coffres normaux de la saison).</summary>
    public bool Special { get; set; }
    public int? LootTier { get; set; }
}

public class ItemPickup
{
    public float T { get; set; }
    public string Item { get; set; } = "";
    public int Count { get; set; }
}

public class MatchResult
{
    public bool Ok { get; set; } = true;
    public string? Error { get; set; }
    public string File { get; set; } = "";
    public string? ReaderVersion { get; set; }
    public string? Branch { get; set; }
    public string? FriendlyName { get; set; }
    public DateTime? StartedUtc { get; set; }
    public double DurationS { get; set; }
    public bool IsLive { get; set; }
    public string? Playlist { get; set; }
    public string? SessionId { get; set; }
    public string? PlayerName { get; set; }
    public uint? Placement { get; set; }
    public uint? TotalPlayers { get; set; }
    public uint? Eliminations { get; set; }
    public bool OwnerFound { get; set; }
    public bool Partial { get; set; }
    public int RelevancyPawns { get; set; }
    public List<ChestOpen> Chests { get; set; } = new();
    public List<ItemPickup> Items { get; set; } = new();
    public int ChestsSeen { get; set; }
    /// <summary>Coffres détruits sans aucune ouverture connue (ni ouvreur, ni compteur) : peut-être cassés sans être attribués.</summary>
    public int ChestsDestroyedUnattributed { get; set; }
    /// <summary>Conteneurs NON comptés comme coffres que le joueur a fouillés (classe → nombre).</summary>
    public Dictionary<string, int> OtherContainersSearched { get; set; } = new();
    /// <summary>Coffres comptés, par classe exacte (classe → nombre).</summary>
    public Dictionary<string, int> ChestClassesOpened { get; set; } = new();
    public int PawnsSeen { get; set; }
    public int OwnerPawns { get; set; }
    public int ChestSearchesSeen { get; set; }
    public List<string> AliasedClasses { get; set; } = new();
    public int ChestsOpenedByAnyone { get; set; }
    /// <summary>Classes de coffres non standard rencontrées (coffres spéciaux, nouvelles saisons).</summary>
    public List<string> SpecialChestClasses { get; set; } = new();
    public List<string> Warnings { get; set; } = new();
}

public abstract class ExtraChest : BaseContainer { }

// Classe générique : toute classe de coffre inconnue est lue avec la description d'un coffre
// (propriétés associées par nom : SearchingPawn, bAlreadySearched, bDestroyed…).
[NetFieldExportGroup(ChestReplayReader.GenericChestPath, minimalParseMode: ParseMode.Normal)]
public class GenericChest : ExtraChest { }

[NetFieldExportGroup(ChestReplayReader.GenericContainerPath, minimalParseMode: ParseMode.Normal)]
public class GenericContainer : BaseContainer { }

public class ChestReplayReader : FortniteReplayReader.ReplayReader
{
    public const string StandardChestPath = "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C";
    public const string GenericChestPath = "/PirateTracker/GenericChest.GenericChest_C";
    public const string PlayerPawnPath = "/Game/Athena/PlayerPawn_Athena.PlayerPawn_Athena_C";
    private static readonly string[] NotChestWords = { "Ammo", "Spawner", "Manager", "Component", "GC_", "Cue", "Chestplate" };
    private static readonly HashSet<string> AliasedPaths = new();
    private static readonly string[] ContainerWords = { "Container", "Cache", "Loot", "Stash", "Crate", "Coffer", "Safe" };
    public const string GenericContainerPath = "/PirateTracker/GenericContainer.GenericContainer_C";

    /// <summary>Une classe inconnue est-elle un coffre ? (nom contenant « Chest », hors meubles et caisses de munitions)</summary>
    public static string? ChestAlias(string path)
    {
        var name = path[(path.LastIndexOf('/') + 1)..];
        // Personnage d'une nouvelle saison (classe renommée) : lu comme PlayerPawn_Athena
        if (name.Contains("PlayerPawn", StringComparison.OrdinalIgnoreCase)
            && !name.Contains("Cache", StringComparison.OrdinalIgnoreCase)
            && !name.Contains("Component", StringComparison.OrdinalIgnoreCase))
        {
            lock (AliasedPaths)
            {
                AliasedPaths.Add(path);
            }
            return PlayerPawnPath;
        }
        var looksLikeChest = (name.Contains("Chest", StringComparison.OrdinalIgnoreCase)
                              || name.Contains("Treasure", StringComparison.OrdinalIgnoreCase))
                             && !path.Contains("/Props/", StringComparison.OrdinalIgnoreCase)
                             && !NotChestWords.Any(w => name.Contains(w, StringComparison.OrdinalIgnoreCase));
        // Autres conteneurs fouillables (caisses de munitions, meubles, nouveautés…) : lus pour le
        // diagnostic, jamais comptés comme coffres.
        var looksLikeContainer = path.StartsWith("/", StringComparison.Ordinal)
                                 && !name.Contains("ClassNetCache", StringComparison.OrdinalIgnoreCase)
                                 && !name.Contains("Component", StringComparison.OrdinalIgnoreCase)
                                 && (path.Contains("/Containers/", StringComparison.OrdinalIgnoreCase)
                                     || ContainerWords.Any(w => name.Contains(w, StringComparison.OrdinalIgnoreCase)));
        if (!looksLikeChest && !looksLikeContainer)
        {
            return null;
        }
        if (looksLikeChest)
        {
            lock (AliasedPaths)
            {
                AliasedPaths.Add(path);
            }
        }
        return looksLikeChest ? GenericChestPath : GenericContainerPath;
    }

    private readonly Dictionary<uint, uint> _channelActor = new();
    internal readonly Dictionary<uint, uint> _pawnToPlayerState = new();
    internal readonly List<(float t, uint chest, string path, uint pawn, bool broken)> _opens = new();
    private readonly List<(string path, uint pawn)> _otherSearches = new();
    private readonly HashSet<(uint, uint)> _otherSearchKeys = new();
    private uint? _recorderId;
    private readonly HashSet<uint> _relevancyPawns = new();
    private readonly Dictionary<uint, int> _lootTier = new();
    private readonly HashSet<string> _chestClassesSeen = new();
    private readonly HashSet<uint> _chestsSeen = new();
    private readonly HashSet<uint> _chestsOpened = new();
    private readonly Dictionary<uint, string> _pickupItem = new();
    private readonly Dictionary<uint, int> _pickupCount = new();
    private readonly List<(float t, uint pickup, uint pawn)> _pickedUp = new();

    private ChestReplayReader() : base(null, ParseMode.Normal) { }

    private new float CurrentTime
    {
        get => _timeOverride ?? base.CurrentTime;
        set => _timeOverride = value;
    }
    private float? _timeOverride;

    public static MatchResult Analyze(string path)
    {
        Unreal.Core.NetFieldParser.PathAlias = ChestAlias;
        lock (AliasedPaths)
        {
            AliasedPaths.Clear();
        }
        var reader = new ChestReplayReader();
        FortniteReplayReader.Models.FortniteReplay? replay = null;
        Exception? error = null;
        try
        {
            replay = reader.ReadReplay(path);
        }
        catch (Exception ex) when (ex is not FileNotFoundException and not DirectoryNotFoundException
                                       and not UnauthorizedAccessException)
        {
            // Replay coupé (partie quittée brutalement, jeu fermé, plantage) : on garde ce qui a été lu.
            error = ex;
        }
        if (replay == null && reader._opens.Count == 0 && reader._pawnToPlayerState.Count == 0)
        {
            throw error ?? new InvalidDataException("Replay vide");
        }
        var result = reader.BuildResult(path, replay);
        if (error != null)
        {
            result.Partial = true;
            result.Warnings.Add($"Replay incomplet (partie quittée ou jeu fermé) : coffres comptés jusqu'à {reader.CurrentTime / 60:F0} min.");
        }
        return result;
    }

    protected override void OnChannelOpened(uint channelIndex, NetworkGUID? actor)
    {
        base.OnChannelOpened(channelIndex, actor);
        if (actor != null)
        {
            _channelActor[channelIndex] = actor.Value;
        }
    }

    protected override void OnExportRead(uint channelIndex, INetFieldExportGroup? exportGroup)
    {
        base.OnExportRead(channelIndex, exportGroup);
        if (!_channelActor.TryGetValue(channelIndex, out var actor))
        {
            return;
        }

        switch (exportGroup)
        {
            case FortniteReplayReader.Models.NetFieldExports.GameState gs:
                if (gs.RecorderPlayerState?.Value is uint rec && rec != 0)
                {
                    _recorderId = rec;
                }
                // Personnage suivi par le replay = celui du joueur qui l'enregistre
                if (gs.PawnForReplayRelevancy is uint rel && rel != 0)
                {
                    _relevancyPawns.Add(rel);
                }
                break;

            case PlayerPawn pawn when pawn.PlayerState.HasValue:
                _pawnToPlayerState[actor] = pawn.PlayerState.Value;
                break;

            // Coffres uniquement (les caisses de munitions et autres conteneurs sont ignorés)
            case BaseContainer other when other is not (Chest or FactionChest or ExtraChest):
                // Conteneur qui n'est pas un coffre : on note qui le fouille (diagnostic)
                if (other.SearchingPawn is uint sp && sp != 0 && _otherSearchKeys.Add((actor, sp)))
                {
                    _otherSearches.Add((CurrentExportPath ?? other.GetType().Name, sp));
                }
                break;

            case BaseContainer chest when chest is Chest or FactionChest or ExtraChest:
                _chestsSeen.Add(actor);
                var classPath = CurrentExportPath ?? chest.GetType().Name;
                _chestClassesSeen.Add(classPath);
                if (chest.ReplicatedLootTier > 0)
                {
                    _lootTier[actor] = chest.ReplicatedLootTier;
                }
                RecordChestUpdate(actor, classPath, chest);
                break;

            case FortPickup pickup:
                if (pickup.ItemDefinition?.Name is string name && name.Length > 0)
                {
                    _pickupItem[actor] = name;
                }
                if (pickup.Count is int count)
                {
                    _pickupCount[actor] = count;
                }
                if (pickup.PickupTarget is uint target && target != 0)
                {
                    _pickedUp.Add((CurrentTime, actor, target));
                }
                break;
        }
    }

    // État par coffre : dernier compteur d'ouvertures vu, dernier joueur qui l'a fouillé.
    private readonly Dictionary<uint, uint> _chestAnim = new();
    private readonly Dictionary<uint, uint> _chestPawn = new();
    private readonly HashSet<uint> _countedViaPawnOnly = new();
    private readonly Dictionary<uint, float> _animWithoutPawnAt = new();
    private readonly HashSet<uint> _hasOpening = new();
    private readonly HashSet<uint> _chestsDestroyed = new();

    /// <summary>
    /// Détecte chaque ouverture d'un coffre, y compris les réouvertures (les coffres se remplissent
    /// à nouveau depuis la saison Treasure Hunters, nov. 2026).
    ///
    /// SearchingPawn (le joueur qui fouille) n'est répliqué que lorsqu'il change : si le même joueur
    /// rouvre un coffre rempli, seul SearchAnimationCount augmente. Chaque augmentation de ce compteur
    /// est donc une ouverture, attribuée au joueur de la mise à jour ou, à défaut, au dernier connu.
    /// Un coffre déjà ouvert quand il devient visible (compteur > 0 sans joueur) n'est pas attribué.
    /// </summary>
    private void RecordChestUpdate(uint actor, string classPath, BaseContainer chest)
    {
        uint? pawn = chest.SearchingPawn is uint p && p != 0 ? p : null;
        var anim = chest.SearchAnimationCount;  // 0 = non transmis dans cette mise à jour
        var broken = chest.bDestroyed || chest.bInstantDeath;
        if (pawn.HasValue)
        {
            _chestPawn[actor] = pawn.Value;
        }
        if (anim > 0 || pawn.HasValue || chest.bAlreadySearched == true)
        {
            _chestsOpened.Add(actor);
        }
        if (broken)
        {
            _chestsDestroyed.Add(actor);
        }

        var opens = 0;
        if (anim > 0)
        {
            if (_chestAnim.TryGetValue(actor, out var last))
            {
                opens = anim > last ? (int)Math.Min(anim - last, 20) : 0;
                _chestAnim[actor] = Math.Max(anim, last);
            }
            else
            {
                // Première fois que l'on voit son compteur : ouverture comptée seulement si le joueur
                // est transmis avec (sinon le coffre avait été ouvert avant d'être visible).
                opens = pawn.HasValue && !_countedViaPawnOnly.Contains(actor) ? 1 : 0;
                if (!pawn.HasValue)
                {
                    _animWithoutPawnAt[actor] = CurrentTime;
                }
                _chestAnim[actor] = anim;
            }
        }
        else if (pawn.HasValue && _animWithoutPawnAt.TryGetValue(actor, out var seenAt)
                 && CurrentTime - seenAt <= 2.0f && !_hasOpening.Contains(actor))
        {
            opens = 1;  // le joueur arrive juste après le compteur, dans une mise à jour séparée
        }
        else if (pawn.HasValue && !_chestAnim.ContainsKey(actor) && _countedViaPawnOnly.Add(actor))
        {
            opens = 1;  // joueur transmis sans compteur (anciennes versions du jeu)
        }

        if (opens > 0 && (pawn ?? _chestPawn.GetValueOrDefault(actor)) is uint who && who != 0)
        {
            for (var i = 0; i < opens; i++)
            {
                _opens.Add((CurrentTime, actor, classPath, who, broken));
            }
            _hasOpening.Add(actor);
            _animWithoutPawnAt.Remove(actor);
        }
    }

    /// <summary>Scénarios simulés de mises à jour de coffres (exécutés par les tests et la CI).</summary>
    public static int SelfTest()
    {
        const uint ME = 100, OTHER = 200;
        var failures = new List<string>();
        void Check(string name, IEnumerable<(float t, uint chest, uint? pawn, uint anim, bool destroyed)> updates,
                   int expectedMine, int expectedBroken = 0)
        {
            var r = new ChestReplayReader();
            foreach (var u in updates)
            {
                r.CurrentTime = u.t;
                var c = new GenericChest { SearchingPawn = u.pawn, SearchAnimationCount = u.anim, bDestroyed = u.destroyed };
                r.RecordChestUpdate(u.chest, StandardChestPath, c);
            }
            var mine = r._opens.Where(o => o.pawn == ME).ToList();
            if (mine.Count != expectedMine || mine.Count(o => o.broken) != expectedBroken)
            {
                failures.Add($"{name}: {mine.Count} ouvertures ({mine.Count(o => o.broken)} cassées), attendu {expectedMine} ({expectedBroken})");
            }
        }
        Check("ouverture simple", new[] { (10f, 1u, (uint?)ME, 1u, false) }, 1);
        Check("même mise à jour répétée", new[] { (10f, 1u, (uint?)ME, 1u, false), (11f, 1u, (uint?)null, 1u, false) }, 1);
        Check("rempli puis rouvert par moi", new[] { (10f, 1u, (uint?)ME, 1u, false), (100f, 1u, (uint?)null, 2u, false) }, 2);
        Check("rouvert 3 fois", new[] { (10f, 1u, (uint?)ME, 1u, false), (100f, 1u, (uint?)null, 2u, false),
                                        (200f, 1u, (uint?)null, 3u, false) }, 3);
        Check("rouvert par un autre", new[] { (10f, 1u, (uint?)ME, 1u, false), (100f, 1u, (uint?)OTHER, 2u, false) }, 1);
        Check("ouvert par un autre puis par moi", new[] { (10f, 1u, (uint?)OTHER, 1u, false), (100f, 1u, (uint?)ME, 2u, false) }, 1);
        Check("déjà ouvert avant d'être visible", new[] { (10f, 1u, (uint?)null, 1u, false) }, 0);
        Check("joueur transmis juste après", new[] { (10f, 1u, (uint?)null, 1u, false), (10.5f, 1u, (uint?)ME, 0u, false) }, 1);
        Check("joueur transmis bien plus tard", new[] { (10f, 1u, (uint?)null, 1u, false), (60f, 1u, (uint?)ME, 0u, false) }, 0);
        Check("cassé", new[] { (10f, 1u, (uint?)ME, 1u, true) }, 1, 1);
        Check("deux coffres", new[] { (10f, 1u, (uint?)ME, 1u, false), (20f, 2u, (uint?)ME, 1u, false) }, 2);
        foreach (var f in failures)
        {
            Console.Error.WriteLine("ÉCHEC " + f);
        }
        Console.WriteLine(failures.Count == 0 ? "selftest OK (11 scénarios)" : $"selftest : {failures.Count} échec(s)");
        return failures.Count == 0 ? 0 : 1;
    }

    /// <summary>Catégorie lisible d'un coffre d'après le nom de sa classe.</summary>
    public static (string category, bool special) ChestCategory(string path)
    {
        var n = path[(path.LastIndexOf('/') + 1)..].ToLowerInvariant();
        if (n.Contains("rare")) return ("rare", true);
        if (n.Contains("buried")) return ("enterré", true);
        if (n.Contains("faction") || n.Contains("society") || n.Contains("oath")) return ("faction", true);
        if (n.Contains("vault") || n.Contains("bunker") || n.Contains("mythic") || n.Contains("boss")) return ("spécial", true);
        if (n.Contains("treasure")) return ("trésor", false);
        return ("standard", false);
    }

    private MatchResult BuildResult(string path, FortniteReplayReader.Models.FortniteReplay? replay)
    {
        var result = new MatchResult
        {
            File = path,
            Branch = replay?.Header?.Branch ?? Replay?.Header?.Branch,
            FriendlyName = replay?.Info?.FriendlyName ?? Replay?.Info?.FriendlyName,
            StartedUtc = replay?.GameData?.UtcTimeStartedMatch ?? replay?.Info?.Timestamp ?? Replay?.Info?.Timestamp,
            DurationS = replay?.Info?.LengthInMs is uint ms && ms > 0 ? ms / 1000.0 : CurrentTime,
            IsLive = replay?.Info?.IsLive ?? Replay?.Info?.IsLive ?? false,
            Playlist = replay?.GameData?.CurrentPlaylist,
            SessionId = replay?.GameData?.GameSessionId,
            Placement = replay?.TeamStats?.Position is > 0 ? replay.TeamStats.Position : null,
            TotalPlayers = replay?.TeamStats?.TotalPlayers is > 0 ? replay.TeamStats.TotalPlayers : null,
            Eliminations = replay?.Stats?.Eliminations,
            ChestsSeen = _chestsSeen.Count,
            ChestsOpenedByAnyone = _chestsOpened.Count,
        };

        var owner = replay?.PlayerData?.FirstOrDefault(p => p.IsReplayOwner);
        result.PlayerName = owner?.PlayerName;

        var recorder = replay?.GameData?.RecorderId ?? _recorderId;
        var ownerPawns = recorder.HasValue
            ? _pawnToPlayerState.Where(kv => kv.Value == recorder.Value).Select(kv => kv.Key).ToHashSet()
            : new HashSet<uint>();
        // Secours : personnage suivi par le replay (PawnForReplayRelevancy), indépendant des classes de personnage
        ownerPawns.UnionWith(_relevancyPawns);
        result.RelevancyPawns = _relevancyPawns.Count;
        result.OwnerFound = ownerPawns.Count > 0;
        result.PawnsSeen = _pawnToPlayerState.Count;
        result.OwnerPawns = ownerPawns.Count;
        result.ChestSearchesSeen = _opens.Select(o => o.chest).Distinct().Count();
        lock (AliasedPaths)
        {
            result.AliasedClasses = AliasedPaths.Select(p => p[(p.LastIndexOf('/') + 1)..].Split('.')[0]).OrderBy(x => x).ToList();
        }
        if (_chestsSeen.Count == 0 && result.DurationS > 120)
        {
            result.Warnings.Add("Aucun coffre reconnu dans ce replay : les coffres de cette saison ne sont pas encore pris en charge.");
        }
        if (_pawnToPlayerState.Count == 0 && result.DurationS > 60)
        {
            result.Warnings.Add("Aucun personnage reconnu dans ce replay : format de cette saison non pris en charge.");
        }
        if (!recorder.HasValue && ownerPawns.Count == 0)
        {
            result.Warnings.Add("Joueur propriétaire du replay introuvable (RecorderPlayerState absent).");
        }
        else if (ownerPawns.Count == 0)
        {
            result.Warnings.Add("Aucun personnage associé au propriétaire du replay.");
        }

        // Chaque ouverture compte (un coffre rempli à nouveau puis rouvert = 2 ouvertures).
        foreach (var o in _opens.OrderBy(o => o.t))
        {
            if (ownerPawns.Contains(o.pawn))
            {
                var shortName = o.path[(o.path.LastIndexOf('/') + 1)..];
                if (shortName.Contains('.'))
                {
                    shortName = shortName[..shortName.IndexOf('.')];
                }
                result.Chests.Add(new ChestOpen
                {
                    T = MathF.Round(o.t, 1),
                    Id = o.chest,
                    Kind = shortName,
                    How = o.broken ? "cassé" : "ouvert",
                    Category = ChestCategory(o.path).category,
                    Special = ChestCategory(o.path).special,
                    LootTier = _lootTier.TryGetValue(o.chest, out var tier) ? tier : null,
                });
            }
        }

        if (result.Chests.Count == 0 && result.ChestSearchesSeen > 0 && _pickedUp.All(p => !ownerPawns.Contains(p.pawn))
            && result.DurationS > 180)
        {
            result.Warnings.Add("Des coffres ont été ouverts dans la partie mais aucun coffre ni objet n'est attribué au joueur : "
                                + "son personnage n'a probablement pas été identifié.");
        }

        static string Short(string path)
        {
            var n = path[(path.LastIndexOf('/') + 1)..];
            return n.Contains('.') ? n[..n.IndexOf('.')] : n;
        }
        result.OtherContainersSearched = _otherSearches.Where(o => ownerPawns.Contains(o.pawn))
            .GroupBy(o => Short(o.path)).OrderByDescending(g => g.Count()).ToDictionary(g => g.Key, g => g.Count());
        result.ChestClassesOpened = result.Chests.GroupBy(c => c.Kind).ToDictionary(g => g.Key, g => g.Count());
        result.ChestsDestroyedUnattributed = _chestsDestroyed.Count(c => !_hasOpening.Contains(c) && !_chestAnim.ContainsKey(c));

        var seenPickups = new HashSet<uint>();
        foreach (var p in _pickedUp.OrderBy(p => p.t))
        {
            if (ownerPawns.Contains(p.pawn) && seenPickups.Add(p.pickup) && _pickupItem.TryGetValue(p.pickup, out var item))
            {
                result.Items.Add(new ItemPickup
                {
                    T = MathF.Round(p.t, 1),
                    Item = item,
                    Count = _pickupCount.TryGetValue(p.pickup, out var c) ? c : 0,
                });
            }
        }

        result.SpecialChestClasses = _chestClassesSeen
            .Where(p => p != StandardChestPath)
            .OrderBy(p => p)
            .ToList();
        if (_chestsOpened.Count > 0 && _opens.Count == 0)
        {
            result.Warnings.Add("Ce replay n'indique pas qui ouvre les coffres (version de Fortnite trop ancienne) : coffres non comptés.");
        }
        if (result.IsLive)
        {
            result.Warnings.Add("Replay encore en cours d'enregistrement.");
        }
        return result;
    }
}
