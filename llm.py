"""LLM core — OpenAI-compatible chat, no SDK and no discord dependency.

Talks to any `${base_url}/chat/completions` (OpenAI, a local Ollama/llama.cpp server,
LM Studio, etc.) over aiohttp, so it's trivial to deploy and swap. build_messages is a
pure function (persona + recalled memory + recent turns + the new message)."""
from typing import List

from aiohttp import ClientSession, ClientTimeout


def build_messages(persona: str, memories: List[str], history: List[dict], user_msg: str) -> List[dict]:
    messages = [{"role": "system", "content": persona}]
    if memories:
        messages.append({"role": "system", "content": "Relevant memory:\n- " + "\n- ".join(memories)})
    messages.extend(history)                       # [{"role": "...", "content": "..."}]
    messages.append({"role": "user", "content": user_msg})
    return messages


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.base = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def _post(self, body: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with ClientSession(timeout=ClientTimeout(total=60)) as s:
            async with s.post(f"{self.base}/chat/completions", json=body, headers=headers) as r:
                return await r.json()

    async def chat(self, messages: List[dict], max_tokens: int = 300, temperature: float = 0.6) -> str:
        data = await self._post({"model": self.model, "messages": messages,
                                 "max_tokens": max_tokens, "temperature": temperature})
        return data["choices"][0]["message"]["content"].strip()

    async def chat_full(self, messages: List[dict], tools: List[dict] = None,
                        max_tokens: int = 400, temperature: float = 0.4) -> dict:
        """Returns the full assistant message (may carry tool_calls) for the agent loop."""
        body = {"model": self.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = await self._post(body)
        return data["choices"][0]["message"]
