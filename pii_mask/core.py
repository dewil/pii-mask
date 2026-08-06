"""Ядро: mask/unmask со stateless mapping.

Принципы (см. дизайн-обсуждение):
- распознаватели только находят сущности, замену делает детерминированный код;
- одинаковая сущность (включая словоформы) -> одна метка на весь диалог;
- mapping возвращается вызывающему, сервис ничего не хранит;
- метка, которой не было во входе, при unmask превращается в UNKNOWN - защита
  от выдуманных моделью данных.

Форматные типы PHONE/EMAIL заменяются на формат-сохраняющие фейки
(+7 000 ... / userN@example.com), остальное - на метки {{TYPE_N}}.
"""
from __future__ import annotations

import copy
import re

from .recognizers import Entity, digits, find_format_entities

LABEL_RE = re.compile(r"\{\{([A-Z]+)_(\d+)\}\}")
PHONE_SCAN_RE = re.compile(r"\+?[78][\d \-()]{9,18}\d")
FAKE_EMAIL_SCAN_RE = re.compile(r"user\d+@example\.com", re.IGNORECASE)

UNKNOWN = "[неизвестное значение]"

DEFAULT_TYPES = ("PERSON", "ORG", "PHONE", "EMAIL", "CARD", "INN", "SNILS", "PASSPORT", "TG", "URL")
# LOC (города/страны) сознательно не маскируем по умолчанию: в рабочих текстах
# это чаще контекст, чем ПД, и ложные маски убивают смысл. Включается через types.

_PRIORITY = {
    "EMAIL": 1, "TG": 2, "CARD": 3, "SNILS": 4, "PHONE": 5,
    "INN": 6, "PASSPORT": 7, "URL": 8, "PERSON": 9, "ORG": 10, "LOC": 11,
}


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


