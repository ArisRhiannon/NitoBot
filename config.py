"""Config + identity + paths. User-owned files (data/, .env, persona.md) live outside
git so `nitobot update` never clobbers them; persona.default.md is the tracked template."""
import json
import os
from pathlib import Path

from earn import Instance

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NITOBOT_DATA", ROOT / "data"))
PERSONA = ROOT / "persona.md"               # user-owned (gitignored)
PERSONA_DEFAULT = ROOT / "persona.default.md"  # tracked template

DEFAULTS = {
    "quorum": 2,
    "epoch_seconds": 600,
    "history_limit": 300,        # how many recent channel messages the agent reads as context
    "modules": ["meta", "earn", "wallet", "social", "admin"],
    "peers": [],
    "gossip_host": "127.0.0.1",
    "gossip_port": 8787,
    "network_secret": "",
    "holopersona": {"enabled": True, "trace": False},
    "llm": {"enabled": False, "base_url": "", "api_key_env": "NITOBOT_LLM_KEY", "model": ""},
}


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def ensure_persona() -> Path:
    """Create the user's editable persona.md from the template on first use."""
    if not PERSONA.exists() and PERSONA_DEFAULT.exists():
        PERSONA.write_text(PERSONA_DEFAULT.read_text(encoding="utf-8"), encoding="utf-8")
    return PERSONA


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = DATA / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def load_instance() -> Instance:
    DATA.mkdir(parents=True, exist_ok=True)
    keyfile = DATA / "instance.key"
    if keyfile.exists():
        return Instance(bytes.fromhex(keyfile.read_text(encoding="utf-8").strip()))
    inst = Instance()
    keyfile.write_text(inst.secret().hex(), encoding="utf-8")
    try:
        os.chmod(keyfile, 0o600)
    except OSError:
        pass
    return inst


def token() -> str:
    t = os.environ.get("NITOBOT_TOKEN", "").strip()
    if not t:
        raise SystemExit("Set NITOBOT_TOKEN to your Discord bot token (see README).")
    return t
