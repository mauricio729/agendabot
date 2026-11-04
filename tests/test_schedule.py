from datetime import date, datetime, timedelta

from app.reminders import reminder_time
from app.schedule import TZ, format_price, free_slots

# 10/11/2026 é uma terça-feira
TUESDAY = date(2026, 11, 10)
SUNDAY = date(2026, 11, 8)
EARLY = datetime(2026, 11, 1, 9, 0, tzinfo=TZ)


def at(h, m=0, d=TUESDAY):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)


def test_dia_livre_respeita_expediente_e_almoco():
    slots = free_slots(TUESDAY, 30, [], EARLY)
    hours = [f"{s:%H:%M}" for s in slots]
    assert hours[0] == "08:00" and hours[-1] == "17:30"
    assert "11:30" in hours and "12:00" not in hours and "13:00" not in hours and "13:30" in hours


def test_servico_longo_precisa_caber_inteiro():
    hours = [f"{s:%H:%M}" for s in free_slots(TUESDAY, 60, [], EARLY)]
    assert "11:00" in hours and "11:30" not in hours  # 11:30 + 60min passaria do almoço
    assert hours[-1] == "17:00"


def test_horario_ocupado_e_sobreposicao():
    busy = [(at(9), at(10))]
    hours = [f"{s:%H:%M}" for s in free_slots(TUESDAY, 60, busy, EARLY)]
    assert "08:00" in hours and "08:30" not in hours and "09:00" not in hours and "09:30" not in hours
    assert "10:00" in hours


def test_domingo_fechado():
    assert free_slots(SUNDAY, 30, [], EARLY) == []


def test_antecedencia_minima_de_2h():
    now = at(10, 15)
    hours = [f"{s:%H:%M}" for s in free_slots(TUESDAY, 30, [], now)]
    assert hours[0] == "13:30"  # 12:15 em diante, mas 12:00–13:30 é almoço


def test_lembrete_24h_antes():
    start = at(14)
    assert reminder_time(start, EARLY) == start - timedelta(hours=24)
    assert reminder_time(start, at(10)) is None  # faltam menos de 24h


def test_formato_preco():
    assert format_price(1500) == "R$ 1.500,00"
    assert format_price(0) == "sem custo"
