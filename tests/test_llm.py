"""LLM + memory tests. Client tested against a mock OpenAI-compatible server (real HTTP)."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web

from memory import MemoryStore
from llm import LLMClient, build_messages


def test_memory_recall_ranks_relevant_first():
    m = MemoryStore()
    m.remember("u", "alice loves rabbits and coffee", ts=1000)
    m.remember("u", "the server event is on friday", ts=1000)
    m.remember("u", "bob plays guitar", ts=1000)
    out = m.recall("u", "tell me about rabbits", k=1, now=1000)
    assert out and "rabbits" in out[0]
    print("ok L1 memory recalls the most relevant note")


def test_build_messages_structure():
    msgs = build_messages("PERSONA", ["mem one"], [{"role": "user", "content": "hi"},
                          {"role": "assistant", "content": "hello"}], "what's up")
    assert msgs[0] == {"role": "system", "content": "PERSONA"}
    assert msgs[1]["role"] == "system" and "mem one" in msgs[1]["content"]
    assert msgs[-1] == {"role": "user", "content": "what's up"}
    print("ok L2 prompt = persona + memory + history + new message")


async def _scenario_client_roundtrip():
    async def handler(request):
        body = await request.json()
        last = body["messages"][-1]["content"]
        assert request.headers.get("Authorization") == "Bearer testkey"
        return web.json_response({"choices": [{"message": {"role": "assistant", "content": f"echo: {last}"}}]})

    app = web.Application()
    app.router.add_post("/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8899).start()
    try:
        client = LLMClient("http://127.0.0.1:8899", "nito-model", "testkey")
        reply = await client.chat(build_messages("p", [], [], "hello there"))
        assert reply == "echo: hello there", reply
    finally:
        await runner.cleanup()
    print("ok L3 OpenAI-compatible client roundtrip (auth header + content)")


def run():
    test_memory_recall_ranks_relevant_first()
    test_build_messages_structure()
    asyncio.run(_scenario_client_roundtrip())


if __name__ == "__main__":
    run()
    print("\nAll NitoBot llm/memory tests passed.")
