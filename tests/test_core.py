"""Ядро Masker: mask/unmask, консистентность меток, обратная подстановка."""
from pii_mask.core import Masker, UNKNOWN


def test_roundtrip_phone_email():
    m = Masker()
    src = "Иван: мой телефон +7 903 123-45-67, почта ivan@mail.ru"
    masked, mapping = m.mask(src)
    assert "+7 903 123-45-67" not in masked
    assert "ivan@mail.ru" not in masked
    # формат-сохраняющие фейки: в тексте валидный по структуре телефон и email
    assert "@example.com" in masked
    restored = m.unmask(masked, mapping)
    assert "+7 903 123-45-67" in restored
    assert "ivan@mail.ru" in restored


def test_same_entity_same_label():
    m = Masker()
    src = "телефон +7 903 123-45-67, повторяю: +7 903 123-45-67"
    masked, mapping = m.mask(src)
    phones = [v for v in mapping["labels"].values() if v["type"] == "PHONE"]
    assert len(phones) == 1


def test_person_inflections_one_label():
    # Natasha: "Иван Петров" и "Ивана Петрова" - одна персона, одна метка
    m = Masker()
    src = "Иван Петров сказал, что заявку Ивана Петрова согласовали."
    masked, mapping = m.mask(src)
    persons = [k for k, v in mapping["labels"].items() if v["type"] == "PERSON"]
    assert len(persons) == 1
    assert "Петров" not in masked and "Петрова" not in masked


def test_unmask_returns_canonical():
    m = Masker()
    src = "Начальник Иван Петров утвердил план."
    masked, mapping = m.mask(src)
    label = next(k for k, v in mapping["labels"].items() if v["type"] == "PERSON")
    answer = f"План {label} принят."
    restored = m.unmask(answer, mapping)
    assert "Иван Петров" in restored
    assert "{{" not in restored


def test_unknown_label_is_guarded():
    # модель выдумала метку, которой не было во входе - защита, не восстанавливаем
    m = Masker()
    _, mapping = m.mask("Иван Петров на связи")
    restored = m.unmask("Ответ для {{PERSON_99}} готов", mapping)
    assert UNKNOWN in restored
    assert "{{PERSON_99}}" not in restored


def test_mask_idempotent():
    m = Masker()
    src = "Иван Петров, тел +7 903 123-45-67"
    masked, mapping = m.mask(src)
    masked2, mapping2 = m.mask(masked, mapping=mapping)
    assert masked2 == masked
    assert mapping2["labels"] == mapping["labels"]


def test_mapping_continuation():
    # второе сообщение диалога: та же сущность - та же метка, новая - следующий номер
    m = Masker()
    _, mapping = m.mask("Пишет Иван Петров")
    masked2, mapping2 = m.mask("Иван Петров и Анна Сидорова на встрече", mapping=mapping)
    persons = {v["original"]: k for k, v in mapping2["labels"].items() if v["type"] == "PERSON"}
    assert persons["Иван Петров"] == next(
        k for k, v in mapping["labels"].items() if v["type"] == "PERSON"
    )
    assert len(persons) == 2


def test_phone_digit_fallback_on_unmask():
    # модель переформатировала фейковый номер - восстанавливаем по цифрам
    m = Masker()
    src = "тел +7 903 123-45-67"
    masked, mapping = m.mask(src)
    fake = next(k for k, v in mapping["labels"].items() if v["type"] == "PHONE")
    digits = "".join(c for c in fake if c.isdigit())
    restored = m.unmask(f"Звоните: {digits}", mapping)
    assert "+7 903 123-45-67" in restored


def test_speaker_markers_untouched():
    # разметка giga-transcribe не должна страдать
    m = Masker()
    src = "**[00:23] Спикер 2:** согласен с Иваном Петровым"
    masked, _ = m.mask(src)
    assert masked.startswith("**[00:23] Спикер 2:**")
