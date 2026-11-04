"""Fluxo de conversa do AgendaBot.

    INICIO ─> MENU ─> SERVICO ─> DIA ─> (PERIODO) ─> HORA ─> CONFIRMAR ─> agendado ✅
                │
                └─> MEUS (lista) ─> AGENDAMENTO (cancelar / remarcar)

Respostas ao lembrete (template com botões Confirmar / Remarcar / Cancelar)
são tratadas em qualquer estado.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from .messages import Buttons, Incoming, ListMenu, Outgoing, Text
from .reminders import reminder_time
from .schedule import (SERVICES, TZ, day_bounds, format_day, format_price, format_when,
                       free_slots)
from .whatsapp import match_option

DAYS_AHEAD = 14       # até quantos dias à frente procurar vagas
MAX_DAYS_LISTED = 7   # quantos dias mostrar na lista
MAX_SLOTS_LISTED = 10  # limite de linhas de uma lista do WhatsApp

MAIN_BUTTONS = [("agendar", "Agendar horário"), ("meus", "Meus agendamentos")]
BACK_WORDS = {"menu", "0", "voltar", "inicio", "início", "oi", "olá", "ola"}


class AgendaBot:
    def __init__(self, sessions, repo, calendar, reminders, clinic: str = "Clínica Sorriso",
                 now: Callable[[], datetime] = lambda: datetime.now(TZ)):
        self.sessions = sessions
        self.repo = repo
        self.calendar = calendar
        self.reminders = reminders
        self.clinic = clinic
        self.now = now

    # ------------------------------------------------------------------ entrada
    def handle(self, msg: Incoming) -> list[Outgoing]:
        s = self.sessions.get(msg.phone) or {"state": "INICIO"}
        value = msg.value
        low = value.lower()

        # Respostas aos botões do template de lembrete
        if low in ("confirmar", "remarcar", "cancelar") and s["state"] not in ("CONFIRMAR", "AGENDAMENTO"):
            reply = self._reminder_reply(msg, low)
            if reply:
                return reply

        if s["state"] == "INICIO" or low in BACK_WORDS:
            return self._go_menu(msg, greeting=s["state"] == "INICIO")

        handler = {
            "MENU": self._on_menu,
            "SERVICO": self._on_service,
            "DIA": self._on_day,
            "PERIODO": self._on_period,
            "HORA": self._on_slot,
            "CONFIRMAR": self._on_confirm,
            "MEUS": self._on_my_list,
            "AGENDAMENTO": self._on_appointment_action,
        }.get(s["state"], self._on_menu)
        return handler(msg, s)

    # ------------------------------------------------------------------ menu
    def _go_menu(self, msg: Incoming, greeting: bool = False) -> list[Outgoing]:
        out: list[Outgoing] = []
        if greeting:
            first = msg.name.split()[0] if msg.name else ""
            out.append(Text(f"Olá{', ' + first if first else ''}! 👋 Aqui é o assistente de "
                            f"agendamentos da {self.clinic}."))
        out.append(Buttons("O que você quer fazer?", MAIN_BUTTONS))
        return self._save(msg.phone, {"state": "MENU"}, out)

    def _on_menu(self, msg: Incoming, s: dict) -> list[Outgoing]:
        choice = match_option(msg.value, MAIN_BUTTONS)
        if choice == "agendar" or "agend" in msg.value.lower() or "marcar" in msg.value.lower():
            return self._ask_service(msg)
        if choice == "meus":
            return self._show_mine(msg)
        return self._save(msg.phone, {"state": "MENU"},
                          [Text("Não entendi 🤔"), Buttons("Escolha uma opção:", MAIN_BUTTONS)])

    # ------------------------------------------------------------------ agendar
    def _ask_service(self, msg: Incoming) -> list[Outgoing]:
        rows = [(f"srv:{sv.id}", sv.name, f"{sv.minutes} min · {format_price(sv.price)}")
                for sv in SERVICES.values()]
        return self._save(msg.phone, {"state": "SERVICO"},
                          [ListMenu("Qual serviço você quer agendar?", "Ver serviços", rows)])

    def _on_service(self, msg: Incoming, s: dict) -> list[Outgoing]:
        options = [(sid, sv.name) for sid, sv in SERVICES.items()]
        sid = msg.value.removeprefix("srv:") if msg.value.startswith("srv:") else match_option(msg.value, options)
        if sid not in SERVICES:
            return [Text("Escolha um dos serviços da lista, por favor.")]
        return self._ask_day(msg, sid)

    def _ask_day(self, msg: Incoming, sid: str, reschedule_id: int | None = None) -> list[Outgoing]:
        service = SERVICES[sid]
        rows = []
        today = self.now().date()
        for i in range(DAYS_AHEAD):
            d = today + timedelta(days=i)
            n = len(self._slots(d, service.minutes))
            if n:
                rows.append((f"dia:{d.isoformat()}", format_day(d),
                             f"{n} horário{'s' if n > 1 else ''} livre{'s' if n > 1 else ''}"))
            if len(rows) == MAX_DAYS_LISTED:
                break
        if not rows:
            return self._save(msg.phone, {"state": "MENU"}, [
                Text("Não temos horários livres nas próximas duas semanas. 😕"),
                Buttons("Posso ajudar com outra coisa?", MAIN_BUTTONS)])
        session = {"state": "DIA", "service": sid, "reschedule": reschedule_id}
        return self._save(msg.phone, session,
                          [ListMenu(f"*{service.name}* ({service.minutes} min). Qual dia fica melhor?",
                                    "Ver dias", rows)])

    def _on_day(self, msg: Incoming, s: dict) -> list[Outgoing]:
        if not msg.value.startswith("dia:"):
            return [Text("Escolha um dia da lista, por favor.")]
        d = date.fromisoformat(msg.value.removeprefix("dia:"))
        service = SERVICES[s["service"]]
        slots = self._slots(d, service.minutes)
        if not slots:
            return [Text("Esse dia acabou de lotar. Escolha outro, por favor.")]
        session = {**s, "day": d.isoformat()}
        morning = [t for t in slots if t.hour < 12]
        afternoon = [t for t in slots if t.hour >= 12]
        # Uma lista do WhatsApp tem no máximo 10 linhas: com muitas vagas, pergunta o período
        if len(slots) > MAX_SLOTS_LISTED and morning and afternoon:
            buttons = [("manha", f"Manhã ({len(morning)})"), ("tarde", f"Tarde ({len(afternoon)})")]
            return self._save(msg.phone, {**session, "state": "PERIODO"},
                              [Buttons(f"{format_day(d)}: prefere manhã ou tarde?", buttons)])
        return self._list_slots(msg, session, slots)

    def _on_period(self, msg: Incoming, s: dict) -> list[Outgoing]:
        if msg.value.startswith("hora:"):  # tocou num horário de uma lista anterior
            return self._on_slot(msg, s)
        period = match_option(msg.value, [("manha", "Manhã"), ("tarde", "Tarde")])
        if msg.value.lower().startswith("manh"):
            period = "manha"
        elif msg.value.lower().startswith("tard"):
            period = "tarde"
        if period not in ("manha", "tarde"):
            return [Text("Toque em *Manhã* ou *Tarde*.")]
        d = date.fromisoformat(s["day"])
        slots = self._slots(d, SERVICES[s["service"]].minutes)
        slots = [t for t in slots if (t.hour < 12) == (period == "manha")]
        return self._list_slots(msg, s, slots)

    def _list_slots(self, msg: Incoming, s: dict, slots: list[datetime]) -> list[Outgoing]:
        d = date.fromisoformat(s["day"])
        rows = [(f"hora:{t.isoformat()}", f"{t:%H:%M}", "") for t in slots[:MAX_SLOTS_LISTED]]
        return self._save(msg.phone, {**s, "state": "HORA"},
                          [ListMenu(f"Horários livres em {format_day(d)}:", "Ver horários", rows)])

    def _on_slot(self, msg: Incoming, s: dict) -> list[Outgoing]:
        if not msg.value.startswith("hora:"):
            return [Text("Escolha um horário da lista, por favor.")]
        start = datetime.fromisoformat(msg.value.removeprefix("hora:"))
        service = SERVICES[s["service"]]
        text = (f"Confirma o agendamento?\n\n🦷 {service.name}\n📅 {format_when(start)}\n"
                f"💰 {format_price(service.price)}")
        buttons = [("sim", "Confirmar"), ("outro", "Outro horário"), ("menu", "Cancelar")]
        return self._save(msg.phone, {**s, "state": "CONFIRMAR", "slot": start.isoformat()},
                          [Buttons(text, buttons)])

    def _on_confirm(self, msg: Incoming, s: dict) -> list[Outgoing]:
        choice = match_option(msg.value, [("sim", "Confirmar"), ("outro", "Outro horário")])
        if choice == "outro":
            return self._ask_day(msg, s["service"], s.get("reschedule"))
        if choice != "sim":
            return [Text("Toque em *Confirmar*, *Outro horário* ou *Cancelar*.")]

        service = SERVICES[s["service"]]
        start = datetime.fromisoformat(s["slot"])
        end = start + timedelta(minutes=service.minutes)

        # Confere de novo: alguém pode ter pego o horário enquanto o cliente decidia
        if start not in self._slots(start.date(), service.minutes):
            sorry = Text("Poxa, esse horário acabou de ser ocupado. 😕 Escolha outro:")
            return [sorry] + self._ask_day(msg, s["service"], s.get("reschedule"))

        if s.get("reschedule"):
            self._cancel(s["reschedule"])

        appt = self.repo.create(msg.phone, msg.name, service.id, start, end)
        event_id = self.calendar.create_event(appt, f"{service.name} · {msg.name or msg.phone}")
        if event_id:
            self.repo.set_event_id(appt["id"], event_id)
        when = reminder_time(start, self.now())
        if when:
            self.reminders.schedule(appt["id"], when)

        verb = "remarcado" if s.get("reschedule") else "agendado"
        text = (f"Prontinho, {verb}! ✅\n\n🦷 {service.name}\n📅 {format_when(start)}\n"
                f"📍 {self.clinic}\n\n"
                + ("Vou te mandar um lembrete um dia antes." if when else "Até já!"))
        return self._save(msg.phone, {"state": "MENU"},
                          [Text(text), Buttons("Precisa de mais alguma coisa?", MAIN_BUTTONS)])

    # ------------------------------------------------------------------ meus agendamentos
    def _show_mine(self, msg: Incoming) -> list[Outgoing]:
        appts = self.repo.upcoming_for(msg.phone, self.now())
        if not appts:
            return self._save(msg.phone, {"state": "MENU"},
                              [Buttons("Você não tem agendamentos futuros.", MAIN_BUTTONS)])
        rows = [(f"ag:{a['id']}", f"{format_day(a['start'].date())} {a['start']:%H:%M}",
                 SERVICES[a["service"]].name + (" · confirmado" if a["status"] == "confirmado" else ""))
                for a in appts[:10]]
        return self._save(msg.phone, {"state": "MEUS"},
                          [ListMenu("Seus próximos agendamentos:", "Ver agendamentos", rows)])

    def _on_my_list(self, msg: Incoming, s: dict) -> list[Outgoing]:
        appt = self._own_appointment(msg)
        if not appt:
            return [Text("Escolha um agendamento da lista, por favor.")]
        text = f"{SERVICES[appt['service']].name}\n📅 {format_when(appt['start'])}\nO que deseja fazer?"
        buttons = [("remarcar", "Remarcar"), ("cancelar", "Cancelar"), ("menu", "Voltar")]
        return self._save(msg.phone, {"state": "AGENDAMENTO", "appt": appt["id"]}, [Buttons(text, buttons)])

    def _on_appointment_action(self, msg: Incoming, s: dict) -> list[Outgoing]:
        appt = self.repo.get(s["appt"])
        action = match_option(msg.value, [("remarcar", "Remarcar"), ("cancelar", "Cancelar")])
        if action == "cancelar":
            self._cancel(appt["id"])
            return self._save(msg.phone, {"state": "MENU"}, [
                Text(f"Agendamento de {format_when(appt['start'])} cancelado."),
                Buttons("Quer marcar outro horário?", MAIN_BUTTONS)])
        if action == "remarcar":
            return self._ask_day(msg, appt["service"], reschedule_id=appt["id"])
        return [Text("Toque em *Remarcar*, *Cancelar* ou *Voltar*.")]

    # ------------------------------------------------------------------ lembrete
    def _reminder_reply(self, msg: Incoming, action: str) -> list[Outgoing] | None:
        """O cliente respondeu ao lembrete. Vale para o próximo agendamento em até 48h."""
        now = self.now()
        appts = [a for a in self.repo.upcoming_for(msg.phone, now)
                 if a["start"] - now <= timedelta(hours=48)]
        if not appts:
            return None
        appt = appts[0]
        if action == "confirmar":
            self.repo.set_status(appt["id"], "confirmado")
            return self._save(msg.phone, {"state": "MENU"},
                              [Text(f"Presença confirmada para {format_when(appt['start'])}. Até lá! 😊")])
        if action == "cancelar":
            self._cancel(appt["id"])
            return self._save(msg.phone, {"state": "MENU"}, [
                Text("Agendamento cancelado. Obrigado por avisar!"),
                Buttons("Quer marcar outro horário?", MAIN_BUTTONS)])
        return self._ask_day(msg, appt["service"], reschedule_id=appt["id"])

    # ------------------------------------------------------------------ apoio
    def _slots(self, d: date, minutes: int) -> list[datetime]:
        start, end = day_bounds(d)
        return free_slots(d, minutes, self.calendar.busy(start, end), self.now())

    def _own_appointment(self, msg: Incoming) -> dict | None:
        if not msg.value.startswith("ag:"):
            return None
        appt = self.repo.get(int(msg.value.removeprefix("ag:")))
        return appt if appt and appt["phone"] == msg.phone else None

    def _cancel(self, appt_id: int) -> None:
        appt = self.repo.get(appt_id)
        self.repo.set_status(appt_id, "cancelado")
        if appt and appt.get("event_id"):
            self.calendar.delete_event(appt["event_id"])

    def _save(self, phone: str, session: dict, out: list[Outgoing]) -> list[Outgoing]:
        self.sessions.save(phone, session)
        return out
