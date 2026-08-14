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
    # Форма в косвенном падеже: только такую есть смысл заменять леммой при
    # восстановлении. Форматные распознаватели падежей не знают - по умолчанию False.
    oblique: bool = False


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
# ОГРН (13) и ОГРНИП (15) - реквизиты юрлица, а не человека, но в выгрузке или акте
# проверки они однозначно называют организацию, из которой документ. Обезличивание,
# оставившее ОГРН, бессмысленно: номер пробивается в открытом реестре за секунды.
OGRN_RE = re.compile(r"(?<!\d)(?:\d{15}|\d{13})(?!\d)")
# УИД договора (Положение Банка России №758-П) - UUID, иногда с номером части через
# дефис. Сквозной идентификатор сделки: связывает записи между выгрузками и вместе с
# любым внешним источником выводит на конкретного заемщика.
#
# Под тот же шаблон попадает и обычный технический UUID (идентификатор запроса в логе).
# Считаем это приемлемым: для модели такой токен смысла не несет, и лишняя маска
# на нем текст не портит - в отличие от маски на названии инструмента или должности.
#
# Между группами допускается перенос строки: в колоночной верстке (акт, выгрузка
# в PDF) УИД разрывается ровно по дефису, и на первом же прогоне так уехало 780 из
# 1079 вхождений - то есть строгий шаблон пропускал большинство. Один перенос,
# не больше: иначе шаблон начнет склеивать соседние колонки таблицы.
_WRAP = r"[ \t]*\n?[ \t]*"
# Последняя группа необязательна. В колоночной верстке хвост УИД не просто
# переносится на следующую строку - он вообще теряет соседство с головой (pdftotext
# уводит его в другое место страницы). На реальном акте так выглядели 978 вхождений
# из 1079: четыре группы, дефис и обрыв. Голова из 20 шестнадцатеричных знаков
# идентифицирует запись ничуть не хуже целого УИД, поэтому маскируем и ее.
UID_RE = re.compile(
    rf"(?<![\w-])[0-9a-f]{{8}}(?:-{_WRAP}[0-9a-f]{{4}}){{1,3}}"
    rf"(?:-{_WRAP}[0-9a-f]{{12}}(?:-\d{{1,3}})?)?-?(?![\w])",
    re.IGNORECASE,
)

# --- ФИО в формах, которые NER не берет ---
#
# NER обучен на новостях, а в них ФИО пишут обычным регистром. В реестрах, выгрузках
# и таблицах официальных документов они идут КАПСОМ - и распознавание падает почти в
# ноль (замер на акте проверки: из 55 полных ФИО капсом поймано 6). Поэтому такие
# формы ловятся отдельно, регулярками, и работают в том числе с --no-ner.
#
# Якорь везде один - отчество: суффикс отчества дает уверенность, которой нет у пары
# заглавных слов самой по себе ("АКТ ПРОВЕРКИ" - тоже два слова капсом).
_CAPS_WORD = r"[А-ЯЁ]{2,}(?:-[А-ЯЁ]{2,})?"
# Голое "ИЧ" в набор не берем: под него попадают обычные слова капсом (КИРПИЧ,
# ПАРАЛИЧ). Редкие формы вроде "ИЛЬИЧ" закрыты вариантом ЬИЧ.
_PATR_TAIL = r"(?:ОВИЧ|ЕВИЧ|ЬИЧ|ОВНА|ЕВНА|ИЧНА)"
# Полное ФИО капсом: два-три слова, одно из которых - отчество (порядок любой,
# в реестрах встречается и "ФАМИЛИЯ ИМЯ ОТЧЕСТВО", и "ИМЯ ОТЧЕСТВО ФАМИЛИЯ").
# Только в пределах строки: спан через перенос разрезал бы верстку таблицы, а
# оторвавшийся хвост добирается правилом ниже.
_CAPS_PATR = rf"[А-ЯЁ]{{3,}}{_PATR_TAIL}"
CAPS_FIO_RE = re.compile(
    rf"(?<![А-ЯЁ\w])(?:"
    rf"{_CAPS_WORD}[ \t]+{_CAPS_WORD}[ \t]+{_CAPS_PATR}"   # ФАМИЛИЯ ИМЯ ОТЧЕСТВО
    rf"|{_CAPS_WORD}[ \t]+{_CAPS_PATR}[ \t]+{_CAPS_WORD}"  # ИМЯ ОТЧЕСТВО ФАМИЛИЯ
    rf"|{_CAPS_WORD}[ \t]+{_CAPS_PATR}"                    # ИМЯ ОТЧЕСТВО
    rf")(?![А-ЯЁ\w])"
)
# Одинокое отчество капсом. В колоночной верстке ФИО переносится по словам, и хвост
# оказывается в отдельной строке; оставить его - оставить часть имени.
CAPS_PATR_RE = re.compile(rf"(?<![А-ЯЁ\w])[А-ЯЁ]{{3,}}{_PATR_TAIL}(?![А-ЯЁ\w])")
# "Фамилия И.О." и "И.О. Фамилия" - основная форма подписи в служебных документах.
# NER их тоже пропускает: инициалы с точками рвут сегментацию.
_SURNAME = r"(?:[А-ЯЁ][а-яё]{2,}|[А-ЯЁ]{3,})"
INITIALS_RE = re.compile(
    rf"(?<![А-ЯЁ\w]){_SURNAME}[ \t]+[А-ЯЁ]\.[ \t]?[А-ЯЁ]\.(?!\w)"
    rf"|(?<![А-ЯЁ\w])[А-ЯЁ]\.[ \t]?[А-ЯЁ]\.[ \t]?{_SURNAME}(?![А-ЯЁ\w])"
)

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


def ogrn_ok(num: str) -> bool:
    """Контрольный разряд ОГРН: остаток от деления числа без последнего разряда
    на 11 (для ОГРНИП - на 13), взятый по модулю 10."""
    if len(num) == 13:
        return int(num[:12]) % 11 % 10 == int(num[12])
    if len(num) == 15:
        return int(num[:14]) % 13 % 10 == int(num[14])
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

    for m in OGRN_RE.finditer(text):
        d = m.group()
        if ogrn_ok(d):
            out.append(Entity("OGRN", d, m.start(), m.end(), d))

    for m in UID_RE.finditer(text):
        out.append(Entity("UID", m.group(), m.start(), m.end(), m.group().lower()))

    for m in PASSPORT_RE.finditer(text):
        window = text[max(0, m.start() - 40):m.start()]
        if PASSPORT_CTX_RE.search(window):
            out.append(Entity("PASSPORT", m.group(), m.start(), m.end(), digits(m.group())))

    # Полная форма имеет приоритет над одиноким отчеством: отчество внутри уже
    # найденного ФИО отдельной сущностью не выдаем, иначе на выходе два кандидата
    # на один и тот же кусок текста.
    named: list[tuple[int, int]] = []
    for rx in (CAPS_FIO_RE, INITIALS_RE):
        for m in rx.finditer(text):
            named.append((m.start(), m.end()))
            out.append(Entity("PERSON", m.group(), m.start(), m.end(),
                              " ".join(m.group().lower().split())))
    for m in CAPS_PATR_RE.finditer(text):
        if any(s <= m.start() and m.end() <= e for s, e in named):
            continue
        out.append(Entity("PERSON", m.group(), m.start(), m.end(), m.group().lower()))

    return out
