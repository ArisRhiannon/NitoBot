"""SocialStore tests (offline)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from social_store import SocialStore


def test_pair_counts_increment():
    s = SocialStore()
    assert s.record("hug", "alice", "bob") == 1
    assert s.record("hug", "alice", "bob") == 2
    assert s.record("hug", "alice", "carol") == 1   # different target, separate count
    assert s.pair_count("hug", "alice", "bob") == 2
    print("ok S1 per-pair counts increment independently")


def test_given_and_received_totals():
    s = SocialStore()
    s.record("hug", "alice", "bob")
    s.record("pat", "alice", "bob")
    s.record("hug", "carol", "bob")
    assert s.received("bob") == 3                    # all actions received
    assert s.received("bob", "hug") == 2             # hugs received
    assert s.given("alice") == 2                     # alice gave 2 total
    assert s.given("alice", "kiss") == 0
    print("ok S2 given/received totals (overall and per-action)")


def test_returning_an_action_is_separate_direction():
    s = SocialStore()
    s.record("hug", "alice", "bob")                  # alice -> bob
    s.record("hug", "bob", "alice")                  # bob returns
    assert s.pair_count("hug", "alice", "bob") == 1
    assert s.pair_count("hug", "bob", "alice") == 1
    print("ok S3 a returned action is counted in its own direction")


def run():
    test_pair_counts_increment()
    test_given_and_received_totals()
    test_returning_an_action_is_separate_direction()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot social tests passed.")
