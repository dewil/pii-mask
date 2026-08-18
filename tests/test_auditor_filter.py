"""Отсев мусора у LLM-аудитора.

Маленькая модель щедра на кандидатов, и цена ложной находки здесь выше цены
пропуска: должность или список навыков, превращенные в {{PERSON_1}}, делают текст
нечитаемым - ровно тот вред, ради которого в NER заведены STOP_TERMS. До 18.08.2026
находки аудитора этот фильтр обходили.

Сеть не нужна: проверяется только предикат отбора, не поход в Ollama.
"""
from pii_mask.auditor import _plausible_candidate as ok


class TestJobTitles:
    def test_title_is_not_a_person(self):
        assert not ok("PERSON", "Ведущий системный аналитик")

    def test_single_word_title_is_not_a_person(self):
        assert not ok("PERSON", "Аналитик")

    def test_real_name_survives(self):
        assert ok("PERSON", "Сергей Волков")

    def test_given_name_survives(self):
        assert ok("PERSON", "Дмитрий")

    def test_unknown_word_is_kept_as_possible_rare_name(self):
        """Слова нет в словаре - экзотическое имя дороже лишней маски."""
        assert ok("PERSON", "Ынгжбар Тукуев")


class TestLists:
    def test_skill_list_is_not_a_person(self):
        assert not ok("PERSON", "Jira, SQL, Python")

    def test_two_surnames_survive(self):
        assert ok("PERSON", "Иванов, Петров")

    def test_org_with_trailing_form_survives(self):
        """У организаций запятая перед формой законна - фильтр списков их не трогает."""
        assert ok("ORG", "Ромашка, ООО")


class TestStopTerms:
    def test_tool_name_rejected_even_from_auditor(self):
        assert not ok("ORG", "Jira")

    def test_org_without_markers_passes(self):
        assert ok("ORG", "Спортмастер Россия")
