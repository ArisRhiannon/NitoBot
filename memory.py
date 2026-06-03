"""Holographic memory via Hyperdimensional Computing (HDC / VSA).

A *real* holographic associative memory, not a keyword index:

- Each text is encoded into one binary **hypervector** of `DIM` bits — information spread
  across all dimensions (holographic: robust, degrades gracefully).
- Encoding is byte-n-gram based → **language- and script-agnostic** (any UTF-8: Spanish,
  English, emoji) with no tokenizer, model, or training.
- All ops are bitwise — deterministic random symbol vectors (hashing), circular shift for
  position, XOR to bind, majority vote to bundle; recall is Hamming distance. No floats in
  the algorithm, no GPU, ~1 KB per memory. Cost is O(len(text) · DIM): ≈2.6 ms to encode a
  message and (vectorized) ≈55 ms to scan 10k memories in Python/numpy; a numpy-free,
  microcontroller-capable C reference (native/holo.c) reproduces identical vectors at a
  similar ≈2.3 ms. It is not sub-microsecond at DIM=8192 — the win of the native build is
  portability, not raw speed.
- The encoding is a fixed, documented spec (seed + DIM + n-gram + ops), so any
  implementation in any language produces **identical, interoperable** hypervectors
  (see HOLO_SPEC.md).

`MemoryStore` keeps the same remember/recall interface — a drop-in upgrade.
"""
import hashlib
import sqlite3
import time

import numpy as np

DIM = 8192            # hypervector size in bits (1 KB)
NGRAM = 3             # byte trigrams
SEED = "nito-hdc-v1"  # part of the cross-implementation spec
_BYTES = DIM // 8


def _expand_bytes(seed: bytes) -> bytes:
    blocks, ctr = b"", 0
    while len(blocks) < _BYTES:
        blocks += hashlib.sha256(seed + ctr.to_bytes(4, "big")).digest()
        ctr += 1
    return blocks[:_BYTES]


class _Codebook:
    """Deterministic hypervector (unpacked bits) per byte value; 256 of them, cached."""
    def __init__(self, seed: str = SEED):
        self._seed = seed.encode("utf-8")
        self._cache = {}

    def of(self, b: int) -> np.ndarray:
        v = self._cache.get(b)
        if v is None:
            v = np.unpackbits(np.frombuffer(_expand_bytes(self._seed + bytes([b])), dtype=np.uint8))
            self._cache[b] = v
        return v


_BOOK = _Codebook()


def encode_bits(text: str) -> np.ndarray:
    """Holographic bit-vector (uint8 0/1, length DIM) of `text`."""
    data = text.encode("utf-8") or b"\x00"
    grams = [data[i:i + NGRAM] for i in range(max(1, len(data) - NGRAM + 1))]
    acc = np.zeros(DIM, dtype=np.int32)
    for g in grams:
        gv = np.zeros(DIM, dtype=np.uint8)
        for pos, b in enumerate(g):
            gv ^= np.roll(_BOOK.of(b), pos)     # bind symbol with its position (circular shift)
        acc += gv                                # bundle (count set bits per dimension)
    return (2 * acc > len(grams)).astype(np.uint8)   # majority vote


def encode(text: str) -> int:
    return int.from_bytes(np.packbits(encode_bits(text)).tobytes(), "big")


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def similarity(a: int, b: int) -> float:
    return 1.0 - hamming(a, b) / DIM


_POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)  # byte popcount LUT


class MemoryStore:
    """Holographic associative memory. Drop-in: same remember/recall as before.

    Vectors are kept as a packed (N, DIM/8) uint8 matrix in memory; recall is a single
    vectorized Hamming over all rows (popcount LUT), so it scales to 10k+ memories."""
    def __init__(self, path: str = ":memory:", half_life_days: float = 14.0):
        self.db = sqlite3.connect(path)
        self.half_life = half_life_days * 86400
        self.db.execute("CREATE TABLE IF NOT EXISTS mem(scope TEXT, text TEXT, vec TEXT, ts REAL)")
        self.db.commit()
        self._cache = {}   # scope -> {"rows": [uint8(B)], "texts": [...], "ts": [...], "mat": ndarray|None}
        for scope, text, vec_hex, ts in self.db.execute("SELECT scope, text, vec, ts FROM mem"):
            self._cache_add(scope, text, np.frombuffer(bytes.fromhex(vec_hex), dtype=np.uint8), ts)

    def _cache_add(self, scope, text, packed, ts):
        c = self._cache.setdefault(str(scope), {"rows": [], "texts": [], "ts": [], "mat": None})
        c["rows"].append(packed); c["texts"].append(text); c["ts"].append(ts); c["mat"] = None

    def remember(self, scope, text: str, ts: float = None) -> None:
        ts = time.time() if ts is None else ts
        packed = np.packbits(encode_bits(text))
        self.db.execute("INSERT INTO mem(scope, text, vec, ts) VALUES(?,?,?,?)",
                        (str(scope), text, packed.tobytes().hex(), ts))
        self.db.commit()
        self._cache_add(scope, text, packed, ts)

    def recall(self, scope, query: str, k: int = 3, now: float = None):
        c = self._cache.get(str(scope))
        if not c or not c["texts"]:
            return []
        now = time.time() if now is None else now
        if c["mat"] is None:
            c["mat"] = np.vstack(c["rows"])
        q = np.packbits(encode_bits(query))
        dist = _POP[np.bitwise_xor(c["mat"], q)].sum(axis=1)          # Hamming to every memory at once
        recency = 0.5 ** ((now - np.asarray(c["ts"])) / self.half_life)
        score = (1.0 - dist / DIM) + 0.05 * recency                  # similarity leads; recency breaks ties
        idx = np.argsort(-score, kind="stable")[:k]
        return [c["texts"][i] for i in idx]
