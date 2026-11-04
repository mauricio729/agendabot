"""Monta os objetos da aplicação a partir das configurações.

Fica separado do main.py para o worker do Celery (tasks.py) usar os mesmos
objetos sem subir a API.
"""
import logging

from .calendar_provider import GoogleCalendar, LocalCalendar
from .config import settings
from .reminders import CeleryReminders, MemoryReminders
from .sessions import make_session_store
from .storage import AppointmentRepository
from .whatsapp import ConsoleSender, WhatsAppClient

log = logging.getLogger("agendabot")

repo = AppointmentRepository(settings.db_path)

if settings.calendar_provider == "google":
    calendar = GoogleCalendar(repo, settings.google_calendar_id, settings.google_token_file)
else:
    calendar = LocalCalendar(repo)

reminders = CeleryReminders() if settings.reminders == "celery" else MemoryReminders()

if settings.wa_token and settings.wa_phone_number_id:
    sender = WhatsAppClient(settings.wa_token, settings.wa_phone_number_id, settings.wa_api_version)
else:
    log.warning("WHATSAPP_TOKEN não configurado: mensagens serão só exibidas no log.")
    sender = ConsoleSender()

sessions = make_session_store(settings.redis_url)
