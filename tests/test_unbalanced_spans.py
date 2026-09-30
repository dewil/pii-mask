"""Маска не захватывает незакрытую скобку и кавычку.

Живые резюме (30.09.2026) дали спаны вида 'окб, нбки)', 'бц "белые сады',
'ооо мобильные игровые решения)', 'газпром - "(ип)'. Название внутри найдено
верно, а лишний знак на краю утаскивает в маску кусок соседней фразы и оставляет
в тексте висящую половину пары - читателю кажется, что документ побит.
"""
import pytest

from pii_mask.core import Masker


def masked(text, **kw):
    return Masker(types=("ORG",), ner_org_needs_form=False, **kw).mask(text)[0]


@pytest.mark.parametrize("текст, хвост", [
    ('Работал в ООО "Мобильные игровые решения), потом ушел.', ")"),
    ('Проекты: ООО "Светопись), сдача в срок.', ")"),
])
def test_trailing_bracket_stays_in_the_text(текст, хвост):
    out = masked(текст)
    assert хвост in out, "непарная скобка утащена в маску"


def test_opening_quote_without_a_pair_is_not_swallowed():
    out = masked('Объекты: БЦ "Белые сады и соседние здания.')
    # Кавычка осталась в тексте: пара для нее в документе не нашлась.
    assert '"' in out


def test_balanced_name_is_masked_whole():
    """Проверка не должна мешать обычному случаю."""
    out = masked('Работал в ООО "Светопись" два года.')
    assert "Светопись" not in out and '""' not in out


def test_name_itself_still_masked_when_the_edge_is_trimmed():
    out = masked('Работал в ООО "Светопись), потом ушел.')
    assert "Светопись" not in out


def test_span_grows_to_the_closing_quote():
    """Название целиком, а не до половины.

    Спан вида 'БЦ "Белые сады' обрывается посреди названия: закрывающая кавычка
    стоит сразу за краем. Расширить до нее лучше, чем срезать, - иначе в тексте
    остается висеть одинокая кавычка и половина имени.
    """
    out = masked('Объекты: ТРЦ "Заречье" 330 тыс. м², БЦ "Белые сады" (класс А).')
    assert "Заречье" not in out and "Белые сады" not in out
    assert '"' not in out, "кавычка от названия осталась в тексте"


def test_generic_property_abbreviations_are_not_organisations():
    """ТПУ, ЖК, ОЦ в перечне объектов - тип здания, а не его имя."""
    out = masked("Масштаб: группа объектов - ОЦ, ТПУ, ЖК и другие; 248 инженеров.")
    assert "ОЦ" in out and "ТПУ" in out and "ЖК" in out


def test_registry_shows_what_was_actually_masked():
    """Реестр замен - ключ к документу, и он обязан совпадать с маской.

    Обрезка правит текст спана; если ключ остается прежним, реестр показывает
    то, чего в маске нет, и разворот по нему даст не тот текст.
    """
    текст = 'Работал в ООО "Светопись), потом ушел.'
    out, mapping = Masker(types=("ORG",), ner_org_needs_form=False).mask(текст)
    ключи = [r["key"] for r in mapping["labels"].values()]
    assert all(")" not in k for k in ключи), ключи
