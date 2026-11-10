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

const string Version = "1.3.0";

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
    /// <summary>true : le joueur est transmis avec l'ouverture ; false : déduit (dernier ouvreur connu du coffre).</summary>
    public bool Direct { get; set; } = true;
    /// <summary>Réouverture d'un coffre déjà ouvert (rempli à nouveau).</summary>
    public bool Reopen { get; set; }
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
    /// <summary>Coffres différents ouverts ou cassés par le joueur.</summary>
    public int UniqueChests { get; set; }
    /// <summary>Total des ouvertures (réouvertures comprises ; un coffre cassé = 1).</summary>
    public int TotalOpenings { get; set; }
    /// <summary>Ouvertures dont l'ouvreur est déduit (non transmis dans la même mise à jour).</summary>
    public int InferredOpenings { get; set; }
    public List<uint> OwnerPawnIds { get; set; } = new();
    /// <summary>Rôle attribué à chaque classe inconnue rencontrée, et pourquoi.</summary>
    public Dictionary<string, string> ClassDecisions { get; set; } = new();
    /// <summary>Journal des événements de coffres concernant le joueur (compté / ignoré, pourquoi).</summary>
    public List<string> Decisions { get; set; } = new();
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

// Tout objet inconnu : lu avec les propriétés d'un conteneur ; son rôle dépend de ce qui est observé.
[NetFieldExportGroup(ChestReplayReader.GenericProbePath, minimalParseMode: ParseMode.Normal)]
public class GenericProbe : BaseContainer { }

public class ChestReplayReader : FortniteReplayReader.ReplayReader
{
    public const string StandardChestPath = "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C";
    public const string GenericChestPath = "/PirateTracker/GenericChest.GenericChest_C";
    public const string PlayerPawnPath = "/Game/Athena/PlayerPawn_Athena.PlayerPawn_Athena_C";
    private static readonly string[] NotChestWords = { "Ammo", "Spawner", "Manager", "Component", "GC_", "Cue", "Chestplate" };
    private static readonly HashSet<string> AliasedPaths = new();
    private static readonly string[] ContainerWords = { "Container", "Cache", "Loot", "Stash", "Crate", "Coffer", "Safe" };
    public const string GenericContainerPath = "/PirateTracker/GenericContainer.GenericContainer_C";
    public const string GenericProbePath = "/PirateTracker/GenericProbe.GenericProbe_C";

    /// <summary>Une classe inconnue est-elle un coffre ? (nom contenant « Chest », hors meubles et caisses de munitions)</summary>
    /// <summary>Classes rencontrées et rôle attribué (coffre / autre conteneur / personnage) avec la raison.</summary>
    private static readonly Dictionary<string, (string role, string reason)> ClassEvidence = new();

