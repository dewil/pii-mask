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
#
# Зачем это важнее, чем кажется. Смысл маскировки ORG - скрыть АФФИЛИАЦИИ человека:
# где работал, где учился. Название инструмента из раздела навыков аффилиацией не
# является, а его замена на метку выносит из текста смысл: "внедряю AI" превращается
# в "внедряю {{ORG_2}}", и дальше документ нечитаем ни человеком, ни моделью.
# На резюме без этого списка доля ложных срабатываний доходила до двух третей
# (замер 13.08.2026: 50 ORG, из них настоящих организаций около 15).
#
# Названий компаний здесь быть не должно ни при каких обстоятельствах: попав сюда,
# работодатель перестанет маскироваться навсегда и молча. Только родовые термины.
STOP_TERMS = frozenset({
    # данные и разработка
    "dwh", "data mart", "etl", "bi", "brd", "fsd", "lm", "sql", "ms sql",
    "powerbi", "power bi", "crm", "erp", "kpi", "api", "ui", "ux",
    "ml", "nlp", "ner", "llm", "genai", "rag", "mcp", "sdd", "ci/cd", "devops",
    "backend", "frontend", "fullstack", "qa", "ux/ui",
    # инструменты и продукты - в резюме это перечень навыков, а не место работы
    "jira", "redmine", "confluence", "ms project", "mysql", "postgresql",
    "postgres", "mongodb", "clickhouse", "redis", "docker", "kubernetes",
    "laravel", "django", "react", "vue", "git", "gitlab", "github",
    "ollama", "claude", "claude api", "claude code", "openai api", "cursor",
    "langchain", "excel", "ms office", "figma", "notion", "trello", "asana",
    # методологии и управленческие рамки
    "scrum", "kanban", "waterfall", "agile", "safe", "evm", "pmbok", "itil",
    "spec-driven development", "time & material", "fixed price",
    # роли и функции
    "product owner", "product manager", "project manager", "team lead",
    "tech lead", "delivery", "delivery/pm", "pm", "рп", "тимлид", "cto", "cio",
    "scrum master", "бизнес-аналитик", "системный аналитик",
    # домен и сокращения деловой речи
    "ai", "it", "hr", "ib", "иб", "ит", "nda", "p&l", "roi", "tco", "sla",
    "ткп", "тз", "нда", "гост", "ндс", "ооо", "ано", "ип",
    # служебная верстка документов
    "специализации", "специализация", "занятость", "планирование",
    "анализ данных", "навыки", "образование", "опыт работы", "транскрипт",
    "ключевые навыки", "о себе", "достижения", "проекты", "портфолио",
})

# Хвост после дефиса или слеша не меняет сути термина: "AI-стек", "P&L-отчетность",
# "SDD-конвейер", "Claude Code-сессий" - это те же AI, P&L, SDD и Claude Code.
# Перечислять все словообразования в списке бессмысленно, их бесконечно много.
#
# Цена приема: компания, чье название начинается со стоп-термина ("AI-Systems"),
# маскироваться перестанет. Считаем допустимым - маскировка ORG у нас мера
# снижения ущерба, а не основание правового режима, и вред от нечитаемого
# документа больше вреда от одного непокрытого названия.
_TERM_TAIL = re.compile(r"[-/].*$")

# Должность за названием работодателя: в резюме строка пишется одной строкой
# ("Северная Торговая Компания - логист"), NER размечает ее одной организацией целиком,
# и в обезличенный текст уходит {{ORG_1}} - вместе с должностью, которой в тексте
# больше нет. Для диагностики резюме это прямой ущерб: модель не видит роль и заявляет,
# что должность не указана, - тот самый класс выдуманных утверждений, ради которого
# ведется журнал замеров.
#
# Признак хвоста - тире В ПРОБЕЛАХ и строчная буква после него. Составные названия
# пишутся через дефис без пробелов ("Альфа-Банк"), а части настоящего названия - с
# прописной ("Технопарк - Мордовия"), поэтому строчная буква после отбивки означает
# должность, обязанность или пояснение, но не продолжение имени собственного.
_ROLE_TAIL = re.compile(r"\s+[-–—]\s+[а-яёa-z][^\n]*\Z")


def _role_tail_len(text: str) -> int:
    """Длина хвоста-должности в конце спана; 0 - хвоста нет."""
    m = _ROLE_TAIL.search(text)
    return len(m.group()) if m else 0


