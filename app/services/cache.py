"""Caché exact-match en memoria para las respuestas del LLM."""

import hashlib
import json
import time
from dataclasses import replace

from app.services.providers import LLMResult, Message


class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 500):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, LLMResult]] = {}

    @staticmethod
    def key(model: str, system: str, messages: list[Message]) -> str:
        payload = json.dumps([model, system, messages], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, key: str) -> LLMResult | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return replace(result, cache_hit=True)

    def set(self, key: str, result: LLMResult) -> None:
        if len(self._store) >= self.max_entries:
            # descarta la entrada más vieja (los dict mantienen el orden de inserción)
            self._store.pop(next(iter(self._store)))
        self._store[key] = (time.monotonic() + self.ttl_seconds, result)

    def clear(self) -> None:
        self._store.clear()
