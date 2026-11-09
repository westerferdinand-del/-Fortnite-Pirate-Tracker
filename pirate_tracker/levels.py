"""Système d'étoiles et de niveaux.

Chaque niveau contient 5 étoiles. ``star_thresholds`` donne le nombre de coffres
(comptés depuis le début du niveau) requis pour chaque étoile ; la 5e étoile
fait passer au niveau suivant.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LevelState:
    level: int
    stars: int  # 0..4 (5 = passage au niveau suivant)
    chests_in_level: int
    level_span: int
    next_star_at: int  # coffres (dans le niveau) pour la prochaine étoile
    prev_star_at: int

    @property
    def star_progress(self) -> float:
        """Progression vers la prochaine étoile, 0..1."""
        span = self.next_star_at - self.prev_star_at
        return 0.0 if span <= 0 else min(1.0, (self.chests_in_level - self.prev_star_at) / span)

    @property
    def level_progress(self) -> float:
        return min(1.0, self.chests_in_level / self.level_span) if self.level_span else 0.0


def validate_thresholds(thresholds: list[int]) -> list[int]:
    t = [int(x) for x in thresholds][:5]
    if len(t) != 5 or any(x <= 0 for x in t) or any(b <= a for a, b in zip(t, t[1:])):
        raise ValueError("Il faut 5 paliers strictement croissants et positifs.")
    return t


def compute_level(total_chests: int, thresholds: list[int]) -> LevelState:
    t = validate_thresholds(thresholds)
    span = t[-1]
    total = max(0, int(total_chests))
    level = total // span + 1
    in_level = total % span
    stars = sum(1 for x in t if in_level >= x)
    prev_at = t[stars - 1] if stars > 0 else 0
    next_at = t[stars] if stars < 5 else span
    return LevelState(level, stars, in_level, span, next_at, prev_at)


def transitions(before: int, after: int, thresholds: list[int]) -> list[tuple[str, LevelState]]:
    """Évènements (\"star\" / \"level\") franchis en passant de ``before`` à ``after`` coffres."""
    events: list[tuple[str, LevelState]] = []
    prev = compute_level(before, thresholds)
    for n in range(before + 1, after + 1):
        cur = compute_level(n, thresholds)
        if cur.level > prev.level:
            events.append(("level", cur))
        elif cur.stars > prev.stars:
            events.append(("star", cur))
        prev = cur
    return events