    /// <summary>
    /// Reconnaît une classe inconnue d'après les propriétés qu'elle réplique (preuve observée dans le
    /// replay) : tout objet qui réplique SearchingPawn / bAlreadySearched / SearchAnimationCount est un
    /// conteneur fouillable, quel que soit son nom. Parmi eux, seuls ceux nommés comme des coffres
    /// (Chest / Treasure, hors meubles et caisses de munitions) sont comptés.
    /// </summary>
    public static string? AliasWithFields(string path, IReadOnlyCollection<string> fields)
    {
        // Les propriétés d'une classe ne sont déclarées dans le replay qu'au moment où elles sont
        // transmises pour la première fois : à la première apparition d'un coffre, SearchingPawn n'est
        // pas encore connu. On ne peut donc pas trier sur les propriétés à ce moment-là : tout objet
        // inconnu est lu avec une description générique, et son rôle est décidé sur les données
        // réellement observées pendant la partie (voir OnExportRead).
        var name = path[(path.LastIndexOf('/') + 1)..];
        if (name.Contains("ClassNetCache", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }
        if (name.Contains("PlayerPawn", StringComparison.OrdinalIgnoreCase)
            && !name.Contains("Component", StringComparison.OrdinalIgnoreCase))
        {
            lock (AliasedPaths)
            {
                AliasedPaths.Add(path);
                ClassEvidence[path] = ("personnage", "nom de classe PlayerPawn");
            }
            return PlayerPawnPath;
        }
        if (IsChestName(path))
        {
            lock (AliasedPaths)
            {
                AliasedPaths.Add(path);
            }
            return GenericChestPath;
        }
        return GenericProbePath;
    }

    /// <summary>Nom de classe d'un coffre (et non d'un meuble, d'une caisse de munitions…).</summary>
    public static bool IsChestName(string path)
    {
        var name = path[(path.LastIndexOf('/') + 1)..];
        return (name.Contains("Chest", StringComparison.OrdinalIgnoreCase)
                || name.Contains("Treasure", StringComparison.OrdinalIgnoreCase))
               && !path.Contains("/Props/", StringComparison.OrdinalIgnoreCase)
               && !NotChestWords.Any(w => name.Contains(w, StringComparison.OrdinalIgnoreCase));
    }

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
    internal readonly List<(float t, uint chest, string path, uint pawn, bool broken, bool direct, bool reopen)> _opens = new();
    /// <summary>Journal : chaque événement de coffre et la décision prise (compté ou ignoré, pourquoi).</summary>
    internal readonly List<(float t, uint chest, string path, string evt, uint pawn, string note)> _log = new();
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
        Unreal.Core.NetFieldParser.PathAliasWithFields = AliasWithFields;
        lock (AliasedPaths)
        {
            AliasedPaths.Clear();
            ClassEvidence.Clear();
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
                if (other is GenericProbe && !(other.SearchingPawn > 0 || other.SearchAnimationCount > 0
                                               || other.bAlreadySearched.HasValue))
                {
                    break;  // objet inconnu sans aucune donnée de conteneur : ignoré
                }
                NoteEvidence(CurrentExportPath, "autre conteneur",
                             "données de fouille observées, nom non reconnu comme coffre : NON compté");
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
                if (chest.SearchingPawn > 0 || chest.SearchAnimationCount > 0 || chest.bAlreadySearched.HasValue)
                {
                    NoteEvidence(classPath, "coffre", chest is GenericChest
                        ? "classe inconnue : nom de coffre + données de fouille observées : compté"
                        : "classe de coffre connue : compté");
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

    private static void NoteEvidence(string? path, string role, string reason)
    {
        if (path == null)
        {
            return;
        }
        lock (AliasedPaths)
        {
            ClassEvidence.TryAdd(path, (role, reason));
        }
    }

    // État par coffre : dernier compteur d'ouvertures vu, dernier joueur qui l'a fouillé.
    private readonly Dictionary<uint, uint> _chestAnim = new();
    private readonly Dictionary<uint, uint> _chestPawn = new();
    private readonly HashSet<uint> _countedViaPawnOnly = new();
    private readonly Dictionary<uint, float> _animWithoutPawnAt = new();
    private readonly HashSet<uint> _hasOpening = new();
    private readonly HashSet<uint> _chestsDestroyed = new();
    private readonly HashSet<uint> _loggedDestroy = new();


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
                    _log.Add((CurrentTime, actor, classPath, "déjà ouvert", 0,
                              "ignoré : déjà ouvert quand il est devenu visible (ouvreur inconnu)"));
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
                var reopen = _hasOpening.Contains(actor) || i > 0;
                _opens.Add((CurrentTime, actor, classPath, who, broken && i == 0, pawn.HasValue, reopen));
                _log.Add((CurrentTime, actor, classPath, broken ? "cassé" : (reopen ? "réouverture" : "ouverture"), who,
                          pawn.HasValue ? "joueur transmis avec l'ouverture" : "joueur déduit (dernier ouvreur connu)"));
                _hasOpening.Add(actor);
            }
            _animWithoutPawnAt.Remove(actor);
        }
        else if (opens > 0)
        {
            _log.Add((CurrentTime, actor, classPath, "ouverture", 0, "ignorée : ouvreur inconnu"));
        }
        else if (broken && _hasOpening.Contains(actor) && _loggedDestroy.Add(actor))
        {
            _log.Add((CurrentTime, actor, classPath, "détruit", pawn ?? 0,
                      "ignoré : coffre déjà ouvert (pas de double comptage)"));
        }

    }

