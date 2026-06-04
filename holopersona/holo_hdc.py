"""HDC / VSA event layer (F4). Each interaction becomes one holographic hypervector built by
*role-filler binding*: each role (user_text, bot_tone, intent, outcome, context, time) is XOR-bound
to its filler and the parts are bundled (majority vote) into one event vector. Reuses the same
DIM/codebook/encode_bits as the holographic memory (HOLO_SPEC), so vectors are deterministic and
cross-implementation reproducible. The encoding is non-reversible — the raw text can't be recovered.
"""
import numpy as np

from memory import DIM, encode_bits   # shared HDC substrate (8192-bit, byte-trigram, fixed seed)

ROLES = ("user_text", "bot_tone", "intent", "outcome", "context", "time")


def symbol(name: str) -> np.ndarray:
    """Deterministic hypervector for a role/label string."""
    return encode_bits("holo:" + name)


def bind(a, b):
    return np.bitwise_xor(a, b)


def bundle(vectors):
    """Majority vote across a list of bit vectors (ties -> 0)."""
    acc = np.zeros(DIM, dtype=np.int32)
    for v in vectors:
        acc += v
    return (2 * acc > len(vectors)).astype(np.uint8)


def similarity(a, b) -> float:
    return 1.0 - float(np.bitwise_xor(a, b).mean())


def _dominant(d, default="na"):
    return max(d, key=d.get) if isinstance(d, dict) and d else default


def encode_event(text, trace=None, outcome="neutral", guild_id="", channel_id="", ts=0.0):
    """Build the holographic event vector from the plan's role structure."""
    trace = trace or {}
    tone = _dominant(trace.get("tone_used"))
    intent = _dominant(trace.get("intent"))
    bucket = str(int(ts // 3600))                       # coarse hour bucket
    parts = [
        bind(symbol("user_text"), encode_bits(text or "")),
        bind(symbol("bot_tone"), symbol("tone:" + tone)),
        bind(symbol("intent"), symbol("intent:" + intent)),
        bind(symbol("outcome"), symbol("outcome:" + str(outcome))),
        bind(symbol("context"), symbol(f"ctx:{guild_id}:{channel_id}")),
        bind(symbol("time"), symbol("t:" + bucket)),
    ]
    return bundle(parts)


def pack(v) -> bytes:
    return np.packbits(v).tobytes()


def unpack(b) -> np.ndarray:
    return np.unpackbits(np.frombuffer(b, dtype=np.uint8))[:DIM]


def consistency(vectors) -> float:
    """How clustered a set of event vectors is (mean pairwise similarity). High = the user's
    interactions keep landing in the same region -> a recurring, stable pattern. ~0.5 = noise."""
    n = len(vectors)
    if n < 2:
        return 1.0 if n == 1 else 0.0
    sims = [similarity(vectors[i], vectors[j]) for i in range(n) for j in range(i + 1, n)]
    return sum(sims) / len(sims)
