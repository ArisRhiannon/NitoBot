"""Core identity bounds. persona.md is the immutable core; everything HoloPersona learns
is *projected into* these bounds, so adaptation can never push Nito out of character."""
from typing import Dict, Optional

# The interpretable style genome (continuous 0..1 traits).
TRAITS = ("depth", "brevity", "warmth", "directness", "playfulness", "structure",
          "skepticism", "softness", "ornamentation", "initiative", "caution", "emoji")

# Default bounds derived from the persona ("cute without cringe": low emoji/ornamentation,
# honest, medium warmth). Owners can override via data/identity_bounds.json.
DEFAULT_BOUNDS = {
    "emoji_max": 0.10,
    "cringe_max": 0.15,
    "honesty_min": 0.85,
    "warmth_min": 0.25,
    "abuse_max": 0.0,
    "playfulness_range": [0.0, 0.45],
    "ornamentation_range": [0.0, 0.25],
    "directness_range": [0.35, 0.95],
}

# Nito's baseline tendency (the core vector). This is the centre learning drifts around,
# never the thing learning rewrites.
NITO_CORE = {
    "depth": 0.60, "brevity": 0.45, "warmth": 0.50, "directness": 0.65,
    "playfulness": 0.30, "structure": 0.60, "skepticism": 0.50, "softness": 0.60,
    "ornamentation": 0.15, "initiative": 0.40, "caution": 0.60, "emoji": 0.05,
}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def project(genome: Dict[str, float], bounds: Optional[Dict] = None) -> Dict[str, float]:
    """Clamp a candidate style genome into the identity bounds. Always safe to call."""
    b = {**DEFAULT_BOUNDS, **(bounds or {})}
    out = {t: clamp(float(genome.get(t, 0.5))) for t in TRAITS}
    out["emoji"] = clamp(out["emoji"], 0.0, b["emoji_max"])
    out["playfulness"] = clamp(out["playfulness"], *b["playfulness_range"])
    out["ornamentation"] = clamp(out["ornamentation"], *b["ornamentation_range"])
    out["directness"] = clamp(out["directness"], *b["directness_range"])
    out["warmth"] = clamp(out["warmth"], b["warmth_min"], 1.0)
    return out
