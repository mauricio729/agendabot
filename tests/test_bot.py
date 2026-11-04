from datetime import datetime

from app.bot import AgendaBot
from app.calendar_provider import LocalCalendar
from app.messages import Buttons, Incoming, ListMenu, Text
from app.reminders import MemoryReminders
from app.schedule import TZ
from app.sessions import MemorySessionStore
from app.storage import AppointmentRepository

PHONE = "5534999999999"
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=TZ)  # segunda-feira, 9h


class FakeCalendar(LocalCalendar):
    """Agenda local que também registra os eventos criados/apagados."""

    def __init__(self, repo):
        super().__init__(repo)
        self.created, self.deleted = [], []

    def create_event(self, appt, title):
        self.created.append(title)
        return f"evt{appt['id']}"

    def delete_event(self, event_id):
        self.deleted.append(event_id)


def make():
    repo = AppointmentRepository(":memory:")
    cal, rem = FakeCalendar(repo), MemoryReminders()
    bot = AgendaBot(MemorySessionStore(), repo, cal, rem, now=lambda: NOW)
    return bot, repo, cal, rem


def say(bot, text="", rid="", phone=PHONE):
    return bot.handle(Incoming(phone, text=text, reply_id=rid, name="Ana Souza"))


def book(bot, service="limpeza", day="2026-11-10", hour="14:00", phone=PHONE):
    say(bot, "oi", phone=phone)
    say(bot, rid="agendar", phone=phone)
    say(bot, rid=f"srv:{service}", phone=phone)
    say(bot, rid=f"dia:{day}", phone=phone)
    say(bot, rid=f"hora:{day}T{hour}:00-03:00", phone=phone)
    return say(bot, rid="sim", phone=phone)


def test_fluxo_completo_de_agendamento():
    bot, repo, cal, rem = make()
    assert "Ana" in say(bot, "oi")[0].body
    services = say(bot, rid="agendar")[0]
    assert isinstance(services, ListMenu) and len(services.rows) == 4

    days = say(bot, rid="srv:limpeza")[0]
    assert isinstance(days, ListMenu)
    assert days.rows[0][1] == "seg 09/11"  # hoje ainda tem vaga à tarde

    period = say(bot, rid="dia:2026-11-10")[0]  # 17 vagas: pergunta manhã ou tarde
    assert isinstance(period, Buttons) and period.buttons == [("manha", "Manhã (8)"), ("tarde", "Tarde (9)")]
    hours = say(bot, rid="tarde")[0]
    assert ("hora:2026-11-10T14:00:00-03:00", "14:00", "") in hours.rows
    assert all(title >= "13:30" for _, title, _ in hours.rows)

    confirm = say(bot, rid="hora:2026-11-10T14:00:00-03:00")[0]
    assert isinstance(confirm, Buttons) and "terça, 10/11 às 14:00" in confirm.body

    done = say(bot, rid="sim")
    assert "agendado" in done[0].body
    appt = repo.upcoming_for(PHONE, NOW)[0]
    assert appt["event_id"] == "evt1" and cal.created == ["Limpeza dental · Ana Souza"]
    assert rem.scheduled[0][1] == datetime(2026, 11, 9, 14, 0, tzinfo=TZ)


def test_horario_ocupado_some_da_lista():
    bot, *_ = make()
    book(bot)
    say(bot, "menu", phone="5511900000000")
    say(bot, rid="agendar", phone="5511900000000")
    say(bot, rid="srv:limpeza", phone="5511900000000")
    say(bot, rid="dia:2026-11-10", phone="5511900000000")
    rows = say(bot, "tarde", phone="5511900000000")[0].rows
    titles = [title for _, title, _ in rows]
    assert "13:30" in titles and "14:00" not in titles


def test_horario_pego_por_outro_cliente_durante_a_escolha():
    bot, repo, *_ = make()
    other = "5511900000000"
    say(bot, "oi", phone=other)
    say(bot, rid="agendar", phone=other)
    say(bot, rid="srv:limpeza", phone=other)
    say(bot, rid="dia:2026-11-10", phone=other)
    say(bot, rid="hora:2026-11-10T14:00:00-03:00", phone=other)
    book(bot)  # Ana confirma primeiro
    out = say(bot, rid="sim", phone=other)
    assert "acabou de ser ocupado" in out[0].body
    assert len(repo.upcoming_for(other, NOW)) == 0


def test_cancelar_pelos_meus_agendamentos():
    bot, repo, cal, _ = make()
    book(bot)
    say(bot, "menu")
    mine = say(bot, rid="meus")[0]
    assert mine.rows[0][0] == "ag:1"
    say(bot, rid="ag:1")
    out = say(bot, rid="cancelar")
    assert "cancelado" in out[0].body
    assert repo.get(1)["status"] == "cancelado" and cal.deleted == ["evt1"]


def test_nao_acessa_agendamento_de_outra_pessoa():
    bot, *_ = make()
    book(bot)
    say(bot, "oi", phone="5511900000000")
    bot.sessions.save("5511900000000", {"state": "MEUS"})
    out = say(bot, rid="ag:1", phone="5511900000000")
    assert isinstance(out[0], Text) and "Escolha" in out[0].body


def test_resposta_ao_lembrete_confirma():
    bot, repo, *_ = make()
    book(bot)
    out = say(bot, "Confirmar")
    assert "confirmada" in out[0].body
    assert repo.get(1)["status"] == "confirmado"


def test_remarcar_cancela_o_antigo_ao_confirmar_o_novo():
    bot, repo, *_ = make()
    book(bot)
    days = say(bot, "Remarcar")[0]
    assert isinstance(days, ListMenu)
    say(bot, rid="dia:2026-11-11")
    say(bot, rid="hora:2026-11-11T09:00:00-03:00")
    out = say(bot, rid="sim")
    assert "remarcado" in out[0].body
    assert repo.get(1)["status"] == "cancelado"
    assert repo.get(2)["status"] == "agendado"
