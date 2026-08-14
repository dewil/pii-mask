"""Regex-распознаватели: форматные ПД РФ. Валидаторы контрольных сумм обязаны отсекать мусор."""
import pytest

from pii_mask.recognizers import find_format_entities


def types_of(text, wanted=None):
    ents = find_format_entities(text)
    if wanted:
        ents = [e for e in ents if e.type == wanted]
    return ents


# --- helpers: генерация валидных номеров ---

def make_inn10(base9: str) -> str:
    k = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    d = [int(c) for c in base9]
    return base9 + str(sum(a * b for a, b in zip(k, d)) % 11 % 10)


def make_snils(base9: str) -> str:
    d = [int(c) for c in base9]
    s = sum(d[i] * (9 - i) for i in range(9))
    if s < 100:
        chk = s
    elif s in (100, 101):
        chk = 0
    else:
        chk = s % 101
        if chk == 100:
            chk = 0
    return f"{base9[0:3]}-{base9[3:6]}-{base9[6:9]} {chk:02d}"


# --- PHONE ---

@pytest.mark.parametrize("raw", [
    "+7 903 123-45-67",
    "8 (903) 123-45-67",
    "89031234567",
    "+7-903-123-45-67",
    "8 903 123 45 67",
])
def test_phone_formats(raw):
    ents = types_of(f"позвони {raw} завтра", "PHONE")
    assert len(ents) == 1
    assert ents[0].text == raw


def test_phone_not_in_long_number():
    # 12+ цифр подряд - не телефон (например, счет)
    assert types_of("счет 407028103800001234567", "PHONE") == []


def test_phone_fake_range_not_rematched():
    # наш собственный фейковый диапазон +7 000 ... не должен маскироваться повторно
    assert types_of("тел +7 000 000-00-01", "PHONE") == []


# --- EMAIL / TG ---

def test_email():
    ents = types_of("пиши на ivan.petrov@company.example или в чат", "EMAIL")
    assert [e.text for e in ents] == ["ivan.petrov@company.example"]


def test_tg_handle():
    ents = types_of("мой ник @ivan_petrov77 в телеге", "TG")
    assert [e.text for e in ents] == ["@ivan_petrov77"]


def test_email_not_double_matched_as_tg():
    ents = find_format_entities("адрес ivan@example.org")
    assert {e.type for e in ents} == {"EMAIL"}


# --- INN ---

def test_inn10_valid():
    inn = make_inn10("770708389")
    ents = types_of(f"ИНН {inn}", "INN")
    assert [e.text for e in ents] == [inn]


def test_inn10_bad_checksum():
    inn = make_inn10("770708389")
    bad = inn[:-1] + str((int(inn[-1]) + 1) % 10)
    assert types_of(f"ИНН {bad}", "INN") == []


# --- SNILS ---

def test_snils_valid():
    sn = make_snils("112233445")
    ents = types_of(f"СНИЛС {sn}", "SNILS")
    assert [e.text for e in ents] == [sn]


def test_snils_bad_checksum():
    sn = make_snils("112233445")
    bad = sn[:-2] + f"{(int(sn[-2:]) + 1) % 100:02d}"
    assert types_of(f"СНИЛС {bad}", "SNILS") == []


# --- CARD (Луна) ---

def test_card_valid_luhn():
    ents = types_of("карта 4111 1111 1111 1111 для оплаты", "CARD")
    assert [e.text for e in ents] == ["4111 1111 1111 1111"]


def test_card_bad_luhn():
    assert types_of("номер 4111 1111 1111 1112", "CARD") == []


# --- PASSPORT (только с контекстным словом) ---

def test_passport_with_context():
    ents = types_of("паспорт 4509 123456 выдан ОВД", "PASSPORT")
    assert [e.text for e in ents] == ["4509 123456"]


def test_passport_without_context():
    # без слова-триггера пара чисел - не паспорт (иначе FP на любой статистике)
    assert types_of("выпустили 4509 123456 единиц", "PASSPORT") == []


# --- URL / домен ---

def test_url_employer_domain_masked():
    """Сайт компании - такой же идентификатор, как ее название."""
    ents = types_of("Северный Торговый Банк, Москва, www.severbank-example.ru", "URL")
    assert [e.text for e in ents] == ["www.severbank-example.ru"]


def test_url_with_scheme_and_path():
    ents = types_of("Сайт https://severbank-example.ru/about устарел", "URL")
    assert [e.text for e in ents] == ["https://severbank-example.ru/about"]


def test_url_skips_technical_hosts():
    """Ссылка на репозиторий или документацию - не персданные, портить текст незачем."""
    src = "Код в github.com/dewil/pii-mask, справка docs.python.org/3/library/re.html"
    assert types_of(src, "URL") == []


def test_url_does_not_eat_filenames():
    """Молдова и Парагвай владеют доменами .md и .py - имена файлов под них не отдаем."""
    assert types_of("Правь core.py и README.md, смотри tests/test_api.py", "URL") == []


def test_url_does_not_swallow_email():
    ents = find_format_entities("почта hr@severbank-example.ru")
    assert [(e.type, e.text) for e in ents if e.type == "EMAIL"] == [
        ("EMAIL", "hr@severbank-example.ru")
    ]


