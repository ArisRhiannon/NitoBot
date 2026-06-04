"""HoloPersona facade — bounded, replayable adaptive style. It never rewrites persona.md;
it only produces a *style card* to guide the LLM and records evidence to a replayable
ledger. Stable at the core, adaptive at the edges."""
import json
from pathlib import Path

from .bounds import DEFAULT_BOUNDS, NITO_CORE, TRAITS, clamp, project
from .ledger import Ledger, replay_user
from .mood import SessionMood
from .card import style_card
from .signals import extract

DRIFT_CAP = 0.35          # max any trait may move from the core (per the plan's daily cap)


class HoloPersona:
    def __init__(self, db_path=":memory:", state_path=None, core=None, bounds=None, cap=DRIFT_CAP):
        self.ledger = Ledger(db_path)
        self.core = dict(core or NITO_CORE)
        self.bounds = {**DEFAULT_BOUNDS, **(bounds or {})}
        self.cap = cap
        self.state_path = Path(state_path) if state_path else None
        self.moods = {}                          # scope -> SessionMood (RAM only)
        self.frozen = False
        if self.state_path and self.state_path.exists():
            try:
                self.frozen = bool(json.loads(self.state_path.read_text()).get("frozen", False))
            except (ValueError, OSError):
                self.frozen = False

    # --- state ---
    def freeze(self, on=True):
        self.frozen = on
        if self.state_path:
            self.state_path.write_text(json.dumps({"frozen": on}))

    def _cap(self, trait, value):
        """Clamp a learned value to within ±cap of the core — enforced, not just reported."""
        c = self.core[trait]
        return clamp(value, c - self.cap, c + self.cap)

    # --- write path (shadow-safe: persona.md is never touched) ---
    def record(self, *, user_id, text, reply, trace=None, guild_id="", channel_id="", now=None):
        eid = self.ledger.append(user_id=user_id, text=text, reply=reply, trace=trace,
                                 guild_id=guild_id, channel_id=channel_id, now=now)
        mood = self.moods.setdefault(str(user_id), SessionMood(now=now))
        for trait, nudge, _w in extract(text):
            mood.nudge(trait, 0.30 * nudge, now=now)
        return eid

    # --- read path ---
    def relationship_means(self, user_id):
        """Evidenced learned style that actually influences replies — drift-capped to ±cap
        from the core, so no trait can run away from who Nito is."""
        if self.frozen:
            return {}
        raw = replay_user(self.ledger, user_id, self.core).evidenced_means()
        return {t: self._cap(t, m) for t, m in raw.items()}

    def style_for(self, user_id, guild_id="", channel_id="", context="", now=None):
        rel = self.relationship_means(user_id)
        mood = {} if self.frozen else self.moods.get(str(user_id), SessionMood(now=now)).current(now)
        return style_card(self.core, relationship=rel, mood=mood, bounds=self.bounds)

    def explain(self, user_id):
        return replay_user(self.ledger, user_id, self.core).explain()

    def drift(self, user_id, cap=None):
        """Report how far a user's *raw* belief has moved from the core. Influence is capped
        separately at ±cap, so 'OVER CAP' means "the raw belief exceeds what we'll actually use"."""
        cap = self.cap if cap is None else cap
        means = replay_user(self.ledger, user_id, self.core).evidenced_means()
        return [(t, round(means[t] - self.core[t], 3),
                 "OVER CAP" if abs(means[t] - self.core[t]) > cap else "ok")
                for t in TRAITS if t in means]

    def consolidate(self, min_evidence=1.0, promote_delta=0.04, now=None):
        """Periodic pass: promote stable, well-evidenced (capped) shifts to a snapshot and
        return an auditable report {user_id: [(trait, capped_delta), ...]}."""
        report = {}
        for uid in self.ledger.scopes():
            g = replay_user(self.ledger, uid, self.core)
            promoted = []
            for t, b in g.traits.items():
                if b.evidence >= min_evidence:
                    d = round(self._cap(t, b.mean) - self.core[t], 3)
                    if abs(d) >= promote_delta:
                        promoted.append((t, d))
            if promoted:
                self.ledger.save_snapshot(uid, g.to_dict(), {"promoted": promoted}, now=now)
                report[uid] = promoted
        return report

    def reset(self, user_id=None, guild_id=None):
        self.ledger.reset(user_id=user_id, guild_id=guild_id)
        if user_id is not None:
            self.moods.pop(str(user_id), None)

    def export_json(self):
        return self.ledger.export_json()
