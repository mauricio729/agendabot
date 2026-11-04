"""Worker do Celery que envia os lembretes.

Rode em um terminal separado:
    celery -A app.tasks worker --loglevel=info

Fora da janela de 24h o WhatsApp só permite mensagens de template aprovadas
pela Meta. Crie no WhatsApp Manager um template chamado `lembrete_consulta`
(categoria Utilidade) com o texto:

    Olá, {{1}}! Lembrete do seu horário de {{2}} na {{3}}: {{4}}.
    Podemos confirmar sua presença?

e três botões de resposta rápida: Confirmar, Remarcar, Cancelar.
O bot já entende essas três respostas.
"""
from celery import Celery

from .config import settings
from .messages import Template
from .schedule import SERVICES, format_when

broker = settings.redis_url or "redis://localhost:6379/0"
celery_app = Celery("agendabot", broker=broker)
celery_app.conf.timezone = "America/Sao_Paulo"


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_reminder(self, appt_id: int) -> str:
    from .container import repo, sender  # import aqui para não carregar tudo no import do módulo

    appt = repo.get(appt_id)
    if not appt or appt["status"] != "agendado":
        return "ignorado"  # cancelado, remarcado ou já confirmado
    first_name = (appt["name"] or "").split()[0] if appt["name"] else "tudo bem"
    msg = Template(settings.reminder_template, params=[
        first_name, SERVICES[appt["service"]].name, settings.clinic_name, format_when(appt["start"]),
    ])
    try:
        sender.send(appt["phone"], msg)
    except Exception as exc:
        raise self.retry(exc=exc)
    return "enviado"
