"""Словарное название ищется целиком, а не по отдельным словам.

Повод: 19.08.2026, разбор словарей организаций по кейсам. Механизм словаря был
рассчитан на разнос названия по документу отдельными словами - он узнает название
в изуродованной верстке, но у него нашлись три побочки, и все три молчаливые:

  "Спортмастер Россия" давала ДВЕ метки вместо одной (отдельно "Спортмастер",
  отдельно "Россия"), и модель видела двух работодателей вместо одного;

  записи без слов с заглавной буквы ("факультет гуманитарных наук") и короче трех
  символов ("VK") не срабатывали ВООБЩЕ - их отсеивала эвристика выделения стемов;

  на пересечении выигрывал NER: "Спортмастер Россия" уходила как {{PERSON_1}},
  потому что PERSON приоритетнее ORG по типу, а источник не учитывался.
"""
from pii_mask.core import Masker


def _mask(text: str, names: tuple[str, ...]) -> tuple[str, dict]:
    return Masker(org_names=names, ner=False).mask(text)


def _originals(mapping: dict) -> list[str]:
    return [v["original"] for v in mapping["labels"].values()]


class TestPhraseKeptWhole:
    def test_multiword_name_gives_one_label(self):
        out, mapping = _mask(
            "2019-2024, руководитель, Спортмастер Россия, Москва.", ("Спортмастер Россия",)
        )
        assert out.count("{{ORG_") == 1
        assert _originals(mapping) == ["Спортмастер Россия"]

    def test_same_name_twice_gets_same_label(self):
        """Ключ у обоих вхождений один, иначе unmask разведет их по разным меткам."""
        out, _ = _mask(
            "Спортмастер Россия, Москва. Позже снова Спортмастер Россия.",
            ("Спортмастер Россия",),
        )
        assert out.count("{{ORG_1}}") == 2
        assert "{{ORG_2}}" not in out


class TestEntriesThatUsedToBeIgnored:
    def test_lowercase_entry_works(self):
        """Ни одного слова с заглавной - раньше стемов не было вовсе."""
        out, mapping = _mask(
            "Отвечал за факультет гуманитарных наук как заказчика.",
            ("факультет гуманитарных наук",),
        )
        assert "{{ORG_1}}" in out
        assert _originals(mapping) == ["факультет гуманитарных наук"]

    def test_two_letter_entry_works(self):
        out, _ = _mask("Внедрял VK ID в продукт.", ("VK",))
        assert "{{ORG_1}} ID" in out


class TestBoundaries:
    def test_does_not_eat_part_of_a_word(self):
        out, _ = _mask("Внедрял MTV-подобные форматы.", ("MTV",))
        assert "MTV-подобные" in out

    def test_common_word_outside_the_name_survives(self):
        """'Россия' в составе названия маскируется, отдельное 'России' - нет."""
        out, _ = _mask(
            "Опыт работы в России, Спортмастер Россия - логист.", ("Спортмастер Россия",)
        )
        assert "в России," in out
        assert "{{ORG_1}} - логист" in out


class TestDictionaryBeatsGuesswork:
    def test_dict_entity_wins_overlap(self):
        """Словарь назвал человек - он побеждает эвристику, даже более приоритетную.

        Проверяем не через NER (он требует моделей и медленный), а напрямую: спан
        того же участка, объявленный персоной, не должен вытеснять словарное ORG.
        """
        from pii_mask.recognizers import Entity

        text = "Коллега Спортмастер Россия отвечал за логистику."
        start = text.index("Спортмастер Россия")
        fake_person = Entity(
            "PERSON", "Спортмастер Россия", start, start + len("Спортмастер Россия"),
            "спортмастер россия",
        )
        out, mapping = Masker(org_names=("Спортмастер Россия",), ner=False).mask(
            text, extra_entities=[fake_person]
        )
        assert "{{ORG_1}}" in out
        assert "PERSON" not in out
