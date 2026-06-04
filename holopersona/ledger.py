"""Replayable event ledger. The canonical truth is the event log:
    current_persona = replay(holo_events)
so personality is auditable, reversible, exportable and reproducible. No stable learning
happens anywhere else — only deterministic replay over recorded evidence.

Note: event_vec (HDC binding) and snapshots are reserved for F3/F4; F0 stores the
deterministic signals + (optional) holo_trace and replays them into a per-user genome."""
import hashlib
import json
import sqlite3
import time

from .signals import extract, EVIDENCE_WEIGHT
from .genome import StyleGenome

VERSION = "holopersona-v3-f0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS holo_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, guild_id TEXT, channel_id TEXT,
  user_id TEXT, input_hash TEXT, reply_hash TEXT, holo_trace TEXT,
  deterministic_signals TEXT, outcome TEXT, event_vec BLOB, version TEXT);
CREATE TABLE IF NOT EXISTS holo_snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, scope TEXT, state TEXT, stats TEXT, version TEXT);
"""


def _h(s):
    return hashlib.sha256((s or "").encode()).hexdigest()[:16]


def outcome_reward(outcome):
    return {"positive": 1.0, "negative": 0.2, "strong_negative": 0.0,
            "neutral": 0.6, "": 0.6}.get(outcome or "", 0.6)


class Ledger:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(holo_events)")]
        if "event_vec" not in cols:                       # migrate older ledgers
            self.db.execute("ALTER TABLE holo_events ADD COLUMN event_vec BLOB")
            self.db.commit()

    def append(self, *, user_id, text, reply, trace=None, guild_id="", channel_id="",
               outcome="neutral", now=None):
        now = time.time() if now is None else now
        sig = extract(text)
        from .holo_hdc import encode_event, pack
        ev = pack(encode_event(text, trace=trace, outcome=outcome,
                               guild_id=guild_id, channel_id=channel_id, ts=now))
        self.db.execute(
            "INSERT INTO holo_events(ts,guild_id,channel_id,user_id,input_hash,reply_hash,"
            "holo_trace,deterministic_signals,outcome,event_vec,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (now, str(guild_id), str(channel_id), str(user_id), _h(text), _h(reply),
             json.dumps(trace) if trace else None, json.dumps(sig), outcome, ev, VERSION))
        self.db.commit()
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def event_vectors(self, user_id):
        from .holo_hdc import unpack
        return [unpack(r[0]) for r in self.db.execute(
            "SELECT event_vec FROM holo_events WHERE user_id=? AND event_vec IS NOT NULL ORDER BY id",
            (str(user_id),)).fetchall()]

    def update_outcome(self, eid, outcome):
        self.db.execute("UPDATE holo_events SET outcome=? WHERE id=?", (outcome, eid))
        self.db.commit()

    def events(self, user_id=None, guild_id=None):
        q = ("SELECT user_id,guild_id,holo_trace,deterministic_signals,outcome,ts "
             "FROM holo_events")
        cond, args = [], []
        if user_id is not None:
            cond.append("user_id=?"); args.append(str(user_id))
        if guild_id is not None:
            cond.append("guild_id=?"); args.append(str(guild_id))
        if cond:
            q += " WHERE " + " AND ".join(cond)
        return self.db.execute(q + " ORDER BY id ASC", args).fetchall()

    def reset(self, user_id=None, guild_id=None):
        if user_id is not None:
            self.db.execute("DELETE FROM holo_events WHERE user_id=?", (str(user_id),))
        elif guild_id is not None:
            self.db.execute("DELETE FROM holo_events WHERE guild_id=?", (str(guild_id),))
        self.db.commit()

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM holo_events").fetchone()[0]

    def save_snapshot(self, scope, state, stats, now=None):
        self.db.execute(
            "INSERT INTO holo_snapshots(ts,scope,state,stats,version) VALUES(?,?,?,?,?)",
            (time.time() if now is None else now, str(scope), json.dumps(state),
             json.dumps(stats), VERSION))
        self.db.commit()

    def snapshot_count(self):
        return self.db.execute("SELECT COUNT(*) FROM holo_snapshots").fetchone()[0]

    def latest_snapshot(self, scope):
        row = self.db.execute(
            "SELECT state,stats,ts FROM holo_snapshots WHERE scope=? ORDER BY id DESC LIMIT 1",
            (str(scope),)).fetchone()
        return None if row is None else {"state": json.loads(row[0]), "stats": json.loads(row[1]), "ts": row[2]}

    def scopes(self):
        return [r[0] for r in self.db.execute(
            "SELECT DISTINCT user_id FROM holo_events ORDER BY user_id").fetchall()]

    def export_json(self):
        cols = ["ts", "guild_id", "channel_id", "user_id", "input_hash", "reply_hash",
                "holo_trace", "deterministic_signals", "outcome", "version"]
        rows = self.db.execute(f"SELECT {','.join(cols)} FROM holo_events ORDER BY id").fetchall()
        return [dict(zip(cols, r)) for r in rows]


def replay_user(ledger: Ledger, user_id, core=None) -> StyleGenome:
    """Deterministically rebuild a user's StyleGenome from their event log, starting from the
    core prior. Trusted text signals carry full confidence; the LLM trace is weak (0.25).
    Outcome scales reward, so corrected/negative replies reinforce less. Silence (neutral, no
    signal) changes nothing."""
    g = StyleGenome(core)
    for (_uid, _gid, trace_json, sig_json, outcome, ts) in ledger.events(user_id=user_id):
        reward = outcome_reward(outcome)
        for trait, nudge, weight in json.loads(sig_json or "[]"):
            g.apply(trait, nudge, confidence=1.0, reward_weight=weight * reward, now=ts)
        if trace_json:
            tr = json.loads(trace_json)
            conf = float(tr.get("confidence", 0.0))
            for trait, nudge in (tr.get("next_nudge") or {}).items():
                g.apply(trait, nudge, confidence=conf,
                        reward_weight=EVIDENCE_WEIGHT["trace"] * reward, now=ts)
    return g
