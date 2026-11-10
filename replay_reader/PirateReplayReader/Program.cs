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

const string Version = "1.0.0";

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
    /// <summary>Coffre spécial : toute classe autre que le coffre standard.</summary>
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

public class ChestReplayReader : FortniteReplayReader.ReplayReader
{
    public const string StandardChestPath = "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C";
    public const string GenericChestPath = "/PirateTracker/GenericChest.GenericChest_C";
    public const string PlayerPawnPath = "/Game/Athena/PlayerPawn_Athena.PlayerPawn_Athena_C";
    private static readonly string[] NotChestWords = { "Ammo", "Spawner", "Manager", "Component", "GC_", "Cue", "Chestplate" };
    private static readonly HashSet<string> AliasedPaths = new();

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
        if (!name.Contains("Chest", StringComparison.OrdinalIgnoreCase)
            || path.Contains("/Props/", StringComparison.OrdinalIgnoreCase)
            || NotChestWords.Any(w => name.Contains(w, StringComparison.OrdinalIgnoreCase)))
        {
            return null;
        }
        lock (AliasedPaths)
        {
            AliasedPaths.Add(path);
        }
        return GenericChestPath;
    }

    private readonly Dictionary<uint, uint> _channelActor = new();
    internal readonly Dictionary<uint, uint> _pawnToPlayerState = new();
    internal readonly List<(float t, uint chest, string path, uint pawn, bool broken)> _opens = new();
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
            case BaseContainer chest when chest is Chest or FactionChest or ExtraChest:
                _chestsSeen.Add(actor);
                var classPath = CurrentExportPath ?? chest.GetType().Name;
                _chestClassesSeen.Add(classPath);
                if (chest.ReplicatedLootTier > 0)
                {
                    _lootTier[actor] = chest.ReplicatedLootTier;
                }
                // SearchingPawn n'est répliqué qu'au moment où le coffre libère son butin, qu'il soit
                // ouvert ou cassé (vérifié sur replay réel : un coffre cassé a SearchingPawn = celui qui
                // l'a détruit, avec bDestroyed/bInstantDeath dans la même mise à jour).
                if (chest.SearchingPawn is uint pawnId && pawnId != 0)
                {
                    _chestsOpened.Add(actor);
                    _opens.Add((CurrentTime, actor, classPath, pawnId, chest.bDestroyed || chest.bInstantDeath));
                }
                else if (chest.bAlreadySearched == true || chest.SearchAnimationCount > 0)
                {
                    _chestsOpened.Add(actor);
                }
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
            result.AliasedClasses = AliasedPaths.OrderBy(x => x).ToList();
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

        // Un coffre n'est compté qu'une fois, à sa première ouverture par le joueur.
        var seen = new HashSet<uint>();
        foreach (var o in _opens.OrderBy(o => o.t))
        {
            if (ownerPawns.Contains(o.pawn) && seen.Add(o.chest))
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
                    Special = o.path != StandardChestPath,
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
