"""Converse com o AgendaBot pelo terminal, sem WhatsApp e sem Google.

    python -m app.simulator

Digite o número da opção ou o título para "clicar" em botões e listas.
Comandos: `lembrete` simula o envio do lembrete do próximo agendamento,
`sair` fecha o simulador.
"""
from datetime import datetime

from .bot import AgendaBot
from .calendar_provider import LocalCalendar
from .messages import Buttons, Incoming, ListMenu, Template
from .reminders import MemoryReminders
from .schedule import SERVICES, TZ, format_when
from .sessions import MemorySessionStore
from .storage import AppointmentRepository
from .whatsapp import match_option, render

PHONE = "5534999999999"


def main() -> None:
    repo = AppointmentRepository(":memory:")
    reminders = MemoryReminders()
    bot = AgendaBot(MemorySessionStore(), repo, LocalCalendar(repo), reminders)
    last: list[tuple] = []

    print("AgendaBot · simulador (digite 'sair' para fechar)\n")
    while True:
        try:
            text = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() == "sair":
            break
        if text.lower() == "lembrete":
            upcoming = repo.upcoming_for(PHONE, datetime.now(TZ))
            if not upcoming:
                print("(nenhum agendamento para lembrar)\n")
                continue
            a = upcoming[0]
            tpl = Template("lembrete_consulta", params=["Cliente", SERVICES[a["service"]].name,
                                                        bot.clinic, format_when(a["start"])])
            print(f"\nbot ›  {render(tpl)}\n[Confirmar]  [Remarcar]  [Cancelar]\n")
            last = [("confirmar", "Confirmar"), ("remarcar", "Remarcar"), ("cancelar", "Cancelar")]
            continue

        reply_id = match_option(text, last) if last else None
        for out in bot.handle(Incoming(PHONE, text=text, reply_id=reply_id or "", name="Cliente Teste")):
            print(f"\nbot ›  {render(out)}\n")
            if isinstance(out, Buttons):
                last = out.buttons
            elif isinstance(out, ListMenu):
                last = [(rid, title) for rid, title, _ in out.rows]
            else:
                last = []
        if reminders.scheduled:
            appt_id, when = reminders.scheduled.pop()
            print(f"(lembrete do agendamento #{appt_id} programado para {when:%d/%m %H:%M})\n")


if __name__ == "__main__":
    main()
