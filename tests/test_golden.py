"""Golden set: на эталонных транскриптах с вымышленными ПД проверяем recall.

Правило: ни одна строка из MUST_MASK не имеет права дожить до замаскированного текста.
Ложные срабатывания здесь не проверяем - пропуск дороже лишней маски.
"""
from pathlib import Path

import pytest

from pii_mask.core import Masker

GOLDEN = Path(__file__).parent / "golden"

MUST_MASK = {
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
}


@pytest.mark.parametrize("fname", sorted(MUST_MASK))
def test_golden_recall(fname):
    src = (GOLDEN / fname).read_text(encoding="utf-8")
    masked, mapping = Masker().mask(src)
    leaked = [s for s in MUST_MASK[fname] if s in masked]
    assert not leaked, f"утекло в masked: {leaked}"
    kept_broken = [s for s in MUST_KEEP[fname] if s not in masked]
    assert not kept_broken, f"поломана структура: {kept_broken}"
    # roundtrip: все оригиналы возвращаются
    restored = Masker().unmask(masked, mapping)
    for s in ("Дмитрий Соколов", "marina.k@romashka-corp.ru"):
        assert s in restored
