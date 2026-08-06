"""Форматные ПД РФ: regex + контрольные суммы. Валидатор обязателен - без него
любой длинный номер в тексте превращается в ложное срабатывание."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Entity:
    type: str
    text: str
    start: int
    end: int
    key: str  # ключ консистентности: одинаковый key -> одна метка


# Наши собственные фейки не должны маскироваться повторно
FAKE_PHONE_CODE = "000"
FAKE_EMAIL_RE = re.compile(r"^user\d+@example\.com$", re.IGNORECASE)

PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8)[ \-]?\(?\d{3}\)?[ \-]?\d{3}[ \-]?\d{2}[ \-]?\d{2}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TG_RE = re.compile(r"(?<![\w.\-@])@[A-Za-z][A-Za-z0-9_]{4,31}\b")
CARD_RE = re.compile(r"(?<!\d)(?:\d{4}[ \-]?){3}\d{4}(?!\d)")
INN_RE = re.compile(r"(?<!\d)(?:\d{12}|\d{10})(?!\d)")
SNILS_RE = re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}[ \-]?\d{2}(?!\d)")
PASSPORT_RE = re.compile(r"(?<!\d)\d{4} \d{6}(?!\d)")
PASSPORT_CTX_RE = re.compile(r"паспорт\w*|сери[ия]\w*", re.IGNORECASE)

# Сайт компании - такой же идентификатор, как ее название: метка {{ORG_1}} рядом
# с живым доменом работодателя бессмысленна.
URL_SCHEME_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+", re.IGNORECASE)
# Голый домен - только с www. или с делового домена верхнего уровня. Списка вида
# "любой TLD" тут быть не может: ".md" и ".py" - это Молдова и Парагвай, и под
# них попали бы имена файлов вроде core.py и README.md.
BARE_DOMAIN_RE = re.compile(
    r"(?<![@\w./-])(?:www\.[a-z0-9-]+(?:\.[a-z0-9-]+)*"
    r"|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:ru|com|org|net|io|co|biz|info|рф))"
    r"(?![\w@])(?:/[^\s<>\"'`)\]}]*)?",
    re.IGNORECASE,
)
# Технические ссылки персданными не являются - маскировать их значит портить текст.
STOP_HOSTS = frozenset({
    "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
    "python.org", "docs.python.org", "wikipedia.org", "ru.wikipedia.org",
    "habr.com", "example.com", "example.org", "example.net",
})


def _url_host(url: str) -> str:
    host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/")[0]
    return host.lower().removeprefix("www.")


def digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def luhn_ok(num: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(num)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def inn_ok(num: str) -> bool:
    def ctrl(digs: str, koef: list[int]) -> int:
        return sum(int(d) * k for d, k in zip(digs, koef)) % 11 % 10

    if len(num) == 10:
        return ctrl(num[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(num[9])
    if len(num) == 12:
        k11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        k12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return ctrl(num[:10], k11) == int(num[10]) and ctrl(num[:11], k12) == int(num[11])
    return False


def snils_ok(num: str) -> bool:
    if len(num) != 11:
        return False
    body, chk = num[:9], int(num[9:])
    s = sum(int(body[i]) * (9 - i) for i in range(9))
    if s < 100:
        expected = s
    elif s in (100, 101):
        expected = 0
    else:
        expected = s % 101
        if expected == 100:
            expected = 0
    return chk == expected


def find_format_entities(text: str) -> list[Entity]:
    out: list[Entity] = []

    for m in EMAIL_RE.finditer(text):
        if not FAKE_EMAIL_RE.match(m.group()):
            out.append(Entity("EMAIL", m.group(), m.start(), m.end(), m.group().lower()))

    for m in TG_RE.finditer(text):
        out.append(Entity("TG", m.group(), m.start(), m.end(), m.group().lower()))

    for rx in (URL_SCHEME_RE, BARE_DOMAIN_RE):
        for m in rx.finditer(text):
            url = m.group().rstrip(".,;:!?")
            if _url_host(url) in STOP_HOSTS:
                continue
            out.append(Entity("URL", url, m.start(), m.start() + len(url), url.lower()))

    for m in PHONE_RE.finditer(text):
        d = digits(m.group())
        if d[1:4] != FAKE_PHONE_CODE:
            out.append(Entity("PHONE", m.group(), m.start(), m.end(), d))

    for m in CARD_RE.finditer(text):
        d = digits(m.group())
        if len(d) == 16 and luhn_ok(d):
            out.append(Entity("CARD", m.group(), m.start(), m.end(), d))

    for m in SNILS_RE.finditer(text):
        d = digits(m.group())
        if snils_ok(d):
            out.append(Entity("SNILS", m.group(), m.start(), m.end(), d))

    for m in INN_RE.finditer(text):
        d = m.group()
        if inn_ok(d):
            out.append(Entity("INN", d, m.start(), m.end(), d))

    for m in PASSPORT_RE.finditer(text):
        window = text[max(0, m.start() - 40):m.start()]
        if PASSPORT_CTX_RE.search(window):
            out.append(Entity("PASSPORT", m.group(), m.start(), m.end(), digits(m.group())))

    return out
