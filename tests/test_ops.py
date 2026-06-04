"""Tests for the CLI self-update (real git) and the history transcript builder. Offline."""
import sys, os, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import cli
from context import build_transcript


def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def test_update_fast_forwards_and_preserves_user_files():
    tmp = Path(tempfile.mkdtemp())
    origin, work = tmp / "origin", tmp / "work"
    origin.mkdir()
    _git(origin, "init", "-q"); _git(origin, "config", "user.email", "t@t"); _git(origin, "config", "user.name", "t")
    (origin / "bot.py").write_text("v1\n"); _git(origin, "add", "-A"); _git(origin, "commit", "-qm", "v1")
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    # user-owned, untracked files (like persona.md / data/) — must survive an update
    (work / "persona.md").write_text("MY SOUL\n")
    (origin / "bot.py").write_text("v2\n"); _git(origin, "add", "-A"); _git(origin, "commit", "-qm", "v2")

    msg = cli.cmd_update(root=work)
    assert "Updated" in msg, msg
    assert (work / "bot.py").read_text() == "v2\n"            # code advanced
    assert (work / "persona.md").read_text() == "MY SOUL\n"   # soul untouched
    # second run is idempotent
    assert "up to date" in cli.cmd_update(root=work).lower()
    print("ok O1 'nitobot update' fast-forwards code and preserves user files")


def test_update_on_non_git_dir():
    tmp = Path(tempfile.mkdtemp())
    assert "isn't a git checkout" in cli.cmd_update(root=tmp)
    print("ok O2 update refuses gracefully when not a git checkout")


def test_transcript_budget_and_bot_tagging():
    msgs = [("alice", "hello there", False), ("Nito", "welcome", True), ("bob", "hi all", False)]
    t = build_transcript(msgs, char_budget=10_000)
    assert t.splitlines() == ["alice: hello there", "Nito [bot]: welcome", "bob: hi all"]
    # tight budget keeps the NEWEST lines
    t2 = build_transcript(msgs, char_budget=12)
    assert t2 == "bob: hi all"
    print("ok O3 transcript tags bots, keeps newest within budget")


def run():
    test_update_fast_forwards_and_preserves_user_files()
    test_update_on_non_git_dir()
    test_transcript_budget_and_bot_tagging()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot ops (CLI/update/context) tests passed.")
