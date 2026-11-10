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
    public string Kind { get; set; } = "";
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
    public List<ChestOpen> Chests { get; set; } = new();
    public List<ItemPickup> Items { get; set; } = new();
    public int ChestsSeen { get; set; }
    public int ChestsOpenedByAnyone { get; set; }
    /// <summary>Classes de conteneurs « coffre » présentes dans le replay mais non lues (nouvelles saisons).</summary>
    public List<string> UnknownChestClasses { get; set; } = new();
    public List<string> Warnings { get; set; } = new();
}

// Autres classes de coffres vues dans des replays récents (Chapitre 5) : lues comme des coffres.
public abstract class ExtraChest : BaseContainer { }

[NetFieldExportGroup("/Game/Building/ActorBlueprints/Containers/Tiered_Chest_6_Parent.Tiered_Chest_6_Parent_C", minimalParseMode: ParseMode.Normal)]
public class ChestParent6 : ExtraChest { }

[NetFieldExportGroup("/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_Generic_Parent.Tiered_Chest_Athena_FactionChest_Generic_Parent_C", minimalParseMode: ParseMode.Normal)]
public class FactionChestParent : ExtraChest { }

public class ChestReplayReader : FortniteReplayReader.ReplayReader
{
    public static readonly HashSet<string> KnownChestPaths = new()
    {
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C",
        "/Game/Building/ActorBlueprints/Containers/Creative_Tiered_Chest.Creative_Tiered_Chest_C",
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_NoLocks.Tiered_Chest_Athena_FactionChest_NoLocks_C",
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_6_Parent.Tiered_Chest_6_Parent_C",
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_Generic_Parent.Tiered_Chest_Athena_FactionChest_Generic_Parent_C",
    };

    private readonly Dictionary<uint, uint> _channelActor = new();
    private readonly Dictionary<uint, uint> _pawnToPlayerState = new();
    private readonly List<(float t, uint chest, string kind, uint pawn)> _opens = new();
    private readonly HashSet<uint> _chestsSeen = new();
    private readonly HashSet<uint> _chestsOpened = new();
    private readonly Dictionary<uint, string> _pickupItem = new();
    private readonly Dictionary<uint, int> _pickupCount = new();
    private readonly List<(float t, uint pickup, uint pawn)> _pickedUp = new();
    private readonly HashSet<string> _groupPaths = new();
    private int _lastGroupCount;

    private ChestReplayReader() : base(null, ParseMode.Normal) { }

    public static MatchResult Analyze(string path)
    {
        var reader = new ChestReplayReader();
        var replay = reader.ReadReplay(path);
        return reader.BuildResult(path, replay);
    }

    protected override void OnChannelOpened(uint channelIndex, NetworkGUID? actor)
    {
        base.OnChannelOpened(channelIndex, actor);
        if (actor != null)
        {
            _channelActor[channelIndex] = actor.Value;
        }
        SnapshotGroups();
    }

    private void SnapshotGroups()
    {
        var map = _netGuidCache?.NetFieldExportGroupMap;
        if (map != null && map.Count != _lastGroupCount)
        {
            _lastGroupCount = map.Count;
            _groupPaths.UnionWith(map.Keys);
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
            case PlayerPawn pawn when pawn.PlayerState.HasValue:
                _pawnToPlayerState[actor] = pawn.PlayerState.Value;
                break;

            // Coffres uniquement (les caisses de munitions et autres conteneurs sont ignorés)
            case BaseContainer chest when chest is Chest or FactionChest or ExtraChest:
                _chestsSeen.Add(actor);
                // SearchingPawn n'est répliqué qu'au moment de l'ouverture (vérifié sur replay réel :
                // chaque coffre avec SearchingPawn a aussi SearchAnimationCount > 0).
                if (chest.SearchingPawn is uint pawnId && pawnId != 0)
                {
                    _chestsOpened.Add(actor);
                    _opens.Add((CurrentTime, actor, chest.GetType().Name, pawnId));
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

    private MatchResult BuildResult(string path, FortniteReplayReader.Models.FortniteReplay replay)
    {
        SnapshotGroups();
        var result = new MatchResult
        {
            File = path,
            Branch = replay.Header?.Branch,
            FriendlyName = replay.Info?.FriendlyName,
            StartedUtc = replay.GameData?.UtcTimeStartedMatch ?? replay.Info?.Timestamp,
            DurationS = (replay.Info?.LengthInMs ?? 0) / 1000.0,
            IsLive = replay.Info?.IsLive ?? false,
            Playlist = replay.GameData?.CurrentPlaylist,
            SessionId = replay.GameData?.GameSessionId,
            Placement = replay.TeamStats?.Position is > 0 ? replay.TeamStats.Position : null,
            TotalPlayers = replay.TeamStats?.TotalPlayers is > 0 ? replay.TeamStats.TotalPlayers : null,
            Eliminations = replay.Stats?.Eliminations,
            ChestsSeen = _chestsSeen.Count,
            ChestsOpenedByAnyone = _chestsOpened.Count,
        };

        var owner = replay.PlayerData?.FirstOrDefault(p => p.IsReplayOwner);
        result.PlayerName = owner?.PlayerName;

        var recorder = replay.GameData?.RecorderId;
        var ownerPawns = recorder.HasValue
            ? _pawnToPlayerState.Where(kv => kv.Value == recorder.Value).Select(kv => kv.Key).ToHashSet()
            : new HashSet<uint>();
        result.OwnerFound = ownerPawns.Count > 0;
        if (!recorder.HasValue)
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
                result.Chests.Add(new ChestOpen { T = MathF.Round(o.t, 1), Id = o.chest, Kind = o.kind });
            }
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

        result.UnknownChestClasses = _groupPaths
            .Where(p => p.Contains("/Containers/Tiered_Chest", StringComparison.OrdinalIgnoreCase)
                        && !KnownChestPaths.Contains(p))
            .OrderBy(p => p)
            .ToList();
        if (result.UnknownChestClasses.Count > 0)
        {
            result.Warnings.Add("Nouveaux types de coffres non pris en charge : " + string.Join(", ", result.UnknownChestClasses));
        }
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
