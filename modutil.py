"""Discord-free moderation helpers (unit-testable): anti-saturation rate limiting and
the permission/role-hierarchy guard that every admin action must pass."""
import time


class RateLimiter:
    """Token bucket per key. Keeps a flood of mod actions from saturating the API
    (and from a compromised/over-eager moderator nuking a server)."""
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.rate = refill_per_sec
        self._buckets = {}

    def allow(self, key, now: float = None) -> bool:
        now = time.time() if now is None else now
        tokens, last = self._buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1, now)
        return True


def can_moderate(actor_top: int, target_top: int, bot_top: int, *,
                 actor_has_perm: bool, target_is_self: bool, target_is_owner: bool):
    """Returns (ok, reason). Enforces: permission, no self-action, never the owner,
    and strict role hierarchy for both the actor and the bot."""
    if not actor_has_perm:
        return False, "you don't have permission for that."
    if target_is_self:
        return False, "you can't moderate yourself."
    if target_is_owner:
        return False, "i won't act on the server owner."
    if actor_top <= target_top:
        return False, "that member is at or above your role."
    if bot_top <= target_top:
        return False, "that member is at or above my role — i can't act."
    return True, ""
