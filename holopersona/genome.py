"""StyleGenome — per-scope learned style as evidence-weighted beliefs. Learning rate
decays as evidence accumulates, so a single signal can't overwrite a stable personality,
but consistent, repeated preferences do consolidate."""
import math
import time
from dataclasses import dataclass, asdict

from .bounds import TRAITS, clamp

BASE_LR = 0.20


@dataclass
class TraitBelief:
    mean: float = 0.5
    evidence: float = 0.0
    volatility: float = 0.0
    last_updated: float = 0.0


def update_trait(b: TraitBelief, nudge: float, confidence: float, reward_weight: float,
                 base_lr: float = BASE_LR, now=None) -> TraitBelief:
    """One robust update. Effective step shrinks with accumulated evidence (1/sqrt)."""
    now = time.time() if now is None else now
    lr = base_lr * confidence * reward_weight / math.sqrt(1.0 + b.evidence)
    new_mean = clamp(b.mean + lr * nudge)
    b.volatility = 0.85 * b.volatility + 0.15 * abs(new_mean - b.mean)
    b.mean = new_mean
    b.evidence += confidence * reward_weight
    b.last_updated = now
    return b


class StyleGenome:
    def __init__(self, core=None):
        # Seed each belief at the core value, so "no evidence" == core and learning moves
        # the trait away from the core (not toward a neutral 0.5 prior).
        core = core or {}
        self.traits = {t: TraitBelief(mean=core.get(t, 0.5)) for t in TRAITS}

    def apply(self, trait, nudge, confidence, reward_weight, now=None):
        if trait in self.traits:
            update_trait(self.traits[trait], nudge, confidence, reward_weight, now=now)

    def means(self):
        return {t: b.mean for t, b in self.traits.items()}

    def evidenced_means(self, min_evidence: float = 0.5):
        """Only traits with real accumulated evidence — used so untrained traits fall back
        to the core instead of dragging everything toward the 0.5 prior."""
        return {t: b.mean for t, b in self.traits.items() if b.evidence >= min_evidence}

    def explain(self):
        def lvl(e):
            return "high" if e >= 2.0 else "medium" if e >= 0.7 else "low"
        return {t: (round(b.mean, 2), lvl(b.evidence)) for t, b in self.traits.items()}

    def to_dict(self):
        return {t: asdict(b) for t, b in self.traits.items()}

    @classmethod
    def from_dict(cls, d):
        g = cls()
        for t, v in (d or {}).items():
            if t in g.traits:
                g.traits[t] = TraitBelief(**v)
        return g
