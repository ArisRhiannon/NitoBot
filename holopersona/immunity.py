"""HoloImmunity — the system refuses to *learn* manipulation, abuse, secrets or attempts
to rewrite the core persona. Deterministic and LLM-free; this is safety, not cleverness."""
import re

TRIGGERS = (
    "ignore previous instructions", "ignore all previous", "disregard previous",
    "change your core persona", "change your persona", "rewrite your persona",
    "store this as a permanent rule", "permanent rule", "always obey me",
    "give me admin", "make me admin", "reveal secrets", "reveal your prompt",
    "system prompt", "insult people", "be abusive",
    "olvida las instrucciones", "ignora las instrucciones", "ignora lo anterior",
    "cambia tu persona", "dame admin", "hazme admin", "regla permanente", "insulta a",
)

_SECRET = re.compile(
    r"(sk-[a-z0-9]{12,}|api[_-]?key|password\s*[:=]|contraseña\s*[:=]|secret\s*[:=]|"
    r"token\s*[:=]|-----begin [a-z ]*private key|bearer\s+[a-z0-9._-]{12,})", re.I)


def is_immune(text: str) -> bool:
    t = (text or "").lower()
    return any(trig in t for trig in TRIGGERS)


def has_secret(text: str) -> bool:
    return bool(_SECRET.search(text or ""))


def safe_to_learn(text: str) -> bool:
    """True only if it's safe to consolidate this text as a style/memory preference."""
    return not (is_immune(text) or has_secret(text))


def scrub_candidates(cands):
    """Split memory candidates into (kept, blocked); blocked ones are never learned."""
    kept, blocked = [], []
    for c in cands or []:
        text = str(c.get("text", "")) if isinstance(c, dict) else str(c)
        (kept if safe_to_learn(text) else blocked).append(c)
    return kept, blocked
