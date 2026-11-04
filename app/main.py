"""API do AgendaBot (FastAPI).

Rotas:
    GET  /webhook          verificação do webhook pela Meta
    POST /webhook          mensagens recebidas do WhatsApp
    GET  /agenda?dia=...   agendamentos de um dia (para a recepção)
    GET  /health

Rode com:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from .bot import AgendaBot
from .config import settings
from .container import calendar, reminders, repo, sender, sessions
from .schedule import SERVICES, TZ, day_bounds
from .whatsapp import ConsoleSender, parse_webhook, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agendabot")

bot = AgendaBot(sessions, repo, calendar, reminders, clinic=settings.clinic_name)
app = FastAPI(title="AgendaBot", description="Agendamento pelo WhatsApp")


@app.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    if mode == "subscribe" and token == settings.verify_token:
        return challenge
    raise HTTPException(status_code=403, detail="Token de verificação inválido")


def process(payload: dict) -> None:
    for msg in parse_webhook(payload):
        log.info("← %s: %s", msg.phone, msg.value)
        for out in bot.handle(msg):
            try:
                sender.send(msg.phone, out)
            except Exception:
                log.exception("Falha ao enviar mensagem para %s", msg.phone)


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()
    if not verify_signature(settings.app_secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Assinatura inválida")
    await run_in_threadpool(process, json.loads(body or b"{}"))
    return {"ok": True}


def require_admin(x_api_key: str = Header("")):
    if x_api_key != settings.admin_token:
        raise HTTPException(status_code=401, detail="Envie o cabeçalho X-Api-Key")


@app.get("/agenda", dependencies=[Depends(require_admin)])
def agenda(dia: date | None = None):
    start, end = day_bounds(dia or datetime.now(TZ).date())
    return [
        {
            "id": a["id"],
            "horario": f"{a['start']:%H:%M}–{a['end']:%H:%M}",
            "servico": SERVICES[a["service"]].name,
            "cliente": a["name"],
            "telefone": a["phone"],
            "status": a["status"],
        }
        for a in repo.on_day(start, end)
    ]


@app.get("/health")
def health():
    return {"status": "ok", "agenda": settings.calendar_provider, "lembretes": settings.reminders,
            "whatsapp": not isinstance(sender, ConsoleSender)}
