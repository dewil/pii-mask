"""Имена и организации через Natasha (slovnet NER, CPU, офлайн).

Ключ консистентности - нормальная форма спана: все словоформы одной персоны
("Иван Петров", "Ивана Петрова", "Иваном Петровым") дают один key и одну метку.
"""
from __future__ import annotations

import re

from .recognizers import Entity

_TYPE_MAP = {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"}

# Граммемы личного имени в pymorphy: имя, фамилия, отчество.
_NAME_GRAMMEMES = {"Name", "Surn", "Patr"}

# Термины, которые NER регулярно принимает за организацию или персону в резюме,
# вакансиях и служебной верстке.
# Список дешевый и пополняется по мере встреч - в отличие от NER, его правка
# ничего не ломает. Сравнение по нижнему регистру.
STOP_TERMS = frozenset({
    "dwh", "data mart", "etl", "bi", "brd", "fsd", "lm", "sql", "ms sql",
    "powerbi", "power bi", "crm", "erp", "kpi", "api", "ui", "ux",
    "специализации", "специализация", "занятость", "планирование",
    "анализ данных", "навыки", "образование", "опыт работы", "транскрипт",
})

# Разметка сбивает сегментацию slovnet: строка "# Имя Фамилия" не дает НИ ОДНОЙ
# сущности, хотя без решеток имя распознается. Проверено, что ломают: ведущие
# "#" (в том числе с отступом и закрывающие), "+", вертикальная черта таблицы и
# обратные кавычки. Не ломают: "-", "*", ">", нумерация, "#тег" в середине строки.
_MD_LINE_EDGE = re.compile(r"^[ \t]*[#+|]+[ \t]*|[ \t]*[#|]+[ \t]*$", re.M)
_MD_INLINE = re.compile(r"[|`]")
# перевод строки после строки, не оканчивающейся знаком препинания
_LINE_BREAK = re.compile(r"(?<=[^\s.!?:;,\-|>])\n")


def _demarkup(text: str) -> str:
    """Теневая копия текста без разметки, ТОЙ ЖЕ длины.

    Замена на пробелы посимвольно - принципиальна: офсеты сущностей в теневом
    тексте совпадают с оригиналом, поэтому маскируем в оригинале без карты
    смещений. Отдавать NER очищенный текст другой длины нельзя - спаны поедут.
    """
    text = _MD_LINE_EDGE.sub(lambda m: " " * len(m.group()), text)
    return _MD_INLINE.sub(" ", text)


def _terminate_lines(text: str) -> str:
    """Завершить точкой строки без знака препинания на конце (длина та же).

    Строка без завершающей пунктуации сливается со следующей, и в слитом
    предложении сущность теряет метку: шапка резюме "Имя Фамилия" плюс строка
    "Телефон: ..." не дает НИ ОДНОЙ сущности, хотя каждая строка по отдельности
    размечается. Замена "\\n" на "." длину сохраняет, поэтому офсеты те же.
    """
    return _LINE_BREAK.sub(".", text)


class NatashaNer:
    _shared = None  # модели грузятся секунды - один экземпляр на процесс

    def __init__(self) -> None:
        from natasha import (
            Doc,
            MorphVocab,
            NewsEmbedding,
            NewsMorphTagger,
            NewsNERTagger,
            Segmenter,
        )

        self._Doc = Doc
        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        emb = NewsEmbedding()
        self._morph_tagger = NewsMorphTagger(emb)
        self._ner_tagger = NewsNERTagger(emb)

    @classmethod
    def shared(cls) -> "NatashaNer":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def extract(self, text: str) -> list[Entity]:
        """Два прохода по одному тексту, объединение находок.

        Проходы дополняют друг друга и годятся для разных документов: без
        завершающих точек лучше размечается проза (транскрипт переносится по
        ширине, и точка рубила бы предложение посередине), с точками - записи
        по строкам (резюме, выгрузки, таблицы). Какой перед нами документ,
        заранее неизвестно, поэтому берем оба, а пересечения спанов разрешит
        Masker._resolve. Обе трансформации сохраняют длину - офсеты общие.
        """
        shadow = _demarkup(text)
        found = self._tag(text, shadow) + self._tag(text, _terminate_lines(shadow))
        seen, out = set(), []
        for ent in found:
            key = (ent.type, ent.start, ent.end)
            if key in seen or not self._plausible(ent):
                continue
            seen.add(key)
            out.append(ent)
        return out

    def _plausible(self, ent: Entity) -> bool:
        """Отсев заведомого мусора NER на верстке резюме и выгрузок.

        Три правила, от общего к частному:

        1. Спан через перенос строки - не сущность. В колоночной верстке NER
           склеивал полстраницы в одну "организацию": от названия факультета до
           списка языков.
        2. Однословная персона, которую словарь знает как обычное слово, -
           не персона: "Аналитик", "Желаемая", "Транскрипт". Слово, которого в
           словаре нет вовсе, оставляем персоной - экзотическое имя дороже
           лишней маски.
        3. Термин из STOP_TERMS - служебное слово верстки, а не сущность.
        """
        if "\n" in ent.text:
            return False
        if " ".join(ent.text.lower().split()) in STOP_TERMS:
            return False
        if ent.type == "PERSON" and len(ent.text.split()) == 1:
            parses = self._morph_vocab.parse(ent.text)
            if any(p.is_known for p in parses):
                return any(g in _NAME_GRAMMEMES for p in parses for g in p.tag.grammemes)
        return True

    def _tag(self, text: str, shadow: str) -> list[Entity]:
        doc = self._Doc(shadow)
        doc.segment(self._segmenter)
        doc.tag_morph(self._morph_tagger)
        doc.tag_ner(self._ner_tagger)
        out = []
        for span in doc.spans:
            etype = _TYPE_MAP.get(span.type)
            if etype is None:
                continue
            try:
                span.normalize(self._morph_vocab)
                key = (span.normal or span.text).lower()
            except Exception:
                key = span.text.lower()
            # Косвенный падеж - если НИ ОДИН токен спана не в именительном.
            # Не "все токены косвенные": морфология читает женскую фамилию
            # "Смирнова" как родительный от "Смирнов", и строгое правило отдало бы
            # лемму, превратив женское имя в мужское.
            cases = [
                (t.feats or {}).get("Case")
                for t in doc.tokens
                if span.start <= t.start < span.stop
            ]
            oblique = bool(cases) and "Nom" not in cases
            # текст берем из ОРИГИНАЛА по тем же офсетам: в теневой копии на месте
            # разметки пробелы, и попади она в спан - в mapping уехал бы не оригинал
            out.append(
                Entity(etype, text[span.start:span.stop], span.start, span.stop, key, oblique)
            )
        return out
