"""Должность за названием работодателя не должна уезжать под маску.

Повод: 19.08.2026 на прогоне диагностики строка "Северная Торговая Компания - логист"
ушла в облако как "{{ORG_1}}." - NER разметил организацией весь спан вместе с
должностью. Ущерб не в утечке, а наоборот: из текста пропала роль, и модель заявила,
что должность не указана. Это ровно тот класс выдуманных утверждений, ради которого
ведется журнал замеров качества разбора.

Граница приема: режем только хвост после тире В ПРОБЕЛАХ и только если он начинается
со строчной буквы. Составные названия пишутся через дефис без пробелов ("Альфа-Банк"),
части настоящего названия - с прописной ("Технопарк - Мордовия").
"""
from pii_mask.core import Masker
from pii_mask.ner import _role_tail_len


def _mask(text: str, **kw) -> tuple[str, dict]:
    out, mapping = Masker(**kw).mask(text)
    return out, mapping


class TestRoleTailRegex:
    """Чистая функция - без загрузки моделей NER."""

    def test_cuts_lowercase_tail(self):
        assert _role_tail_len("Северная Торговая Компания - логист") == len(" - логист")

    def test_keeps_capitalized_tail(self):
        """Прописная после тире - это часть названия, а не должность."""
        assert _role_tail_len("Технопарк - Мордовия") == 0

    def test_keeps_hyphen_without_spaces(self):
        assert _role_tail_len("Альфа-Банк") == 0

    def test_cuts_after_en_dash(self):
        assert _role_tail_len("Ромашка — ведущий аналитик") == len(" — ведущий аналитик")

    def test_cuts_multiword_tail(self):
        assert _role_tail_len("Ромашка - руководитель проектов") == len(" - руководитель проектов")

    def test_does_not_cross_newline(self):
        assert _role_tail_len("Ромашка - логист\nследующая строка") == 0


class TestRoleTailInMask:
    def test_role_stays_in_text(self):
        out, _ = _mask("2012-2014, Северная Торговая Компания - логист.")
        assert "логист" in out
        assert "Торговая" not in out

    def test_mapping_holds_name_without_role(self):
        _, mapping = _mask("2012-2014, Северная Торговая Компания - логист.")
        originals = [v["original"] for v in mapping["labels"].values()]
        assert "Северная Торговая Компания" in originals
