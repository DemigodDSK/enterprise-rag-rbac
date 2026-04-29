"""Pluggable LLM generator. OpenAI is the default; Z.AI remains as a fallback provider."""
import os
import time

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"
DEFAULT_ZAI_MODEL = "glm-4-flash"

ZAI_ENDPOINTS = [
    ("Z.AI International", "https://api.z.ai/api/paas/v4/"),
    ("ZhipuAI China", "https://open.bigmodel.cn/api/paas/v4/"),
]
ZAI_MODEL_CANDIDATES = [
    "glm-4-flash", "glm-4.5-flash", "glm-4.5-air", "glm-4-air",
    "glm-4-plus", "glm-4", "glm-4.5", "glm-4.6",
]


def _auto_detect_zai(client_factory, key, forced_model=None):
    """Try endpoint + model combos until one returns a real response. Returns (client, model, base_url)."""
    candidates = [forced_model] if forced_model else ZAI_MODEL_CANDIDATES
    for ep_name, ep_url in ZAI_ENDPOINTS:
        client = client_factory(api_key=key, base_url=ep_url)
        for model in candidates:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ok"}],
                    max_tokens=5, timeout=15,
                )
                if resp.choices and resp.choices[0].message.content:
                    print(f"  ✅ Z.AI: {ep_name} / {model}")
                    return client, model, ep_url
            except Exception:
                continue
    return None, None, None

SYSTEM_PROMPT = """You are a professional enterprise AI assistant for Aurelius Health Systems.

INSTRUCTIONS:
- Answer naturally and clearly, as if speaking to an employee.
- Do NOT mention file paths, chunking, metadata, or internal system behavior.
- Do NOT say "based on the document" or "the context says".
- Prefer a single clean paragraph unless the user explicitly asks for a list.
- Only use information from the provided context blocks.
- If the context is insufficient, say: "I don't have enough information in the allowed documents."
- Add source citations ONLY at the very end, formatted as: Sources: [1], [2]
- Be concise, professional, and helpful."""


class LLMGenerator:
    """Two providers, one interface. Selected via LLM_PROVIDER env var ('openai' or 'zai')."""

    def __init__(self):
        self.client = None
        self.available = False
        self.provider = os.environ.get("LLM_PROVIDER", "openai").lower().strip()
        self.model = None
        self.base_url = None

        try:
            from openai import OpenAI
        except ImportError:
            print("  ⚠️  openai package not installed — retrieval-only mode")
            return

        if self.provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not key:
                print("  ⚠️  OPENAI_API_KEY not set — retrieval-only mode")
                return
            self.model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
            self.client = OpenAI(api_key=key)
            self.available = True
            print(f"  ✅ OpenAI LLM ready (model: {self.model})")
        elif self.provider == "zai":
            key = os.environ.get("ZAI_API_KEY", "").strip()
            if not key:
                print("  ⚠️  ZAI_API_KEY not set — retrieval-only mode")
                return
            forced_model = os.environ.get("ZAI_MODEL", "").strip() or None
            client, model, base_url = _auto_detect_zai(OpenAI, key, forced_model)
            if client is None:
                print("  ⚠️  Z.AI: no working endpoint/model combo — retrieval-only mode")
                return
            self.client = client
            self.model = model
            self.base_url = base_url
            self.available = True
        else:
            print(f"  ⚠️  Unknown LLM_PROVIDER='{self.provider}' — retrieval-only mode")

    def answer(self, query: str, docs, user) -> str:
        if not self.available:
            return self._fallback(docs)

        ctx = ""
        for i, d in enumerate(docs, 1):
            source = d.metadata.get("source", "?")
            category = d.metadata.get("category", "?")
            ctx += f"\n--- SOURCE {i}: {source} [{category}] ---\n{d.page_content.strip()}\n"

        user_msg = f"CONTEXT DOCUMENTS:\n{ctx}\n\nQUESTION: {query}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(2 ** attempt)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                    timeout=30,
                )
                return response.choices[0].message.content
            except Exception as e:
                err = str(e)
                if ("429" in err or "rate" in err.lower()) and attempt < max_retries - 1:
                    continue
                print(f"  ⚠️  LLM error: {err[:200]}")
                return (
                    "⚠️ AI service error. Here are the relevant document excerpts:\n\n"
                    + self._fallback(docs)
                )
        return self._fallback(docs)

    @staticmethod
    def _fallback(docs) -> str:
        if not docs:
            return "No matching documents found for your query."
        parts = []
        for i, d in enumerate(docs, 1):
            name = d.metadata.get("source", "?").replace(".md", "").replace("_", " ")
            excerpt = d.page_content.strip()[:400]
            lines = [l for l in excerpt.split("\n") if l.strip() and not l.startswith("# ")]
            clean = " ".join(lines)[:350]
            parts.append(f"**{i}. {name}**\n{clean}...")
        return "\n\n".join(parts)
