"""Agendamento dos lembretes de 24h antes.

- `CeleryReminders`: produção. Usa o Celery com Redis para disparar a tarefa
  `send_reminder` no horário certo, mesmo se a API reiniciar.
- `MemoryReminders`: simulador e testes. Só guarda o que seria agendado.
"""
from __future__ import annotations

from datetime import datetime, timedelta

REMINDER_BEFORE = timedelta(hours=24)


def reminder_time(start: datetime, now: datetime) -> datetime | None:
    """Quando enviar o lembrete. None se a consulta for em menos de 24h."""
    when = start - REMINDER_BEFORE
    return when if when > now else None


class MemoryReminders:
    def __init__(self):
        self.scheduled: list[tuple[int, datetime]] = []

    def schedule(self, appt_id: int, when: datetime) -> None:
        self.scheduled.append((appt_id, when))


class CeleryReminders:
    def schedule(self, appt_id: int, when: datetime) -> None:
        from .tasks import send_reminder  # import tardio: Celery só é exigido em produção

        send_reminder.apply_async(args=[appt_id], eta=when)
