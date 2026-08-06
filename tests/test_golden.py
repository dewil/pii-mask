"""Golden set: на эталонных транскриптах с вымышленными ПД проверяем recall.

Правило: ни одна строка из MUST_MASK не имеет права дожить до замаскированного текста.
Ложные срабатывания здесь не проверяем - пропуск дороже лишней маски.
"""
from pathlib import Path

import pytest

from pii_mask.core import Masker

GOLDEN = Path(__file__).parent / "golden"

_RESUME_PII = [
    "Смирнова Анна Валерьевна",
    "+7 (912) 3456789",
    "anna.smirnova.94@mail.example",
    "Северный Торговый Банк",
    "severbank-example.ru",
    "Новосибирский государственный технический университет",
    "Ковалев Игорь Петрович",
    "+7 (913) 7654321",
]

MUST_MASK = {
    # Одно содержание в двух формах: колоночная выгрузка из PDF и нормальный
    # markdown. Верстка не должна влиять на то, что считается персданными.
    "resume_hh_1.md": _RESUME_PII,
    "resume_md_1.md": _RESUME_PII,
    "transcript_1.md": [
        "Дмитрий Соколов",
        "Марина",
        "marina.k@romashka-corp.ru",
        "Соколову",
        "8 (916) 555-12-34",
        "Алексей Межов",
        "@a_mezhov",
        "Алексею",
        "Дмитрию Соколову",
    ],
}

MUST_KEEP = {
    "transcript_1.md": ["Спикер 1", "Спикер 2", "Спикер 3", "[00:23]", "Транскрипт"],
    # Резюме: канцелярия и доменные термины - не ПД. Если они уходят под маску,
    # документ становится нечитаемым, а для показа человеку - непригодным.
    "resume_hh_1.md": [
        "Желаемая должность", "Специализации", "Аналитик", "полная занятость",
        "Data Mart", "Планирование", "Анализ данных", "Образование", "Навыки",
        "Финансовый сектор", "Руководитель направления клиентской аналитики",
    ],
    "resume_md_1.md": [
        "Желаемая должность", "Аналитик", "полная занятость", "Data Mart",
        "планирование", "Образование", "Навыки", "Руководитель направления клиентской аналитики",
    ],
}

# Что обязано вернуться при обратной подстановке. Имена сюда не берем: у них
# отдельная известная проблема с падежом (женская фамилия восстанавливается
# мужской формой), она чинится отдельно и не должна прятать регрессии здесь.
ROUNDTRIP = {
    "transcript_1.md": ["marina.k@romashka-corp.ru", "8 (916) 555-12-34"],
    "resume_hh_1.md": ["anna.smirnova.94@mail.example", "+7 (912) 3456789", "www.severbank-example.ru"],
    "resume_md_1.md": ["anna.smirnova.94@mail.example", "+7 (913) 7654321", "www.severbank-example.ru"],
}


@pytest.mark.parametrize("fname", sorted(MUST_MASK))
def test_golden_recall(fname):
    src = (GOLDEN / fname).read_text(encoding="utf-8")
    masked, mapping = Masker().mask(src)
    leaked = [s for s in MUST_MASK[fname] if s in masked]
    assert not leaked, f"утекло в masked: {leaked}"
    kept_broken = [s for s in MUST_KEEP[fname] if s not in masked]
    assert not kept_broken, f"поломана структура: {kept_broken}"


@pytest.mark.parametrize("fname", sorted(ROUNDTRIP))
def test_golden_roundtrip(fname):
    src = (GOLDEN / fname).read_text(encoding="utf-8")
    masked, mapping = Masker().mask(src)
    restored = Masker().unmask(masked, mapping)
    missing = [s for s in ROUNDTRIP[fname] if s not in restored]
    assert not missing, f"не вернулось при развороте: {missing}"
