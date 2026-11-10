"""Noms lisibles, rareté et catégorie des objets Fortnite à partir de leur nom interne.

Les replays donnent le nom technique de l'objet (ex. ``WID_Assault_CoreAR_Athena_UC``).
On en déduit un libellé français et la rareté (suffixe ``_C``, ``_UC``, ``_R``…).
Les noms inconnus restent affichés tels quels, nettoyés.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RARITIES = {
    "C": ("Commun", "#9ca3af"),
    "UC": ("Peu commun", "#22c55e"),
    "R": ("Rare", "#3b82f6"),
    "VR": ("Épique", "#a855f7"),
    "SR": ("Légendaire", "#f59e0b"),
    "UR": ("Mythique", "#fbbf24"),
    "Ore": ("Épique", "#a855f7"),
}

AMMO = {
    "AthenaAmmoDataShells": "Munitions : cartouches",
    "AthenaAmmoDataBulletsLight": "Munitions légères",
    "AthenaAmmoDataBulletsMedium": "Munitions moyennes",
    "AthenaAmmoDataBulletsHeavy": "Munitions lourdes",
    "AthenaAmmoDataRockets": "Roquettes",
    "AthenaAmmoDataEnergyCell": "Cellules d'énergie",
    "AmmoDataArrows": "Flèches",
}

MATERIALS = {
    "WoodItemData": "Bois",
    "StoneItemData": "Pierre",
    "MetalItemData": "Métal",
    "Athena_WadsItemData": "Lingots d'or",
}

KNOWN = {
    "WID_Paprika_ShieldSmall": "Petite potion de bouclier",
    "Athena_ShockGrenade": "Grenade à impulsion",
    "Athena_Shields": "Potion de bouclier",
    "Athena_ShieldSmall": "Petite potion de bouclier",
    "Athena_Medkit": "Trousse de soins",
    "Athena_Bandage": "Bandages",
    "Athena_ChillBronco": "Chug Splash",
    "Athena_Flopper": "Poisson",
    "Athena_GrenadeFrag": "Grenade",
}

WEAPON_TYPES = [
    ("Assault", "Fusil d'assaut"), ("Shotgun", "Fusil à pompe"), ("SMG", "Mitraillette"),
    ("Pistol", "Pistolet"), ("Sniper", "Fusil de précision"), ("DMR", "Fusil de précision (DMR)"),
    ("Hook_Gun", "Grappin"), ("Launcher", "Lanceur"), ("RocketLauncher", "Lance-roquettes"),
    ("Minigun", "Minigun"), ("LMG", "Mitrailleuse légère"), ("Bow", "Arc"), ("Crossbow", "Arbalète"),
    ("Melee", "Arme de mêlée"), ("Harvest", "Pioche"), ("Grenade", "Grenade"),
]

# Motifs par défaut du jeton pirate (nom interne inconnu à l'avance : l'utilisateur peut
# aussi désigner l'objet exact dans la page « Récompenses »).
DEFAULT_TOKEN_PATTERNS = [
    r"pirate.*(token|coin|doubloon|medal|jeton)", r"(token|coin|doubloon|medal|jeton).*pirate",
    # Saison Treasure Hunters (nov. 2026) : accès à la Boutique Pirate, 1 chance sur 137 500 par coffre
    r"pirate.?shop", r"shop.?access", r"piratestore",
]

# Catégories de coffres d'après le nom de leur classe (même règle que le lecteur C#)
CHEST_CATEGORIES = {
    "standard": "Coffre", "trésor": "Coffre de chasse au trésor", "rare": "Coffre rare",
    "enterré": "Coffre enterré", "faction": "Coffre de faction", "spécial": "Coffre spécial",
}


def chest_category(kind: str) -> tuple[str, bool]:
    """Catégorie d'un coffre et s'il est « spécial » (rare, enterré…), d'après sa classe.

    Les coffres normaux de la saison (y compris ceux de chasse au trésor) ne sont pas spéciaux.
    """
    n = (kind or "").lower()
    if "rare" in n:
        return "rare", True
    if "buried" in n:
        return "enterré", True
    if any(w in n for w in ("faction", "society", "oath")):
        return "faction", True
    if any(w in n for w in ("vault", "bunker", "mythic", "boss")):
        return "spécial", True
    if "treasure" in n:
        return "trésor", False
    return "standard", False


@dataclass(frozen=True)
class ItemInfo:
    raw: str
    name: str
    category: str  # arme / soin / munitions / matériaux / objet
    rarity: str
    color: str


def _clean(raw: str) -> str:
    s = re.sub(r"^(WID_|Athena_|AGID_|TID_)", "", raw)
    s = re.sub(r"_(Athena)", "", s)
    s = re.sub(r"_(C|UC|R|VR|SR|UR)$", "", s)
    s = s.replace("_", " ").strip()
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return s or raw


def describe(raw: str) -> ItemInfo:
    if raw in AMMO:
        return ItemInfo(raw, AMMO[raw], "munitions", "", "#9ca3af")
    if raw in MATERIALS:
        color = "#fbbf24" if raw == "Athena_WadsItemData" else "#9ca3af"
        return ItemInfo(raw, MATERIALS[raw], "matériaux", "", color)
    m = re.search(r"_(C|UC|R|VR|SR|UR)(?:_Ore_T\d+)?$", raw) or re.search(r"_(VR|SR|UR|UC|R|C)_Ore_T\d+$", raw)
    rarity_key = m.group(1) if m else ""
    rarity, color = RARITIES.get(rarity_key, ("", "#cbd5e1"))
    if raw in KNOWN:
        cat = "soin" if any(k in raw for k in ("Shield", "Medkit", "Bandage", "Chill", "Flopper")) else "objet"
        return ItemInfo(raw, KNOWN[raw], cat, rarity, color)
    if raw.startswith("WID_"):
        label = next((fr for key, fr in WEAPON_TYPES if key.lower() in raw.lower()), None)
        if label:
            name = f"{label} {rarity.lower()}".strip() if rarity else label
            return ItemInfo(raw, name, "arme", rarity, color)
        return ItemInfo(raw, _clean(raw), "arme", rarity, color)
    cat = "soin" if re.search(r"shield|medkit|bandage|heal|chug|slurp", raw, re.I) else "objet"
    return ItemInfo(raw, _clean(raw), cat, rarity, color)


def is_token(raw: str, patterns: list[str], exact: list[str]) -> bool:
    if raw in exact:
        return True
    return any(re.search(p, raw, re.I) for p in patterns)
