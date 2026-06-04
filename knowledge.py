"""Irminsul integration for NitoBot — server-scoped knowledge consolidation + Akasha context
injection. Discord-free so it's testable offline; the cog (cogs/knowledge.py) drives it.

Knowledge is consolidated per guild (scope ``guild:<id>``) so facts learned by the server are
shared across its members. persona.md is never touched; every call is safe to fail. All engine
access is serialized with a lock so it's safe to call from both the event loop and worker
threads (the Irminsul sqlite connections are shared across threads)."""
import threading

from irminsul import AkashaConfig, Engine, ModelInfo

from config import DATA


class Knowledge:
    def __init__(self, cfg: dict, db_path: str = None):
        ic = (cfg or {}).get("irminsul", {})
        self.ctx_window = int(ic.get("context_window", 8192))
        self._lock = threading.Lock()
        ak = AkashaConfig(
            base_pct=float(ic.get("base_pct", 0.15)),
            min_tokens=int(ic.get("min_tokens", 256)),
            max_tokens=int(ic.get("max_tokens", 2048)),
            ambient_on_small_ctx=bool(ic.get("ambient_on_small_ctx", False)),
        )
        path = db_path if db_path is not None else str(DATA / "irminsul.db")
        self.engine = Engine(path, akasha_config=ak,
                             model=ModelInfo(name="nito", context_window=self.ctx_window))

    @staticmethod
    def scope_for(guild_id) -> str:
        return f"guild:{guild_id}"

    def remember(self, text: str, scope: str) -> bool:
        with self._lock:
            return self.engine.remember(text, scope=scope)

    def grow(self, scope: str):
        with self._lock:
            return self.engine.grow(scope=scope)

    def card(self, message: str, scope: str, used_tokens: int = 0) -> str:
        """The Akasha knowledge card to prepend to the prompt ('' if nothing to add). Never raises."""
        with self._lock:
            return self.engine.knowledge_card(
                message, scope=scope,
                model=ModelInfo(name="nito", context_window=self.ctx_window),
                used_tokens=max(0, int(used_tokens)))

    def status(self, scope: str = None) -> dict:
        with self._lock:
            return self.engine.status(scope)

    def close(self):
        with self._lock:
            self.engine.close()
