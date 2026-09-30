"""INV-MASK-05, INV-MASK-06: имя закрывается независимо от алфавита и верстки.

Прогон 45 живых резюме (01.10.2026): в девяти шапка с именем владельца написана
латиницей и осталась открытой целиком, при том что русское ФИО в тех же файлах
закрывалось. Документ выглядит обезличенным - метки в нем есть, - а человек
назван в первой строке.

Формы имен взяты из той выборки и заменены на однотипные вымышленные: русская,
украинская, армянская, тюркская транслитерация плюс западное имя.
"""
import pytest

from pii_mask.core import Masker


def mask(text, **kw):
    return Masker(types=("PERSON",), ner_person_needs_fio=True, **kw).mask(text)[0]


ШАПКА = "{имя}\nSenior Project Manager\nMoscow, Russia\n\nSummary\nPython, SQL.\n"


@pytest.mark.parametrize("имя", [
    "Ivan Safonov",
    "Anna Pereverzeva",
    "Maksim Kravets",
    "Azamat Kenesbekov",
    "Zhamilya Khairullina",
    "Lyudvig Asoyan",
    "Petr Gorbunov",
    "Olga Zaretskaya",
    "Dmitry Kovalenko",
])
def test_latin_full_name_in_the_header_is_masked(имя):
    out = mask(ШАПКА.format(имя=имя))
    assert имя not in out, "имя латиницей осталось открытым"


@pytest.mark.parametrize("пара", [
    "Project Manager", "Risk Management", "Business Process", "Product Owner",
    "Distributed Systems", "Journey Mapping", "Senior Frontend", "Clean Architecture",
    "Machine Learning", "Data Engineer",
])
def test_job_titles_are_not_names(пара):
    """В англоязычном резюме таких пар сотни - их маскировать нельзя."""
    текст = f"Ivan Safonov\n{пара}\nMoscow\n\nSummary\nОпыт работы с данными.\n"
    out = mask(текст)
    assert пара in out, "должность принята за имя"
    assert "Ivan Safonov" not in out, "имя не закрыто"


def test_city_is_not_a_name():
    out = mask("Anna Pereverzeva\nSoftware Developer\nLos Angeles, USA\n")
    assert "Los Angeles" in out


def test_latin_name_is_masked_consistently_across_the_document():
    """Имя встречается и в шапке, и в подписи - закрыто в обоих местах."""
    текст = ("Ivan Safonov\nSenior Developer\n\nSummary\nОпыт с данными.\n\n"
             "Рекомендации предоставит Ivan Safonov по запросу.\n")
    out = mask(текст)
    assert "Ivan Safonov" not in out


@pytest.mark.parametrize("пара", [
    "Google Sheets",          # известный термин плюс слово на -ets
    "Atlassian Jira",         # -ian плюс термин
    "Kotlin Coroutines",      # -in
    "Languages Russian",      # строка "Languages" в резюме
    "English Russian",
    "Nazarbayev University",  # имя носит организация, а не человек
    "Lebedev Physical",
    "Ukrainian Fund",
    "Cabin Monitoring",
])
def test_technical_and_organisation_pairs_are_not_people(пара):
    """Ложные маски первой версии правила, снятые на живой выборке 01.10.2026.

    Суффикс фамилии у соседнего слова тут настоящий, поэтому одного суффикса
    мало: термин проверяется пословно, а организационное слово рядом
    ("University", "Fund") означает, что имя носит не человек.
    """
    текст = f"Ivan Safonov\nSenior Developer\n\nSkills: {пара}, SQL.\n"
    out = mask(текст)
    assert пара in out, "не имя человека, а маска стоит"
    assert "Ivan Safonov" not in out, "настоящее имя при этом должно быть закрыто"
