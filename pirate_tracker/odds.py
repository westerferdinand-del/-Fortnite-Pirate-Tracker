"""Chances d'obtenir le jeton pirate (accès à la Boutique Pirate).

Taux publié par Epic (Fortnite Status, 7 nov. 2026) : 1 chance sur 137 500 par coffre en partie
normale ; il est augmenté pendant les « Treasure Hours ». Chaque ouverture est un tirage
indépendant : avoir déjà ouvert beaucoup de coffres ne rend pas le suivant plus chanceux. La
probabilité cumulée dit seulement à quel point il était probable d'en avoir eu au moins un.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_ONE_IN = 137_500


@dataclass(frozen=True)
class TokenOdds:
    one_in: int
    openings: int
    probability_any: float  # probabilité d'avoir obtenu au moins un jeton en `openings` ouvertures
    expected_tokens: float  # nombre moyen de jetons attendu
    openings_for_half: int  # ouvertures pour avoir 1 chance sur 2 au total

    @property
    def percent(self) -> float:
        return 100.0 * self.probability_any


def token_odds(openings: int, one_in: int = DEFAULT_ONE_IN) -> TokenOdds:
    one_in = max(1, int(one_in))
    n = max(0, int(openings))
    p = 1.0 / one_in
    prob = -math.expm1(n * math.log1p(-p)) if p < 1 else (1.0 if n else 0.0)  # 1 - (1-p)^n, précis
    half = math.ceil(math.log(0.5) / math.log1p(-p)) if p < 1 else 1
    return TokenOdds(one_in, n, prob, n * p, half)


def format_percent(x: float) -> str:
    """1,93 → « 1,9 % » ; 0,0145 → « 0,015 % » : assez de chiffres pour rester parlant."""
    if x == 0:
        return "0 %"
    if x < 1:
        s = f"{x:.2g}"  # deux chiffres significatifs : 0,015 % ; 0,00073 %
        if "e" in s:
            s = f"{x:.8f}".rstrip("0")
    else:
        s = f"{x:.1f}"
    return s.replace(".", ",") + " %"
