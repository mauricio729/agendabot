"""Integração com a WhatsApp Cloud API (Meta).

- `parse_webhook`: transforma o JSON que a Meta envia no webhook em `Incoming`.
- `verify_signature`: confere o cabeçalho X-Hub-Signature-256 (HMAC SHA-256).
- `build_payload`: monta o JSON de envio para cada tipo de mensagem.
- `WhatsAppClient`: envia mensagens pela API.
- `ConsoleSender`: imprime as mensagens no terminal (modo desenvolvimento).

Documentação oficial: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

import hashlib
import hmac
import logging

import requests

from .messages import Buttons, Incoming, ListMenu, Outgoing, Template, Text

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"

# Limites de caracteres da API para mensagens interativas
MAX_BUTTON_TITLE = 20
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72


def parse_webhook(payload: dict) -> list[Incoming]:
    """Extrai as mensagens de clientes de um evento de webhook.

    Eventos de status (entregue, lida...) são ignorados: só nos interessam
    as mensagens que o cliente mandou.
    """
    result: list[Incoming] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {
                c.get("wa_id"): c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
            }
            for m in value.get("messages", []):
                phone = m.get("from", "")
                msg = Incoming(phone=phone, name=names.get(phone, ""))
                kind = m.get("type")
                if kind == "text":
                    msg.text = m.get("text", {}).get("body", "")
                elif kind == "interactive":
                    inter = m.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    msg.reply_id = reply.get("id", "")
                    msg.text = reply.get("title", "")
                elif kind == "button":  # botão de resposta rápida de um template
                    msg.reply_id = m.get("button", {}).get("payload", "")
                    msg.text = m.get("button", {}).get("text", "")
                else:
                    # áudio, imagem, figurinha... o bot responde pedindo texto
                    msg.text = f"[{kind}]"
                result.append(msg)
    return result


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Confere se o webhook veio mesmo da Meta.

    A Meta assina o corpo da requisição com o App Secret e envia o resultado
    em `X-Hub-Signature-256: sha256=<hex>`. Sem App Secret configurado
    (desenvolvimento local), a verificação é ignorada.
    """
    if not app_secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def build_payload(to: str, msg: Outgoing) -> dict:
    """Monta o JSON que a Cloud API espera para cada tipo de mensagem."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}

    if isinstance(msg, Text):
        return {**base, "type": "text", "text": {"body": msg.body, "preview_url": False}}

    if isinstance(msg, Buttons):
        buttons = [
            {"type": "reply", "reply": {"id": bid, "title": title[:MAX_BUTTON_TITLE]}}
            for bid, title in msg.buttons[:3]
        ]
        return {
            **base,
            "type": "interactive",
            "interactive": {"type": "button", "body": {"text": msg.body}, "action": {"buttons": buttons}},
        }

    if isinstance(msg, ListMenu):
        rows = [
            {"id": rid, "title": title[:MAX_ROW_TITLE], "description": desc[:MAX_ROW_DESCRIPTION]}
            for rid, title, desc in msg.rows[:10]
        ]
        return {
            **base,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": msg.body},
                "action": {
                    "button": msg.button[:MAX_BUTTON_TITLE],
                    "sections": [{"title": msg.section_title[:MAX_ROW_TITLE], "rows": rows}],
                },
            },
        }

    if isinstance(msg, Template):
        components = []
        if msg.params:
            components.append(
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in msg.params]}
            )
        return {
            **base,
            "type": "template",
            "template": {"name": msg.name, "language": {"code": msg.language}, "components": components},
        }

    raise TypeError(f"Tipo de mensagem não suportado: {type(msg).__name__}")


class WhatsAppClient:
    """Envia mensagens pela WhatsApp Cloud API."""

    def __init__(self, token: str, phone_number_id: str, api_version: str = "v21.0",
                 session: requests.Session | None = None):
        self.url = f"{GRAPH_URL}/{api_version}/{phone_number_id}/messages"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session = session or requests.Session()

    def send(self, to: str, msg: Outgoing) -> dict:
        payload = build_payload(to, msg)
        resp = self.session.post(self.url, json=payload, headers=self.headers, timeout=10)
        if resp.status_code >= 400:
            log.error("Erro ao enviar para %s: %s %s", to, resp.status_code, resp.text)
            resp.raise_for_status()
        return resp.json()


def render(msg: Outgoing) -> str:
    """Representação em texto de uma mensagem, para o terminal."""
    if isinstance(msg, Text):
        return msg.body
    if isinstance(msg, Buttons):
        opts = "  ".join(f"[{title}]" for _, title in msg.buttons)
        return f"{msg.body}\n{opts}"
    if isinstance(msg, ListMenu):
        lines = [msg.body, f"☰ {msg.button}"]
        lines += [f"  • {title}" + (f" — {desc}" if desc else "") for _, title, desc in msg.rows]
        return "\n".join(lines)
    if isinstance(msg, Template):
        return f"(template {msg.name}) {' | '.join(msg.params)}"
    return str(msg)


class ConsoleSender:
    """Usado quando não há token do WhatsApp: só mostra no terminal/log."""

    def __init__(self):
        self.sent: list[tuple[str, Outgoing]] = []

    def send(self, to: str, msg: Outgoing) -> dict:
        self.sent.append((to, msg))
        log.info("→ %s\n%s", to, render(msg))
        return {"console": True}


def match_option(value: str, options: list[tuple[str, ...]]) -> str | None:
    """Permite que o cliente escolha uma opção digitando o número ou o título.

    Ex.: com opções [("status", "Status do pedido"), ...], tanto "1" quanto
    "status do pedido" retornam "status". Clicar no botão já manda o id.
    """
    v = value.strip().lower()
    for i, opt in enumerate(options, start=1):
        oid, title = opt[0], opt[1]
        if v in (oid.lower(), str(i), title.lower()):
            return oid
    return None
