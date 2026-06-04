"""HoloPersona facade — bounded, replayable adaptive style. It never rewrites persona.md;
it only produces a *style card* to guide the LLM and records evidence to a replayable
ledger. Stable at the core, adaptive at the edges."""
import json
from pathlib import Path

from .bounds import DEFAULT_BOUNDS, NITO_CORE, TRAITS, project
from .ledger import Ledger, replay_user
from .mood import SessionMood
from .card import style_card
from .signals import extract


class HoloPersona:
    def __init__(self, db_path=":memory:", state_path=None, core=None, bounds=None):
        self.ledger = Ledger(db_path)
        self.core = dict(core or NITO_CORE)
        self.bounds = {**DEFAULT_BOUNDS, **(bounds or {})}
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
        if self.frozen:
            return {}
        return replay_user(self.ledger, user_id, self.core).evidenced_means()

    def style_for(self, user_id, guild_id="", channel_id="", context="", now=None):
        rel = self.relationship_means(user_id)
        mood = {} if self.frozen else self.moods.get(str(user_id), SessionMood(now=now)).current(now)
        return style_card(self.core, relationship=rel, mood=mood, bounds=self.bounds)

    def explain(self, user_id):
        return replay_user(self.ledger, user_id, self.core).explain()

    def drift(self, user_id, cap=0.35):
        """Report how far a user's learned style has moved from the core, flagging any trait
        beyond the daily-style cap. Final style is always projected into bounds."""
        means = replay_user(self.ledger, user_id, self.core).evidenced_means()
        rows = []
        for t in TRAITS:
            if t in means:
                d = means[t] - self.core[t]
                rows.append((t, round(d, 3), "OVER CAP" if abs(d) > cap else "ok"))
        return rows

    def reset(self, user_id=None, guild_id=None):
        self.ledger.reset(user_id=user_id, guild_id=guild_id)
        if user_id is not None:
            self.moods.pop(str(user_id), None)

    def export_json(self):
        return self.ledger.export_json()
