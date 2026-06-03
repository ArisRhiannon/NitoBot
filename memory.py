"""Associative ("holographic") memory — recall by keyword overlap + recency decay.

Deliberately lightweight: pure Python + SQLite, no embedding model or vector DB, so it
runs anywhere at near-zero cost. The interface (remember/recall) is the drop-in point —
swap in a vector backend later without touching the LLM cog. We don't call this semantic
search; it's honest associative recall.
"""
import re
import sqlite3
import time

_TOK = re.compile(r"[a-z0-9]+")


def _toks(s: str):
    return set(_TOK.findall(s.lower()))


class MemoryStore:
    def __init__(self, path: str = ":memory:", half_life_days: float = 7.0):
        self.db = sqlite3.connect(path)
        self.half_life = half_life_days * 86400
        self.db.execute("CREATE TABLE IF NOT EXISTS mem(scope TEXT, text TEXT, ts REAL)")
        self.db.commit()

    def remember(self, scope, text: str, ts: float = None) -> None:
        self.db.execute("INSERT INTO mem(scope, text, ts) VALUES(?,?,?)",
                        (str(scope), text, time.time() if ts is None else ts))
        self.db.commit()

    def recall(self, scope, query: str, k: int = 3, now: float = None):
        now = time.time() if now is None else now
        q = _toks(query)
        scored = []
        for text, ts in self.db.execute("SELECT text, ts FROM mem WHERE scope=?", (str(scope),)):
            overlap = len(q & _toks(text))
            recency = 0.5 ** ((now - ts) / self.half_life)   # 1.0 now -> 0.5 after one half-life
            if overlap > 0 or recency > 0.25:
                scored.append((overlap + recency, ts, text))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [t for _, _, t in scored[:k]]
