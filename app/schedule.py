"""Regras da agenda: serviços, horário de funcionamento e cálculo de horários livres.

Tudo aqui é Python puro (sem banco, sem API), por isso é fácil de testar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
WEEKDAYS_FULL = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    minutes: int
    price: float


SERVICES = {
    s.id: s
    for s in [
        Service("avaliacao", "Avaliação", 30, 0),
        Service("limpeza", "Limpeza dental", 30, 150),
        Service("restauracao", "Restauração", 60, 220),
        Service("clareamento", "Clareamento", 60, 600),
    ]
}

# Horário de funcionamento por dia da semana (0 = segunda). Intervalos [início, fim).
OPENING_HOURS: dict[int, list[tuple[time, time]]] = {
    0: [(time(8), time(12)), (time(13, 30), time(18))],
    1: [(time(8), time(12)), (time(13, 30), time(18))],
    2: [(time(8), time(12)), (time(13, 30), time(18))],
    3: [(time(8), time(12)), (time(13, 30), time(18))],
    4: [(time(8), time(12)), (time(13, 30), time(17))],
    5: [(time(8), time(12))],
    # domingo fechado
}

SLOT_STEP = timedelta(minutes=30)     # de quanto em quanto tempo oferecer horários
MIN_NOTICE = timedelta(hours=2)       # antecedência mínima para agendar

Interval = tuple[datetime, datetime]


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def free_slots(day: date, minutes: int, busy: list[Interval], now: datetime,
               step: timedelta = SLOT_STEP, notice: timedelta = MIN_NOTICE) -> list[datetime]:
    """Horários de início livres em `day` para um serviço de `minutes` minutos.

    Um horário é livre quando o serviço inteiro cabe dentro do expediente e
    não se sobrepõe a nenhum intervalo ocupado.
    """
    duration = timedelta(minutes=minutes)
    earliest = now + notice
    result = []
    for start_t, end_t in OPENING_HOURS.get(day.weekday(), []):
        start = datetime.combine(day, start_t, TZ)
        end = datetime.combine(day, end_t, TZ)
        cur = start
        while cur + duration <= end:
            slot = (cur, cur + duration)
            if cur >= earliest and not any(overlaps(slot, b) for b in busy):
                result.append(cur)
            cur += step
    return result


def day_bounds(day: date) -> Interval:
    start = datetime.combine(day, time(0), TZ)
    return start, start + timedelta(days=1)


def format_day(d: date) -> str:
    """'ter 11/11'"""
    return f"{WEEKDAYS[d.weekday()]} {d:%d/%m}"


def format_when(dt: datetime) -> str:
    """'terça, 11/11 às 14:00'"""
    dt = dt.astimezone(TZ)
    return f"{WEEKDAYS_FULL[dt.weekday()]}, {dt:%d/%m} às {dt:%H:%M}"


def format_price(value: float) -> str:
    if not value:
        return "sem custo"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