# --- ОГРН / ОГРНИП ---

def make_ogrn13(base12: str) -> str:
    return base12 + str(int(base12) % 11 % 10)


def make_ogrn15(base14: str) -> str:
    return base14 + str(int(base14) % 13 % 10)


def test_ogrn13_valid():
    ogrn = make_ogrn13("102770006732")
    assert [e.text for e in types_of(f"ОГРН {ogrn}", "OGRN")] == [ogrn]


def test_ogrn13_bad_checksum():
    ogrn = make_ogrn13("102770006732")
    bad = ogrn[:-1] + str((int(ogrn[-1]) + 1) % 10)
    assert types_of(f"ОГРН {bad}", "OGRN") == []


def test_ogrnip15_valid():
    ogrnip = make_ogrn15("30477050030001")
    assert [e.text for e in types_of(f"ОГРНИП {ogrnip}", "OGRN")] == [ogrnip]


def test_ogrn_not_confused_with_inn():
    """Границы по цифрам разводят типы: 13 знаков - не ИНН, 10 - не ОГРН."""
    ogrn = make_ogrn13("102770006732")
    assert types_of(f"реквизит {ogrn}", "INN") == []


# --- УИД договора (758-П) ---

def test_uid_uuid():
    uid = "3f2a9c14-5b6d-4e71-9a02-7c8de1f04b95"
    assert [e.text for e in types_of(f"УИД {uid} по договору", "UID")] == [uid]


def test_uid_with_part_number():
    uid = "3f2a9c14-5b6d-4e71-9a02-7c8de1f04b95-1"
    assert [e.text for e in types_of(f"запись {uid}", "UID")] == [uid]


def test_uid_needs_full_shape():
    """Обрывок хеша - не УИД: иначе маска ляжет на любой технический идентификатор."""
    assert types_of("хвост 09f4feeaa721-0 в колонке", "UID") == []


# --- ФИО капсом и инициалами (NER их не берет) ---

def test_caps_fio_full():
    ents = types_of("субъект ИВАНОВ ПЕТР СЕРГЕЕВИЧ включен в выборку", "PERSON")
    assert [e.text for e in ents] == ["ИВАНОВ ПЕТР СЕРГЕЕВИЧ"]


def test_caps_fio_name_first():
    ents = types_of("от ПЕТР СЕРГЕЕВИЧ ИВАНОВ поступило", "PERSON")
    assert [e.text for e in ents] == ["ПЕТР СЕРГЕЕВИЧ ИВАНОВ"]


def test_caps_fio_without_surname():
    ents = types_of("указан ПЕТР СЕРГЕЕВИЧ в графе", "PERSON")
    assert [e.text for e in ents] == ["ПЕТР СЕРГЕЕВИЧ"]


def test_caps_patronymic_alone_is_masked():
    """Колоночная верстка переносит ФИО по словам - хвост нельзя оставлять в тексте."""
    ents = types_of("ИВАНОВ ПЕТР\nСЕРГЕЕВИЧ", "PERSON")
    assert "СЕРГЕЕВИЧ" in [e.text for e in ents]


def test_caps_fio_not_glued_across_lines():
    """Спан через перенос разрезал бы верстку таблицы: ловим построчно."""
    ents = types_of("ИВАНОВ ПЕТР\nСЕРГЕЕВИЧ", "PERSON")
    assert all("\n" not in e.text for e in ents)


def test_caps_heading_is_not_a_name():
    assert types_of("АКТ ПРОВЕРКИ ПО ОТДЕЛЬНОМУ ВОПРОСУ", "PERSON") == []


def test_caps_common_word_with_ich_is_not_patronymic():
    """Голое 'ИЧ' в набор суффиксов не входит - иначе КИРПИЧ становится персоной."""
    assert types_of("материал КИРПИЧ на складе", "PERSON") == []


def test_surname_with_initials():
    ents = types_of("Руководитель рабочей группы Страхова М.Е.", "PERSON")
    assert [e.text for e in ents] == ["Страхова М.Е."]


def test_initials_before_surname():
    ents = types_of("подписал М.Е. Страхова лично", "PERSON")
    assert [e.text for e in ents] == ["М.Е. Страхова"]


def test_caps_surname_with_initials():
    ents = types_of("СТРАХОВА М.Е.", "PERSON")
    assert [e.text for e in ents] == ["СТРАХОВА М.Е."]


def test_uid_wrapped_across_lines():
    """В колоночной верстке УИД рвется по дефису - строгий шаблон пропускал большинство."""
    src = "договор 3f2a9c14-5b6d-4e71-9a02-\n   7c8de1f04b95 в реестре"
    ents = types_of(src, "UID")
    assert len(ents) == 1 and ents[0].text.startswith("3f2a9c14")


def test_uid_head_without_tail():
    """Верстка теряет хвост УИД - голова из 20 знаков идентифицирует запись не хуже."""
    ents = types_of("в графе 3f2a9c14-5b6d-4e71-9a02-\nследующая строка", "UID")
    assert [e.text for e in ents] == ["3f2a9c14-5b6d-4e71-9a02-"]


def test_uid_does_not_eat_date_range():
    assert types_of("период 2019-2024 годы, бюджет 200-250", "UID") == []
