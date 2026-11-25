import json
import urllib.request
from . import config


class LLMClient:
    def __init__(self, url=None, model=None):
        self.url = (url or config.OLLAMA_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    def isOnline(self):
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def ask(self, prompt):
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(self.url + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as r:
                reply = json.loads(r.read().decode()).get("response", "").strip()
                return reply or "Sorry, the language model returned nothing."
        except Exception:
            return "Sorry, the language model did not answer."
