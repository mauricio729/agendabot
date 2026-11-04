"""Configurações lidas do arquivo .env (veja .env.example)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    clinic_name: str = os.getenv("CLINIC_NAME", "Clínica Sorriso")
    # WhatsApp Cloud API
    wa_token: str = os.getenv("WHATSAPP_TOKEN", "")
    wa_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_api_version: str = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "agendabot-dev")
    app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
    reminder_template: str = os.getenv("REMINDER_TEMPLATE", "lembrete_consulta")
    # Agenda: local | google
    calendar_provider: str = os.getenv("CALENDAR_PROVIDER", "local")
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    # Lembretes: memory (só registra) | celery
    reminders: str = os.getenv("REMINDERS", "memory")
    redis_url: str = os.getenv("REDIS_URL", "")
    db_path: str = os.getenv("DB_PATH", "agendabot.db")
    admin_token: str = os.getenv("ADMIN_TOKEN", "troque-esta-chave")


settings = Settings()
