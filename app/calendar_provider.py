"""De onde vem a agenda: banco local ou Google Agenda.

As duas classes têm os mesmos métodos, então o bot não precisa saber qual
está em uso. Escolha com CALENDAR_PROVIDER=local ou CALENDAR_PROVIDER=google.
"""
from __future__ import annotations

from datetime import datetime

from .schedule import Interval
from .storage import AppointmentRepository


class LocalCalendar:
    """Usa só os agendamentos do próprio banco como horários ocupados."""

    def __init__(self, repo: AppointmentRepository):
        self.repo = repo

    def busy(self, start: datetime, end: datetime) -> list[Interval]:
        return self.repo.busy_between(start, end)

    def create_event(self, appt: dict, title: str) -> str | None:
        return None

    def delete_event(self, event_id: str) -> None:
        pass


class GoogleCalendar:
    """Consulta e cria eventos no Google Agenda da clínica.

    Ocupado = agendamentos do bot + qualquer compromisso que a equipe já tenha
    colocado direto no Google Agenda (almoço, folga, reunião...).

    Gere o token com:  python scripts/autorizar_google.py
    """

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, repo: AppointmentRepository, calendar_id: str = "primary",
                 token_file: str = "token.json"):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_file, self.SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())  # OAuth2: renova o token de acesso automaticamente
        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self.calendar_id = calendar_id
        self.repo = repo

    def busy(self, start: datetime, end: datetime) -> list[Interval]:
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                "items": [{"id": self.calendar_id}]}
        resp = self.service.freebusy().query(body=body).execute()
        google_busy = [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in resp["calendars"][self.calendar_id]["busy"]
        ]
        # inclui os do banco também, caso o evento ainda não tenha sido criado
        return google_busy + self.repo.busy_between(start, end)

    def create_event(self, appt: dict, title: str) -> str | None:
        event = {
            "summary": title,
            "description": f"Agendado pelo WhatsApp\nCliente: {appt['name']}\nTelefone: +{appt['phone']}",
            "start": {"dateTime": appt["start"].isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": appt["end"].isoformat(), "timeZone": "America/Sao_Paulo"},
        }
        created = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
        return created["id"]

    def delete_event(self, event_id: str) -> None:
        self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
