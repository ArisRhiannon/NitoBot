"""SessionMood — the fast layer. A per-conversation tilt that changes in real time and
decays hard (~0.85 every 10 minutes). It lives in memory and is never persisted as stable
personality, so a heated thread can't permanently change who Nito is."""
import time

from .bounds import TRAITS, clamp

DECAY_PER = 0.85
DECAY_WINDOW = 600.0  # seconds (10 minutes)


class SessionMood:
    def __init__(self, now=None):
        self.vals = {t: 0.0 for t in TRAITS}
        self.ts = time.time() if now is None else now

    def decay(self, now=None):
        now = time.time() if now is None else now
        dt = max(0.0, now - self.ts)
        factor = DECAY_PER ** (dt / DECAY_WINDOW)
        self.vals = {t: v * factor for t, v in self.vals.items()}
        self.ts = now
        return self

    def nudge(self, trait, amount, now=None):
        self.decay(now)
        if trait in self.vals:
            self.vals[trait] = clamp(self.vals[trait] + amount, -1.0, 1.0)

    def current(self, now=None):
        self.decay(now)
        return dict(self.vals)
