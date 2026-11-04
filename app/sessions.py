"""Onde o bot guarda em que ponto da conversa cada cliente está.

A sessão expira em 24h, o mesmo tempo da janela de atendimento do WhatsApp.
Em produção use Redis (REDIS_URL); sem ele, as sessões ficam em memória e
somem quando o servidor reinicia.
"""
from __future__ import annotations

import json
import time

SESSION_TTL = 24 * 60 * 60


class MemorySessionStore:
    def __init__(self, ttl: int = SESSION_TTL, clock=time.time):
        self.ttl = ttl
        self.clock = clock
        self._data: dict[str, tuple[float, dict]] = {}

    def get(self, phone: str) -> dict | None:
        item = self._data.get(phone)
        if not item:
            return None
        expires_at, data = item
        if self.clock() > expires_at:
            del self._data[phone]
            return None
        return dict(data)

    def save(self, phone: str, data: dict) -> None:
        self._data[phone] = (self.clock() + self.ttl, dict(data))

    def clear(self, phone: str) -> None:
        self._data.pop(phone, None)


class RedisSessionStore:
    def __init__(self, url: str, ttl: int = SESSION_TTL, prefix: str = "agendabot:sessao:"):
        import redis  # importado aqui para o Redis ser opcional

        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.ttl = ttl
        self.prefix = prefix

    def get(self, phone: str) -> dict | None:
        raw = self.r.get(self.prefix + phone)
        return json.loads(raw) if raw else None

    def save(self, phone: str, data: dict) -> None:
        self.r.setex(self.prefix + phone, self.ttl, json.dumps(data))

    def clear(self, phone: str) -> None:
        self.r.delete(self.prefix + phone)


def make_session_store(redis_url: str = ""):
    return RedisSessionStore(redis_url) if redis_url else MemorySessionStore()