    /// <summary>
    /// Scénarios simulés (exécutés par les tests et la CI). Chaque scénario rejoue une suite de mises à
    /// jour répliquées d'un ou plusieurs coffres et vérifie : ouvertures du joueur, coffres uniques,
    /// coffres cassés. ME et ME2 sont deux personnages du même joueur (réapparition / relance).
    /// </summary>
    public static int SelfTest()
    {
        const uint ME = 100, ME2 = 101, OTHER = 200, OTHER2 = 201;
        var owner = new HashSet<uint> { ME, ME2 };
        var lines = new List<string>();
        var failures = 0;

        void Check(string name, (float t, uint chest, uint? pawn, uint anim, bool destroyed)[] updates,
                   int openings, int unique, int broken = 0)
        {
            var r = new ChestReplayReader();
            foreach (var u in updates)
            {
                r.CurrentTime = u.t;
                var c = new GenericChest { SearchingPawn = u.pawn, SearchAnimationCount = u.anim, bDestroyed = u.destroyed };
                r.RecordChestUpdate(u.chest, StandardChestPath, c);
            }
            var mine = r._opens.Where(o => owner.Contains(o.pawn)).ToList();
            var got = (mine.Count, mine.Select(o => o.chest).Distinct().Count(), mine.Count(o => o.broken));
            var ok = got == (openings, unique, broken);
            failures += ok ? 0 : 1;
            lines.Add($"{(ok ? "OK   " : "ÉCHEC")} {name} : attendu {openings} ouv./{unique} uniques/{broken} cassés, "
                      + $"obtenu {got.Item1}/{got.Item2}/{got.Item3}");
        }

        Check("coffre ouvert une fois", new[] { (10f, 1u, (uint?)ME, 1u, false) }, 1, 1);
        Check("plusieurs coffres ouverts", new[] { (10f, 1u, (uint?)ME, 1u, false), (20f, 2u, (uint?)ME, 1u, false),
                                                  (30f, 3u, (uint?)ME, 1u, false) }, 3, 3);
        Check("même mise à jour répétée (pas de double)", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                                 (11f, 1u, (uint?)null, 1u, false) }, 1, 1);
        Check("rouvert après remplissage (même joueur)", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                                (100f, 1u, (uint?)null, 2u, false) }, 2, 1);
        Check("rouvert 3 fois", new[] { (10f, 1u, (uint?)ME, 1u, false), (100f, 1u, (uint?)null, 2u, false),
                                        (200f, 1u, (uint?)null, 3u, false) }, 3, 1);
        Check("cassé directement", new[] { (10f, 1u, (uint?)ME, 1u, true) }, 1, 1, 1);
        Check("ouvert puis cassé (compté une fois, comme ouvert)", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                                          (50f, 1u, (uint?)ME, 1u, true) }, 1, 1, 0);
        Check("ouvert par moi puis cassé par un autre", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                               (50f, 1u, (uint?)OTHER, 1u, true) }, 1, 1, 0);
        Check("ouvert par un adversaire", new[] { (10f, 1u, (uint?)OTHER, 1u, false) }, 0, 0);
        Check("cassé par un adversaire", new[] { (10f, 1u, (uint?)OTHER, 1u, true) }, 0, 0);
        Check("rouvert par un autre après moi", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                       (100f, 1u, (uint?)OTHER, 2u, false) }, 1, 1);
        Check("ouvert par un autre puis rouvert par moi", new[] { (10f, 1u, (uint?)OTHER, 1u, false),
                                                                 (100f, 1u, (uint?)ME, 2u, false) }, 1, 1);
        Check("plusieurs joueurs, plusieurs coffres", new[] { (10f, 1u, (uint?)OTHER, 1u, false),
            (12f, 2u, (uint?)ME, 1u, false), (15f, 3u, (uint?)OTHER2, 1u, false), (20f, 4u, (uint?)ME, 1u, true),
            (30f, 5u, (uint?)OTHER, 1u, true) }, 2, 2, 1);
        Check("changement de personnage (réapparition)", new[] { (10f, 1u, (uint?)ME, 1u, false),
                                                                (400f, 2u, (uint?)ME2, 1u, false) }, 2, 2);
        Check("déjà ouvert avant d'être visible", new[] { (10f, 1u, (uint?)null, 1u, false) }, 0, 0);
        Check("ouvreur transmis juste après le compteur", new[] { (10f, 1u, (uint?)null, 1u, false),
                                                                 (10.5f, 1u, (uint?)ME, 0u, false) }, 1, 1);
        Check("ouvreur transmis bien plus tard (ignoré)", new[] { (10f, 1u, (uint?)null, 1u, false),
                                                                 (60f, 1u, (uint?)ME, 0u, false) }, 0, 0);

        // Classification des classes (noms)
        void Class(string path, string expected)
        {
            var target = AliasWithFields(path, Array.Empty<string>());
            var got = target == GenericChestPath ? "coffre" : target == PlayerPawnPath ? "personnage"
                    : target == GenericProbePath ? "inconnu (décidé sur les données)" : "ignoré";
            var ok = got == expected;
            failures += ok ? 0 : 1;
            lines.Add($"{(ok ? "OK   " : "ÉCHEC")} classe {path[(path.LastIndexOf('/') + 1)..]} : attendu {expected}, obtenu {got}");
        }
        Class("/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_New.Tiered_Chest_Athena_New_C", "coffre");
        Class("/TreasureHunters/Containers/B_TreasureHunt_Chest.B_TreasureHunt_Chest_C", "coffre");
        Class("/Game/Building/ActorBlueprints/Containers/Tiered_Ammo_Athena2.Tiered_Ammo_Athena2_C", "inconnu (décidé sur les données)");
        Class("/Game/Athena/BuildingActors/Props/Building/ActorBlueprints/Containers/Athena_Prop_Bedroom_HopeChest_03.Athena_Prop_Bedroom_HopeChest_03_C", "inconnu (décidé sur les données)");
        Class("/Game/Athena/PlayerPawn_Athena_Ch7.PlayerPawn_Athena_Ch7_C", "personnage");
        Class("FortGameStateComponent_Reboot_ClassNetCache", "ignoré");

        var cats = new (string kind, string cat, bool special)[]
        {
            ("Tiered_Chest_Athena", "standard", false), ("B_TreasureHunt_Chest", "trésor", false),
            ("Tiered_Chest_Rare_Athena", "rare", true), ("BuriedChest", "enterré", true),
            ("Tiered_Chest_Athena_FactionChest_NoLocks", "faction", true),
        };
        foreach (var (kind, cat, special) in cats)
        {
            var got = ChestCategory(kind);
            var ok = got == (cat, special);
            failures += ok ? 0 : 1;
            lines.Add($"{(ok ? "OK   " : "ÉCHEC")} catégorie {kind} : attendu {cat}/{(special ? "spécial" : "normal")}, "
                      + $"obtenu {got.category}/{(got.special ? "spécial" : "normal")}");
        }

        foreach (var l in lines)
        {
            Console.WriteLine(l);
        }
        Console.WriteLine(failures == 0 ? $"selftest OK ({lines.Count} vérifications)" : $"selftest : {failures} échec(s)");
        return failures == 0 ? 0 : 1;
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
                    Direct = o.direct,
                    Reopen = o.reopen,
                });
            }
        }

        result.TotalOpenings = result.Chests.Count;
        result.UniqueChests = result.Chests.Select(c => c.Id).Distinct().Count();
        result.InferredOpenings = result.Chests.Count(c => !c.Direct);
        result.OwnerPawnIds = ownerPawns.OrderBy(x => x).ToList();
        lock (AliasedPaths)
        {
            result.ClassDecisions = ClassEvidence.ToDictionary(kv => kv.Key[(kv.Key.LastIndexOf('/') + 1)..].Split('.')[0],
                                                               kv => $"{kv.Value.role} ({kv.Value.reason})");
        }
        var ownerChests = result.Chests.Select(c => c.Id).ToHashSet();
        foreach (var e in _log.Where(e => ownerPawns.Contains(e.pawn) || ownerChests.Contains(e.chest)).OrderBy(e => e.t).Take(400))
        {
            var who = e.pawn == 0 ? "inconnu" : ownerPawns.Contains(e.pawn) ? "moi" : $"autre joueur ({e.pawn})";
            var counted = ownerPawns.Contains(e.pawn) && !e.note.StartsWith("ignoré") ? "COMPTÉ" : "ignoré";
            result.Decisions.Add($"{(int)e.t / 60:00}:{(int)e.t % 60:00} coffre {e.chest} [{e.path[(e.path.LastIndexOf('/') + 1)..].Split('.')[0]}] "
                                 + $"{e.evt} par {who} → {counted} — {e.note}");
        }
        if (result.InferredOpenings > 0)
        {
            result.Warnings.Add($"{result.InferredOpenings} ouverture(s) attribuée(s) par déduction (dernier ouvreur connu du coffre).");
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
