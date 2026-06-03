"""NitoBot gossip — how independent NitoBots federate the earn ledger (no central server).

Security, in layers:
- Every attestation is ed25519-signed and self-validating: a forged one is dropped on
  ingest, so even an open endpoint can't be tricked into paying out fake Nito.
- Optional `network_secret`: requires an HMAC-SHA256 header on every request, so a private
  federation only talks to its own bots (constant-time compared).
- Binds 127.0.0.1 by default — never exposed unless the operator puts it behind TLS
  (e.g. a Cloudflare tunnel / reverse proxy). Activity data (Discord IDs + counts) then
  travels encrypted between bots.
- Per-IP rate limit + body-size cap to blunt spam/DoS.
"""
import hashlib
import hmac
import json
import time

from aiohttp import web, ClientSession, ClientTimeout

MAX_BODY = 512 * 1024
RATE_PER_10S = 60


def auth_tag(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class GossipServer:
    def __init__(self, economy, host="127.0.0.1", port=8787, secret=""):
        self.economy, self.host, self.port, self.secret = economy, host, port, secret
        self._hits = {}
        self._runner = None

    def _rate_ok(self, ip: str) -> bool:
        win = int(time.time()) // 10
        w, c = self._hits.get(ip, (win, 0))
        c = c + 1 if w == win else 1
        self._hits[ip] = (win, c)
        return c <= RATE_PER_10S

    def _authed(self, request, body: bytes) -> bool:
        if not self.secret:
            return True
        return hmac.compare_digest(request.headers.get("X-Nito-Auth", ""), auth_tag(self.secret, body))

    async def _gossip(self, request):
        if not self._rate_ok(request.remote or "?"):
            return web.json_response({"error": "rate limited"}, status=429)
        body = await request.read()
        if len(body) > MAX_BODY:
            return web.json_response({"error": "too large"}, status=413)
        if not self._authed(request, body):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            data = json.loads(body)
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        atts = data if isinstance(data, list) else [data]
        accepted = 0
        for att in atts:
            try:
                self.economy.ingest(att)   # verifies ed25519 sig; forged -> raises -> dropped
                accepted += 1
            except Exception:
                pass
        return web.json_response({"accepted": accepted})

    async def _ledger(self, request):
        if self.secret and not hmac.compare_digest(request.headers.get("X-Nito-Auth", ""), auth_tag(self.secret, b"ledger")):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(list(self.economy.ledger.atts.values()))

    async def start(self):
        app = web.Application(client_max_size=MAX_BODY)
        app.add_routes([web.post("/gossip", self._gossip), web.get("/ledger", self._ledger)])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


class GossipClient:
    def __init__(self, economy, peers, secret=""):
        self.economy, self.peers, self.secret = economy, list(peers), secret

    def _headers(self, body: bytes) -> dict:
        h = {"Content-Type": "application/json"}
        if self.secret:
            h["X-Nito-Auth"] = auth_tag(self.secret, body)
        return h

    async def publish(self, att: dict):
        body = json.dumps(att).encode("utf-8")
        async with ClientSession(timeout=ClientTimeout(total=5)) as s:
            for url in self.peers:
                try:
                    async with s.post(f"{url.rstrip('/')}/gossip", data=body, headers=self._headers(body)):
                        pass
                except Exception:
                    pass  # a peer being down must never break earning

    async def pull(self):
        headers = {"X-Nito-Auth": auth_tag(self.secret, b"ledger")} if self.secret else {}
        async with ClientSession(timeout=ClientTimeout(total=5)) as s:
            for url in self.peers:
                try:
                    async with s.get(f"{url.rstrip('/')}/ledger", headers=headers) as r:
                        for att in await r.json():
                            try:
                                self.economy.ingest(att)
                            except Exception:
                                pass
                except Exception:
                    pass
