#!/usr/bin/env python3
"""nitobot — terminal CLI.  nitobot run | update | setup | version

`update` fast-forwards the code from git. Your persona.md, data/ (config, wallet key,
memory) and .env are gitignored, so updates never touch your personal/soul settings."""
import argparse
import json
import subprocess
from pathlib import Path

VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parent


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def cmd_update(root: Path = ROOT) -> str:
    if not (root / ".git").exists():
        return "This NitoBot isn't a git checkout, so it can't self-update. Reinstall from the repo."
    g = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    g("fetch", "--quiet")
    r = g("pull", "--ff-only")
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        return ("Update couldn't fast-forward (local changes to tracked files, or a diverged "
                "branch). Your persona.md, data/ and .env are untouched — resolve with git and retry.\n" + out)
    base = "Already up to date." if "up to date" in out.lower() else "Updated."
    return base + " persona.md, data/ and settings were left untouched. Run 'nitobot run' to apply."


def cmd_setup() -> str:
    import config
    config.DATA.mkdir(parents=True, exist_ok=True)
    config.ensure_persona()
    cfgp = config.DATA / "config.json"
    if not cfgp.exists():
        cfgp.write_text(json.dumps(config.DEFAULTS, indent=2), encoding="utf-8")
    envp = config.ROOT / ".env"
    if not envp.exists():
        try:
            tok = input("Discord bot token (Enter to skip): ").strip()
        except EOFError:
            tok = ""
        if tok:
            envp.write_text(f"NITOBOT_TOKEN={tok}\n", encoding="utf-8")
    return "Setup done. Edit data/config.json or persona.md to taste, then: nitobot run"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nitobot", description="NitoBot — a Discord bot you earn Nito in.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the bot")
    sub.add_parser("update", help="update the code (keeps your persona, data and settings)")
    sub.add_parser("setup", help="create config + persona + token")
    sub.add_parser("version", help="print version")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        import config
        config.ensure_persona()
        import bot
        bot.main()
    elif args.cmd == "update":
        print(cmd_update())
    elif args.cmd == "setup":
        print(cmd_setup())
    elif args.cmd == "version":
        print("nitobot", VERSION)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
