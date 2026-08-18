"""Название работодателя, которое NER не берет из-за верстки резюме.

Повод: 18.08.2026 на живом резюме два работодателя ушли в облачную модель открытым
текстом. Причина оказалась не в одном правиле, а в двух разных дырах, и тесты здесь
разделены так же:

- "Спарго Технологии, ЗАО" - форма ПОСЛЕ названия и без кавычек (основной формат
  выгрузки с hh.ru). Признак формальный, значит закрывается регуляркой;
- "Спортмастер Россия" - формальных признаков нет вовсе. Регуляркой такое не взять,
  не забрав заодно половину документа, - только словарем или LLM-аудитором.

Проверялось и опровергнуто: чистка колоночной верстки эту дыру не закрывает. NER
теряет название и на отдельной строке, если рядом стоят даты или тире.
"""
from pii_mask.core import Masker
from pii_mask.recognizers import ORG_TRAILING_FORM_RE, find_format_entities, load_org_dict

CV_FRAGMENT = (
    "Апрель 2024 —      Спортмастер Россия\n"
    "Сентябрь 2025      Ведущий системный аналитик\n\n"
    "Январь 2024 —      Спарго Технологии, ЗАО\n"
    "Апрель 2024        Аналитик\n"
)


def _mask(text: str, **kw) -> str:
    return Masker(ner=False, **kw).mask(text)[0]


class TestTrailingForm:
    def test_masks_name_before_form(self):
        assert "Спарго" not in _mask(CV_FRAGMENT)

    def test_matches_in_column_layout(self):
        hit = ORG_TRAILING_FORM_RE.search("Январь 2024 —      Спарго Технологии, ЗАО")
        assert hit and hit.group() == "Спарго Технологии, ЗАО"

    def test_matches_on_clean_line(self):
        assert ORG_TRAILING_FORM_RE.search("Работал в Спарго Технологии, ЗАО.")

    def test_leading_form_not_stolen(self):
        """В "Москва, ООО Ромашка" организация - "ООО Ромашка", город трогать нельзя."""
        assert not ORG_TRAILING_FORM_RE.search("Москва, ООО Ромашка")

    def test_line_break_after_form_is_fine(self):
        assert ORG_TRAILING_FORM_RE.search("Ромашка, ООО\nАдрес: тут")

    def test_ip_after_fio_is_not_org(self):
        """"Иванов Иван, ИП" - это человек, а не хвост названия."""
        assert not ORG_TRAILING_FORM_RE.search("Иванов Иван, ИП")

    def test_common_words_not_matched(self):
        assert not ORG_TRAILING_FORM_RE.search("в банке, компания росла")


class TestOrgDict:
    def test_name_without_any_marker_survives_without_dict(self):
        """Фиксируем границу: без словаря такое название не маскируется."""
        assert "Спортмастер" in _mask(CV_FRAGMENT)

    def test_dict_masks_it(self, tmp_path):
        d = tmp_path / "orgs.txt"
        d.write_text("# работодатели кейса\nСпортмастер Россия\n", encoding="utf-8")
        out = _mask(CV_FRAGMENT, org_names=load_org_dict(d))
        assert "Спортмастер" not in out

    def test_dict_propagates_to_other_mentions(self, tmp_path):
        d = tmp_path / "orgs.txt"
        d.write_text("Спортмастер Россия\n", encoding="utf-8")
        text = "Работал в Спортмастер Россия.\nПозже вернулся в Спортмастер."
        out = _mask(text, org_names=load_org_dict(d))
        assert "Спортмастер" not in out

    def test_comments_and_blanks_ignored(self, tmp_path):
        d = tmp_path / "orgs.txt"
        d.write_text("\n# только комментарий\n  Ромашка  # хвост\n\n", encoding="utf-8")
        assert load_org_dict(d) == ("Ромашка",)

    def test_missing_file_is_an_error(self, tmp_path):
        import pytest

        with pytest.raises(SystemExit):
            load_org_dict(tmp_path / "нет.txt")

    def test_dict_is_optional(self):
        assert find_format_entities("текст без организаций") == []
