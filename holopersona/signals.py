"""Deterministic, LLM-free signals extracted straight from user text. These are the
*trusted* evidence (weight 0.70). The LLM's self-reported trace is weak (weight 0.25):
the model proposes, the deterministic engine decides how much to believe it."""

# substring -> (trait, direction in {-1,+1})   (Spanish + English)
TEXT_SIGNALS = {
    "sin emojis": ("emoji", -1.0), "no emojis": ("emoji", -1.0), "quita los emojis": ("emoji", -1.0),
    "no uses emojis": ("emoji", -1.0), "no emoji": ("emoji", -1.0),
    "más corto": ("brevity", +1.0), "mas corto": ("brevity", +1.0), "muy largo": ("brevity", +1.0),
    "sé breve": ("brevity", +1.0), "se breve": ("brevity", +1.0), "shorter": ("brevity", +1.0),
    "too long": ("brevity", +1.0), "be brief": ("brevity", +1.0),
    "más largo": ("brevity", -1.0), "mas largo": ("brevity", -1.0),
    "explica más": ("depth", +1.0), "explica mas": ("depth", +1.0), "piensa más": ("depth", +1.0),
    "más técnico": ("depth", +1.0), "mas tecnico": ("depth", +1.0), "explain more": ("depth", +1.0),
    "more detail": ("depth", +1.0), "go deeper": ("depth", +1.0),
    "más directo": ("directness", +1.0), "ve al grano": ("directness", +1.0), "be direct": ("directness", +1.0),
    "cringe": ("ornamentation", -1.0), "menos cringe": ("ornamentation", -1.0),
    "no seas cursi": ("ornamentation", -1.0), "less flowery": ("ornamentation", -1.0),
}

CORRECTION = ("eso no", "no es así", "no es asi", "incorrecto", "that's wrong", "thats wrong", "estás mal")
ALIGNMENT = ("gracias", "exacto", "perfecto", "me gusta así", "me gusta asi", "thanks", "exactly", "perfect")

# Evidence weights (how much each kind of signal is trusted).
EVIDENCE_WEIGHT = {
    "explicit": 1.00, "moderation": 1.00, "text": 0.70,
    "behavior": 0.30, "trace": 0.25, "silence": 0.00,
}


def extract(text: str):
    """Return a list of (trait, nudge in [-1,1], weight) from trusted text signals."""
    t = (text or "").lower()
    return [(trait, direction, EVIDENCE_WEIGHT["text"])
            for sub, (trait, direction) in TEXT_SIGNALS.items() if sub in t]


def outcome_of(text: str) -> str:
    """Infer the outcome of the *previous* reply from a follow-up message. Silence is not bad."""
    t = (text or "").lower()
    if any(c in t for c in CORRECTION):
        return "negative"
    if any(a in t for a in ALIGNMENT):
        return "positive"
    return "neutral"
