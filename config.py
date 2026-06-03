"""Config + persistent validator identity. Settings in data/config.json, secrets in env."""
import json
import os
from pathlib import Path

from earn import Instance

DATA = Path(os.environ.get("NITOBOT_DATA", "data"))


def _load_dotenv():
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DEFAULTS = {
    "quorum": 2,            # independent NitoBots that must agree to confirm earnings
    "epoch_seconds": 600,   # message-commit window per channel
    "modules": ["meta", "earn", "wallet", "social", "admin"],
    "peers": [],            # NitoBot gossip endpoints (federation; no central server)
    "gossip_host": "127.0.0.1",   # bind loopback by default; expose via TLS proxy/Cloudflare tunnel
    "gossip_port": 8787,
    "network_secret": "",   # set the same value on your bots for a private, authenticated federation
    "automod": {"mode": "SHADOW"},   # opt-in: add "automod" to modules; needs goodfaith
    "llm": {"enabled": False, "base_url": "", "api_key_env": "NITOBOT_LLM_KEY", "model": ""},
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = DATA / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def load_instance() -> Instance:
    """Load this bot's ed25519 identity, creating + persisting one on first run."""
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