# Разметка сбивает сегментацию slovnet: строка "# Имя Фамилия" не дает НИ ОДНОЙ
# сущности, хотя без решеток имя распознается. Проверено, что ломают: ведущие
# "#" (в том числе с отступом и закрывающие), "+", вертикальная черта таблицы и
# обратные кавычки. Не ломают: "-", "*", ">", нумерация, "#тег" в середине строки.
_MD_LINE_EDGE = re.compile(r"^[ \t]*[#+|]+[ \t]*|[ \t]*[#|]+[ \t]*$", re.M)
_MD_INLINE = re.compile(r"[|`]")
# перевод строки после строки, не оканчивающейся знаком препинания
_LINE_BREAK = re.compile(r"(?<=[^\s.!?:;,\-|>])\n")


def _is_stop_term(text: str) -> bool:
    """Родовой термин, а не сущность: сравнение целиком и по голове составного."""
    term = " ".join(text.lower().split()).strip(" -–,.:;()[]\"'«»")
    if not term:
        return True
    if term in STOP_TERMS:
        return True
    head = _TERM_TAIL.sub("", term).strip()
    return bool(head) and head != term and head in STOP_TERMS


def _demarkup(text: str) -> str:
    """Теневая копия текста без разметки, ТОЙ ЖЕ длины.

    Замена на пробелы посимвольно - принципиальна: офсеты сущностей в теневом
    тексте совпадают с оригиналом, поэтому маскируем в оригинале без карты
    смещений. Отдавать NER очищенный текст другой длины нельзя - спаны поедут.
    """
    text = _MD_LINE_EDGE.sub(lambda m: " " * len(m.group()), text)
    return _MD_INLINE.sub(" ", text)


_CAPS_RUN = re.compile(r"[А-ЯЁA-Z]{2,}(?:[-'][А-ЯЁA-Z]{2,})*")


def _detitle_caps(text: str) -> str:
    """Слова капсом - в обычный регистр (длина та же, офсеты общие).

    NER учен на новостях, где имена и названия пишут обычным регистром; в реестрах
    и шапках официальных документов их пишут прописными, и распознавание падает
    почти в ноль. Регулярка с якорем на отчество закрывает только ФИО, у которых
    отчество есть: "ДРОЗДЕНКО РАИСА" и "АЛЬФА-БАНК" ей не по зубам, а нормализация
    регистра возвращает такие случаи в зону, где NER работает штатно.

    В маскированный текст все равно уходит оригинал: спаны берутся по офсетам из
    исходной строки, теневая копия нужна только тэггеру.
    """
    return _CAPS_RUN.sub(lambda m: m.group().capitalize(), text)


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
        found = (
            self._tag(text, shadow)
            + self._tag(text, _terminate_lines(shadow))
            + self._tag(text, _terminate_lines(_detitle_caps(shadow)))
            + self._name_words(text)
        )
        seen, out = set(), []
        for ent in found:
            key = (ent.type, ent.start, ent.end)
            if key in seen or not self._plausible(ent):
                continue
            seen.add(key)
            out.append(ent)
        return out

    def _name_words(self, text: str) -> list[Entity]:
        """Одинокое слово капсом, которое словарь знает как имя или фамилию.

        Последний рубеж для колонки, где ФИО стоит без отчества и без соседей:
        тэггеру не за что зацепиться, а морфология слово узнает. Требуем, чтобы
        слово было В СЛОВАРЕ - незнакомое здесь не трогаем, иначе под маску уйдут
        заголовки и аббревиатуры, которых в официальном документе больше, чем имен.
        """
        out = []
        for m in re.finditer(r"(?<![А-ЯЁ\w])[А-ЯЁ]{4,}(?![А-ЯЁ\w])", text):
            parses = self._morph_vocab.parse(m.group().capitalize())
            known = [p for p in parses if p.is_known]
            if known and any(g in _NAME_GRAMMEMES for g in known[0].tag.grammemes):
                out.append(
                    Entity("PERSON", m.group(), m.start(), m.end(), m.group().lower())
                )
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
           Сравнивается и целиком, и по голове составного термина (см. _TERM_TAIL).
        """
        if "\n" in ent.text:
            return False
        if _is_stop_term(ent.text):
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
            stop = span.stop - _role_tail_len(text[span.start:span.stop])
            if stop <= span.start:
                continue
            if stop != span.stop:
                # обрезали хвост - нормальная форма относилась к полному спану
                key = text[span.start:stop].lower()
            cases = [
                (t.feats or {}).get("Case")
                for t in doc.tokens
                if span.start <= t.start < stop
            ]
            oblique = bool(cases) and "Nom" not in cases
            # текст берем из ОРИГИНАЛА по тем же офсетам: в теневой копии на месте
            # разметки пробелы, и попади она в спан - в mapping уехал бы не оригинал
            raw = text[span.start:stop]
            out.append(
                Entity(etype, raw, span.start, stop, key, oblique)
            )
        return out
