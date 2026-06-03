#!/usr/bin/env python3
"""NitoBot installer — one command, Windows and Linux/macOS.

    python3 install.py        (Linux/macOS)
    py install.py             (Windows)
"""
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DATA = ROOT / "data"


def venv_python() -> str:
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return str(VENV / sub / exe)


def main():
    print("NitoBot installer\n-----------------")
    if not VENV.exists():
        print("· creating virtual environment (.venv)")
        venv.create(VENV, with_pip=True)
    py = venv_python()
    print("· installing dependencies")
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-U", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])

    DATA.mkdir(exist_ok=True)
    cfg = DATA / "config.json"
    if not cfg.exists():
        secret, peers = "", []
        try:
            secret = input("· network_secret for a private federation (Enter for open): ").strip()
            peer = input("· a peer NitoBot URL to federate with (Enter to skip): ").strip()
            if peer:
                peers = [peer]
        except EOFError:
            pass
        cfg.write_text(json.dumps({
            "quorum": 2, "epoch_seconds": 600,
            "modules": ["meta", "earn", "wallet", "social", "admin"], "peers": peers,
            "gossip_host": "127.0.0.1", "gossip_port": 8787, "network_secret": secret,
            "llm": {"enabled": False, "base_url": "", "api_key_env": "NITOBOT_LLM_KEY", "model": ""},
        }, indent=2), encoding="utf-8")
        print(f"· wrote {cfg.relative_to(ROOT)}")

    env = ROOT / ".env"
    if not env.exists():
        try:
            tok = input("· Discord bot token (Enter to skip): ").strip()
        except EOFError:
            tok = ""
        if tok:
            env.write_text(f"NITOBOT_TOKEN={tok}\n", encoding="utf-8")
            print("· wrote .env")

    print("\nDone. Start NitoBot with:\n  " + py + " bot.py")
    print("(set NITOBOT_TOKEN in .env or your environment first)")


if __name__ == "__main__":
    main()
