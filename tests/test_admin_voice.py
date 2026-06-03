"""Admin + voice core tests (offline)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modutil import RateLimiter, can_moderate
from voice_core import parse_voice_command


def test_rate_limiter_bursts_then_blocks_then_refills():
    rl = RateLimiter(capacity=3, refill_per_sec=1.0)
    t = 1000.0
    assert all(rl.allow("mod", now=t) for _ in range(3))   # burst of 3
    assert rl.allow("mod", now=t) is False                  # 4th blocked
    assert rl.allow("mod", now=t + 1.0) is True             # 1 token refilled after 1s
    assert rl.allow("other", now=t) is True                 # separate key, own bucket
    print("ok M1 rate limiter: burst, block, refill, per-key")


def test_can_moderate_guard():
    assert can_moderate(5, 3, 9, actor_has_perm=True, target_is_self=False, target_is_owner=False)[0] is True
    assert can_moderate(5, 3, 9, actor_has_perm=False, target_is_self=False, target_is_owner=False)[0] is False  # no perm
    assert can_moderate(5, 3, 9, actor_has_perm=True, target_is_self=True, target_is_owner=False)[0] is False    # self
    assert can_moderate(5, 3, 9, actor_has_perm=True, target_is_self=False, target_is_owner=True)[0] is False    # owner
    assert can_moderate(3, 3, 9, actor_has_perm=True, target_is_self=False, target_is_owner=False)[0] is False   # not above
    assert can_moderate(5, 3, 2, actor_has_perm=True, target_is_self=False, target_is_owner=False)[0] is False   # bot too low
    print("ok M2 moderation guard: perm, self, owner, actor & bot hierarchy")


def test_voice_command_parsing():
    assert parse_voice_command("nito ping") == ("ping", "")
    assert parse_voice_command("nito say hello there") == ("say", "hello there")
    assert parse_voice_command("hello there") is None      # no wake word
    assert parse_voice_command("nito") is None             # wake word only
    print("ok M3 voice parser: wake-word gated, command + args")


def run():
    test_rate_limiter_bursts_then_blocks_then_refills()
    test_can_moderate_guard()
    test_voice_command_parsing()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot admin/voice tests passed.")