class Masker:
    def __init__(self, types: tuple[str, ...] = DEFAULT_TYPES, ner: bool = True):
        self.types = set(types)
        self._use_ner = ner and bool({"PERSON", "ORG", "LOC"} & self.types)

    # --- mask ---

    def mask(
        self,
        text: str,
        mapping: dict | None = None,
        extra_entities: list[Entity] | None = None,
    ) -> tuple[str, dict]:
        mapping = copy.deepcopy(mapping) if mapping else {"version": 1, "labels": {}}
        labels: dict = mapping["labels"]

        candidates = [e for e in find_format_entities(text) if e.type in self.types]
        if self._use_ner:
            from .ner import NatashaNer

            candidates += [e for e in NatashaNer.shared().extract(text) if e.type in self.types]
        if extra_entities:
            # находки аудитора не фильтруем по types (раз LLM сочла это ПД - маскируем),
            # но отбрасываем наши же артефакты: метки и фейки не должны маскироваться
            # вторым слоем, иначе unmask разворачивает только верхний
            candidates += [e for e in extra_entities if not self._is_own_artifact(e.text)]

        # уже стоящие метки и спаны внутри них неприкосновенны (идемпотентность)
        occupied = [(m.start(), m.end()) for m in LABEL_RE.finditer(text)]
        accepted = self._resolve(candidates, occupied)

        replacements: list[tuple[int, int, str]] = []
        for ent in sorted(accepted, key=lambda e: e.start):
            placeholder = self._assign_label(labels, ent)
            replacements.append((ent.start, ent.end, placeholder))

        out, pos = [], 0
        for start, end, placeholder in replacements:
            out.append(text[pos:start])
            out.append(placeholder)
            pos = end
        out.append(text[pos:])
        return "".join(out), mapping

    @staticmethod
    def _resolve(candidates: list[Entity], occupied: list[tuple[int, int]]) -> list[Entity]:
        taken = list(occupied)
        accepted = []
        ordered = sorted(
            candidates,
            key=lambda e: (_PRIORITY.get(e.type, 99), -(e.end - e.start), e.start),
        )
        for ent in ordered:
            span = (ent.start, ent.end)
            if any(_overlaps(span, t) for t in taken):
                continue
            taken.append(span)
            accepted.append(ent)
        return accepted

    def _assign_label(self, labels: dict, ent: Entity) -> str:
        for placeholder, rec in labels.items():
            if rec["type"] == ent.type and (
                rec["key"] == ent.key or ent.key in rec.get("aliases", [])
            ):
                return placeholder

        # одиночное имя линкуем к единственному полному ФИО с этим токеном
        if ent.type == "PERSON" and " " not in ent.key:
            hosts = [
                (placeholder, rec)
                for placeholder, rec in labels.items()
                if rec["type"] == "PERSON" and " " in rec["key"] and ent.key in rec["key"].split()
            ]
            if len(hosts) == 1:
                placeholder, rec = hosts[0]
                rec.setdefault("aliases", []).append(ent.key)
                return placeholder

        n = 1 + max(
            (rec["n"] for rec in labels.values() if rec["type"] == ent.type), default=0
        )
        placeholder = self._make_placeholder(ent.type, n)
        original = ent.text
        # Лемму подставляем ТОЛЬКО для явно косвенной формы: иначе морфология
        # портит имя - женская фамилия "Смирнова" читается как родительный от
        # "Смирнов" и восстанавливалась бы мужской формой.
        if ent.type == "PERSON" and ent.oblique:
            original = ent.key.title()  # восстанавливать именительный падеж, не случайную словоформу
        labels[placeholder] = {"type": ent.type, "original": original, "key": ent.key, "n": n}
        return placeholder

    @staticmethod
    def _is_own_artifact(s: str) -> bool:
        from .recognizers import FAKE_EMAIL_RE

        s = s.strip()
        if LABEL_RE.search(s):
            return True
        if FAKE_EMAIL_RE.match(s):
            return True
        d = digits(s)
        return len(d) == 11 and d[1:4] == "000"

    @staticmethod
    def _make_placeholder(etype: str, n: int) -> str:
        if etype == "PHONE":
            return f"+7 000 000-{n // 100:02d}-{n % 100:02d}"
        if etype == "EMAIL":
            return f"user{n}@example.com"
        return f"{{{{{etype}_{n}}}}}"

    # --- unmask ---

    def mask_with_audit(self, text: str, mapping: dict | None = None) -> tuple[str, dict]:
        """mask + второй проход локальной LLM по уже замаскированному тексту.

        Fail-closed: если аудит запрошен, а Ollama недоступна - ошибка, а не
        тихий пропуск (вызывающий явно попросил повышенный recall).
        """
        from .auditor import audit, ollama_alive

        if not ollama_alive():
            raise RuntimeError(
                "запрошен --audit, но Ollama недоступна (PII_MASK_OLLAMA_URL); "
                "маскировка без аудита не выполнена намеренно"
            )
        masked, mapping = self.mask(text, mapping)
        extras = audit(masked)
        if extras:
            masked, mapping = self.mask(masked, mapping, extra_entities=extras)
        return masked, mapping

    def unmask(self, text: str, mapping: dict) -> str:
        labels: dict = mapping.get("labels", {})

        def sub_label(m: re.Match) -> str:
            rec = labels.get(m.group(0))
            return rec["original"] if rec else UNKNOWN

        text = LABEL_RE.sub(sub_label, text)

        phone_by_digits = {
            digits(placeholder): rec["original"]
            for placeholder, rec in labels.items()
            if rec["type"] == "PHONE"
        }

        def sub_phone(m: re.Match) -> str:
            d = digits(m.group(0))
            if d in phone_by_digits:
                return phone_by_digits[d]
            if d[1:4] == "000":  # выдуманный моделью номер из фейкового диапазона
                return UNKNOWN
            return m.group(0)

        text = PHONE_SCAN_RE.sub(sub_phone, text)

        def sub_email(m: re.Match) -> str:
            rec = labels.get(m.group(0).lower())
            return rec["original"] if rec else UNKNOWN

        text = FAKE_EMAIL_SCAN_RE.sub(sub_email, text)
        return text
