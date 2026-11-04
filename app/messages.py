"""Tipos de mensagem usados pelo bot.

O bot nunca chama a API do WhatsApp diretamente: ele recebe um `Incoming`
e devolve uma lista de mensagens de saída (Text, Buttons, ListMenu, Template).
Quem envia de verdade é o `WhatsAppClient` (produção) ou o `ConsoleSender`
(simulador e desenvolvimento). Isso deixa a lógica do bot fácil de testar.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Incoming:
    """Mensagem recebida de um cliente."""

    phone: str            # número do cliente no formato do WhatsApp (ex.: 5534999999999)
    text: str = ""        # texto digitado (ou título do botão clicado)
    reply_id: str = ""    # id do botão ou da linha da lista que o cliente clicou
    name: str = ""        # nome do perfil do cliente no WhatsApp

    @property
    def value(self) -> str:
        """O que o cliente escolheu: o id do botão, se houver, senão o texto."""
        return (self.reply_id or self.text).strip()


@dataclass
class Text:
    body: str


@dataclass
class Buttons:
    """Até 3 botões de resposta rápida. Cada botão é (id, título)."""

    body: str
    buttons: list[tuple[str, str]]


@dataclass
class ListMenu:
    """Menu em lista com até 10 linhas. Cada linha é (id, título, descrição)."""

    body: str
    button: str
    rows: list[tuple[str, str, str]]
    section_title: str = "Opções"


@dataclass
class Template:
    """Mensagem de template aprovada pela Meta (necessária fora da janela de 24h)."""

    name: str
    language: str = "pt_BR"
    params: list[str] = field(default_factory=list)


Outgoing = Text | Buttons | ListMenu | Template
