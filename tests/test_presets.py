"""Именованные наборы типов: что считать ПД, знает сервис, а не вызывающий.

Набор подбирался месяц по живым файлам и жил константами в телеграм-боте.
Второй потребитель услуги подбирал бы те же шестнадцать типов и четыре флага
заново - и получил бы другой результат на том же документе, причем молча: оба
прогона отвечают кодом 0.

Наборов два, и различает их строгость к организациям, а не список типов
(довод - в ~/Work/pii-mask/docs/done/2026-09-29-spec-presets.md).
"""
import subprocess
import sys

import pytest

from pii_mask import presets

РЕЗЮМЕ = """Сухарев Пётр
Ведущий инженер
Москва | +7 916 000-00-03 | suharev@example.org
Ключевые компетенции: проектирование, надзор

Опыт работы
Заречье Инвест, 02.2014 - 01.2025
Ведущий инженер, 01.2021 - 01.2025
Образование: МИСИ
"""

СЧЕТ = """Счет на оплату № 41 от 03.02.2026
Поставщик: ООО "Заречье Инвест", ИНН 7701234567, КПП 770101001
Товар: насос Грундфос, фильтр Аквабрайт
"""


def test_two_presets_are_offered():
    assert set(presets.names()) == {"resume", "accounting"}


def test_resume_and_accounting_share_the_type_list():
    """Разводить списки значит платить утечкой за аккуратность."""
    assert presets.get("resume").types == presets.get("accounting").types


def test_presets_differ_in_strictness_to_organisations():
    assert presets.get("accounting").ner_org_needs_form
    assert not presets.get("resume").ner_org_needs_form


def test_unknown_preset_names_the_known_ones():
    with pytest.raises(ValueError) as err:
        presets.get("бухгалтерия")
    assert "resume" in str(err.value) and "accounting" in str(err.value)


def test_auto_picks_resume_for_a_resume():
    chosen, _ = presets.resolve("auto", РЕЗЮМЕ)
    assert chosen.name == "resume"


def test_auto_picks_accounting_for_a_business_paper():
    chosen, _ = presets.resolve("auto", СЧЕТ)
    assert chosen.name == "accounting"


def test_auto_falls_back_to_strict_when_the_document_is_unreadable():
    """Лишняя маска дешевле пропуска, поэтому неизвестность - строгий режим."""
    chosen, why = presets.resolve("auto", None)
    assert chosen.name == "accounting"
    assert "не" in why.lower()


def test_resolve_explains_the_choice():
    """Молчаливая смена режима - два прогона одного файла дают разное."""
    _, why = presets.resolve("auto", РЕЗЮМЕ)
    assert "резюме" in why.lower()


# --- CLI -------------------------------------------------------------------

def run(args, cwd):
    return subprocess.run([sys.executable, "-m", "pii_mask.cli", *args],
                          capture_output=True, text=True, cwd=cwd)


def mask_with(tmp_path, text, extra):
    src = tmp_path / "док.md"
    src.write_text(text, encoding="utf-8")
    out = tmp_path / "готово.md"
    proc = run(["mask", str(src), "-o", str(out), "--mapping",
                str(tmp_path / "реестр.json"), *extra], tmp_path)
    assert proc.returncode == 0, proc.stderr
    return out.read_text(encoding="utf-8"), proc.stderr


def test_resume_preset_masks_an_employer_without_a_legal_form(tmp_path):
    masked, _ = mask_with(tmp_path, РЕЗЮМЕ, ["--preset", "resume"])
    assert "Заречье Инвест" not in masked


def test_accounting_preset_keeps_trade_marks_in_the_goods_column(tmp_path):
    masked, _ = mask_with(tmp_path, СЧЕТ, ["--preset", "accounting"])
    assert "Грундфос" in masked and "Аквабрайт" in masked


def test_auto_preset_on_a_resume_behaves_like_the_resume_preset(tmp_path):
    masked, err = mask_with(tmp_path, РЕЗЮМЕ, ["--preset", "auto"])
    assert "Заречье Инвест" not in masked
    assert "resume" in err


def test_explicit_types_replace_the_preset_list(tmp_path):
    """Ручной режим: список задан руками, набор его не возвращает."""
    masked, _ = mask_with(tmp_path, РЕЗЮМЕ,
                          ["--preset", "resume", "--types", "EMAIL"])
    assert "suharev@example.org" not in masked
    assert "+7 916 000-00-03" in masked


def test_explicit_flag_adds_strictness_on_top_of_a_preset(tmp_path):
    masked, _ = mask_with(tmp_path, РЕЗЮМЕ,
                          ["--preset", "resume", "--ner-org-needs-form"])
    assert "Заречье Инвест" in masked


def test_chosen_preset_is_printed(tmp_path):
    _, err = mask_with(tmp_path, СЧЕТ, ["--preset", "accounting"])
    assert "accounting" in err


def test_presets_command_lists_the_sets(tmp_path):
    proc = run(["presets"], tmp_path)
    assert proc.returncode == 0
    assert "resume" in proc.stdout and "accounting" in proc.stdout
    assert "PERSON" in proc.stdout
