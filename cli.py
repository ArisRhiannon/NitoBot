#!/usr/bin/env python3
"""nitobot — terminal CLI.  nitobot run | update | setup | version

`update` fast-forwards the code from git. Your persona.md, data/ (config, wallet key,
memory) and .env are gitignored, so updates never touch your personal/soul settings."""
import argparse
import json
import subprocess
import sys
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


def _enable_knowledge(cfg: dict) -> dict:
    """Turn on the Irminsul knowledge feature in a config dict (pure, testable)."""
    cfg.setdefault("irminsul", {})["enabled"] = True
    mods = cfg.setdefault("modules", [])
    if "knowledge" not in mods:
        mods.append("knowledge")
    return cfg


_AGPL_NOTICE = (
    "\nOptional feature — Irminsul knowledge + Akasha context (long-term memory that\n"
    "consolidates what your server says and feeds it back into Nito's replies).\n"
    "\n  ⚠ Irminsul is licensed AGPL-3.0. If you enable it, a build you distribute or run as a\n"
    "    network service is governed by the AGPL for the combined work — you'd have to offer its\n"
    "    source under the AGPL — unless you hold an Irminsul commercial license. NitoBot's own\n"
    "    code stays MIT, and nothing AGPL is installed unless you say yes here.\n")


def cmd_setup() -> str:
    import config
    config.DATA.mkdir(parents=True, exist_ok=True)
    config.ensure_persona()
    cfgp = config.DATA / "config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else dict(config.DEFAULTS)
    envp = config.ROOT / ".env"
    if not envp.exists():
        try:
            tok = input("Discord bot token (Enter to skip): ").strip()
        except EOFError:
            tok = ""
        if tok:
            envp.write_text(f"NITOBOT_TOKEN={tok}\n", encoding="utf-8")
    # Opt-in, AGPL-aware knowledge feature
    print(_AGPL_NOTICE)
    try:
        ans = input("Enable the Irminsul knowledge feature (AGPL-3.0)? [y/N]: ").strip().lower()
    except EOFError:
        ans = ""
    extra = ""
    if ans in ("y", "yes", "s", "si", "sí"):
        _enable_knowledge(cfg)
        print("Installing irminsul (AGPL-3.0)…")
        r = subprocess.run([sys.executable, "-m", "pip", "install",
                            "irminsul @ git+https://github.com/ArisRhiannon/Irminsul.git"],
                           capture_output=True, text=True)
        extra = ("\nIrminsul enabled (AGPL-3.0). Your combined build is now AGPL-governed."
                 if r.returncode == 0 else
                 "\nEnabled in config, but auto-install failed — run:\n"
                 "  pip install \"irminsul @ git+https://github.com/ArisRhiannon/Irminsul.git\"")
    else:
        print("Knowledge feature left disabled — NitoBot stays MIT-only.")
    cfgp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return "Setup done. Edit data/config.json or persona.md to taste, then: nitobot run" + extra


def cmd_persona(args) -> str:
    """Inspect/manage HoloPersona — the bounded adaptive style layer (persona.md untouched)."""
    import config
    from holopersona import HoloPersona
    config.DATA.mkdir(parents=True, exist_ok=True)
    hp = HoloPersona(db_path=config.DATA / "holo.db", state_path=config.DATA / "holo_state.json")
    a = args.action
    if a == "freeze":
        hp.freeze(True); return "HoloPersona frozen — style is pinned to the core persona."
    if a == "unfreeze":
        hp.freeze(False); return "HoloPersona unfrozen — adaptive layers active again."
    if a == "status":
        return (f"events: {hp.ledger.count()}   users: {len(hp.ledger.scopes())}   "
                f"snapshots: {hp.ledger.snapshot_count()}   frozen: {hp.frozen}   cap: ±{hp.cap}\n"
                f"core persona is immutable; learning is bounded (±cap) + replayable.")
    if a == "consolidate":
        rep = hp.consolidate()
        if not rep:
            return "Nothing stable enough to promote yet."
        out = []
        for uid, st in rep.items():
            out.append(f"Promoted for {uid} (HDC consistency {st['consistency']}):")
            out += [f"  {t} {d:+.3f}" for t, d in st["promoted"]]
        out.append(f"\nSnapshots saved: {len(rep)}.")
        return "\n".join(out)
    if a == "export":
        return json.dumps(hp.export_json(), indent=2)
    if a in ("explain", "drift", "replay", "reset") and not (args.user or args.guild):
        if a == "reset":
            return "reset needs --user <id> or --guild <id>."
        if a in ("explain", "drift"):
            return f"{a} needs --user <id>."
    if a == "reset":
        hp.reset(user_id=args.user, guild_id=args.guild)
        return f"reset {'user '+args.user if args.user else 'guild '+args.guild} — events removed; replay now yields the core."
    if a == "explain":
        g = hp.explain(args.user)
        lines = [f"Relationship style for {args.user}:", ""]
        lines += [f"{t:<14}{m:>5.2f}  {lvl} confidence" for t, (m, lvl) in g.items()]
        return "\n".join(lines)
    if a == "drift":
        rows = hp.drift(args.user)
        if not rows:
            return f"No evidenced drift for {args.user} yet (style == core)."
        return "\n".join(f"{t:<14}{d:+.3f}  {flag}" for t, d, flag in rows)
    if a == "replay":
        n = hp.ledger.count()
        return f"replayed {n} events deterministically; current_persona = replay(holo_events)."
    return "unknown persona action"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nitobot", description="NitoBot — a Discord bot you earn Nito in.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the bot")
    sub.add_parser("update", help="update the code (keeps your persona, data and settings)")
    sub.add_parser("setup", help="create config + persona + token")
    sub.add_parser("version", help="print version")
    pp = sub.add_parser("persona", help="inspect/manage the adaptive style layer (HoloPersona)")
    pp.add_argument("action", choices=["status", "explain", "drift", "freeze", "unfreeze",
                                       "reset", "export", "replay", "consolidate"])
    pp.add_argument("--user")
    pp.add_argument("--guild")
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
    elif args.cmd == "persona":
        print(cmd_persona(args))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
