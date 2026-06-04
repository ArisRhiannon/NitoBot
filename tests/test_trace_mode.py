"""Trace-mode test — one LLM call returns {reply, holo_trace}; we surface reply and feed the
hardened trace into learning. Mock OpenAI server, offline."""
import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web

from llm import LLMClient, build_messages
from holopersona.respond import respond_with_trace, trace_messages, TRACE_SYSTEM
from holopersona import HoloPersona


def test_trace_messages_injects_instruction():
    msgs = trace_messages([{"role": "system", "content": "You are Nito."},
                           {"role": "user", "content": "hi"}])
    assert TRACE_SYSTEM in msgs[0]["content"] and msgs[0]["content"].startswith("You are Nito.")
    print("ok TR1 trace mode injects the JSON-output instruction into the system message")


async def _trace_roundtrip():
    async def handler(request):
        body = await request.json()
        assert "tools" not in body                         # trace mode is a plain structured call
        payload = {"reply": "short answer.",
                   "holo_trace": {"confidence": 0.7, "next_nudge": {"brevity": 0.5, "emoji": -0.4},
                                  "memory_candidates": [{"text": "user api_key=sk-deadbeef12345"}]}}
        return web.json_response({"choices": [{"message": {"role": "assistant",
                                  "content": json.dumps(payload)}}]})

    app = web.Application(); app.router.add_post("/chat/completions", handler)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8913).start()
    try:
        client = LLMClient("http://127.0.0.1:8913", "nito", "")
        msgs = build_messages("You are Nito.", [], [], "be brief")
        reply, trace = await respond_with_trace(client, msgs)
        assert reply == "short answer."                     # user sees only the reply
        assert trace["next_nudge"]["brevity"] == 0.5 and trace["next_nudge"]["emoji"] == -0.4
        assert trace["blocked_candidates"] == 1 and trace["memory_candidates"] == []  # secret scrubbed
        # the trace's weak evidence is recorded and replays into learned style
        hp = HoloPersona(db_path=":memory:")
        for i in range(20):
            hp.record(user_id="u", text="(no explicit signal)", reply=reply, trace=trace, now=1000.0 + i)
        rel = hp.relationship_means("u")
        assert rel.get("brevity", 0.0) > hp.core["brevity"]   # nudged up over many turns
    finally:
        await runner.cleanup()
    print("ok TR2 single call yields reply + hardened trace; trace feeds bounded learning")


def run():
    test_trace_messages_injects_instruction()
    asyncio.run(_trace_roundtrip())


if __name__ == "__main__":
    run()
    print("\nAll NitoBot trace-mode tests passed.")
