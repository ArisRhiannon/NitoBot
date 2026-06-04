"""HoloTrace: parse and harden the LLM's structured output. The user only ever sees
`reply`; the `holo_trace` is weak evidence that is clamped, validated and immunity-scrubbed.
If the model didn't emit valid JSON, we still surface a reply and simply drop the trace."""
import json

from .bounds import TRAITS
from . import immunity

INTENTS = ("info", "support", "decision", "play")


def _num(x, lo, hi, default=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return lo if v < lo else hi if v > hi else v


def _clamp_map(d, lo, hi, allowed=None):
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if allowed is not None and k not in allowed:
            continue
        n = _num(v, lo, hi)
        if n is not None:
            out[str(k)] = n
    return out


def parse_response(raw: str):
    """Return (reply, trace_or_None). Never block the visible answer on a bad trace."""
    raw = raw or ""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return raw.strip(), None
    if not isinstance(obj, dict) or "reply" not in obj:
        return raw.strip(), None
    return str(obj.get("reply", "")).strip(), validate_trace(obj.get("holo_trace"))


def validate_trace(trace):
    """Clamp every field to its legal range, drop unknown traits, and remove any memory
    candidate that is unsafe to learn (secrets, prompt injection). Returns None if unusable."""
    if not isinstance(trace, dict):
        return None
    cands_in = trace.get("memory_candidates") or []
    kept, blocked = immunity.scrub_candidates(cands_in if isinstance(cands_in, list) else [])
    cleaned = []
    for c in kept:
        if not isinstance(c, dict):
            continue
        cleaned.append({
            "text": str(c.get("text", ""))[:500],
            "kind": str(c.get("kind", "note"))[:40],
            "confidence": _num(c.get("confidence"), 0.0, 1.0, 0.0),
            "importance": _num(c.get("importance"), 0.0, 1.0, 0.0),
        })
    return {
        "v": 3,
        "confidence": _num(trace.get("confidence"), 0.0, 1.0, 0.0),
        "intent": _clamp_map(trace.get("intent"), 0.0, 1.0, INTENTS),
        "tone_used": _clamp_map(trace.get("tone_used"), 0.0, 1.0, TRAITS),
        "next_nudge": _clamp_map(trace.get("next_nudge"), -1.0, 1.0, TRAITS),
        "prediction": _clamp_map(trace.get("prediction"), 0.0, 1.0, ("satisfaction", "mismatch")),
        "memory_candidates": cleaned,
        "blocked_candidates": len(blocked),
    }
