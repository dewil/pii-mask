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
    # HR и обучение: термины ремесла, а не работодатели
    "hrbp", "t&d", "talent review", "performance review", "performance",
    "ispring", "power point", "powerpoint", "smart", "9-box", "ии", "ис",
    "obsidian", "sqlite", "onnx", "codex", "qwen", "ktalk", "linkedin", "vk",
    "google", "telegram", "whisper", "pert", "wbs", "субд", "cv", "pdf",
    # платформы данных и инженерия: в резюме это перечень стека. Строка стека
    # идет сплошным перечислением через запятую, и NER метит организациями
    # половину списка - документ приходит с метками вместо инструментов
    # (замер 30.09.2026 на восьми живых резюме: 61 такая маска из 334).
    # Компании, чье имя носит и продукт (Oracle, IBM, Microsoft), сюда
    # намеренно не идут: в резюме они чаще работодатель, чем стек.
    "hadoop", "kafka", "airflow", "informatica", "tableau", "greenplum",
    "apache nifi", "nifi", "looker", "looker studio", "sas", "spark", "спарк",
    "python", "java", "bigdata", "big data", "trino", "cognos", "grafana",
    "prometheus", "superset", "dbt", "hive", "pxf", "edifact", "bpwin",
    "aris", "erwin", "smart vista", "equation", "кхд", "нси", "уид",
    # отраслевые аббревиатуры: инженерные системы здания, скоринг, обучение
    "скуд", "соуэ", "bms", "cctv", "апс", "аупт", "впв", "бки",
    "скоринг бюро", "enps", "galileo", "amadeus",
    # обороты деловой речи, которые морфология читает как имя собственное
    "due diligence", "presale", "пресейл", "fmcg", "пдн",
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
    # подписи реквизитов в бланках. Без них NER принимает саму подпись за имя
    # ("ИНН" ушло в маску как человек), а вместе с подписью пропадает признак,
    # по которому опознается номер рядом, - и номер остается открытым. Один
    # промах превращается в два, причем второй молчаливый.
    "инн", "кпп", "огрн", "огрнип", "окпо", "октмо", "оквэд", "бик",
    "снилс", "кбк", "уин",
    # делопроизводство и учет: в резюме бухгалтера и снабженца это предмет
    # работы, а не место работы. Без них "учет ТМЦ" превращалось в
    # "учет {{ORG_2}}", и обязанности становились нечитаемыми.
    "тмц", "пто", "егрюл", "егрип", "ндфл", "фсс", "пфр", "омс", "усн",
    "осно", "envd", "енвд", "кудир", "тк рф", "гк рф", "жкх", "смр", "окс",
    "кс-2", "кс-3", "тору", "зуп", "мсфо", "рсбу", "авр", "первичка",
    # товарная номенклатура: родовые слова, которые морфология читает как
    # форму имени ("саше" - и товар, и дательный падеж "Саша")
    "саше",
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
# пишутся через дефис без пробелов ("Ромашка-Банк"), а части настоящего названия - с
# прописной ("Технопарк - Заречье"), поэтому строчная буква после отбивки означает
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
    if head and head != term and head in STOP_TERMS:
        return True
    return _term_with_plain_words(text, term)


def _term_with_plain_words(original: str, term: str) -> bool:
    """Стоп-термин плюс обычные слова вокруг него: "курс Power Point".

    Перечислять такие спаны поштучно бессмысленно - их столько, сколько фраз в
    языке. Зато у них общее устройство: известный термин, а вокруг слова со
    строчной буквы ("курс", "офлайн", "поколение").

    Регистр остатка - главное условие, без него правило съедает названия: в
    "Ромашка SQL" остаток "Ромашка" словарь тоже знает обычным словом (цветок),
    и спан ушел бы из масок вместе с работодателем. Название пишут с большой
    буквы, пояснение вокруг термина - с маленькой.
    """
    остаток = term
    for stop in sorted(STOP_TERMS, key=len, reverse=True):
        if len(stop) >= 3:
            остаток = re.sub(rf"(?<![^\W\d_]){re.escape(stop)}(?![^\W\d_])",
                             " ", остаток)
    if остаток == term:
        return False                       # ни одного известного термина внутри
    слова = re.findall(r"[^\W\d_]{3,}", остаток)
    if not слова:
        return True                        # спан целиком собран из терминов
    if any(re.search(rf"(?<![^\W\d_])[А-ЯЁA-Z]{re.escape(w[1:])}", original)
           for w in слова):
        return False                       # слово с большой буквы - имя собственное
    return all(_common_word(w) for w in слова)


_COMMON_CACHE: dict[str, bool] = {}


def _common_word(word: str) -> bool:
    """Словарь знает слово обычным; морфологии нет - считаем, что не знает."""
    if word not in _COMMON_CACHE:
        try:
            _COMMON_CACHE[word] = NatashaNer.shared().known_common_word(word)
        except Exception:                                 # noqa: BLE001
            _COMMON_CACHE[word] = False
    return _COMMON_CACHE[word]


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
    отчество есть: "ВЕРШКОВА ГАЛИНА" и "РОМАШКА-БАНК" ей не по зубам, а нормализация
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
            if ent.type == "ORG" and self._in_stack_line(text, ent):
                continue
            seen.add(key)
            out.append(ent)
        out += self._surname_by_patronymic(text, out)
        return out

    # Слово с большой буквы вплотную к спану: слева "Сухарева Алина", справа
    # "Алина Сухарева". Перенос строки границей не считаем - ФИО не переносят.
    _LEFT_WORD = re.compile(r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)[ \t]+$")
    _RIGHT_WORD = re.compile(r"^[ \t]+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)")

    def _surname_by_patronymic(self, text: str, found: list[Entity]) -> list[Entity]:
        """Дотянуть спан ФИО до соседней фамилии, когда в нем есть отчество.

        NER регулярно отдает только "Имя Отчество", оставляя фамилию снаружи, и
        документ выглядит обезличенным при названном человеке (резюме,
        28.09.2026: в шапке осталась фамилия). Порядок слов тут не помогает -
        фамилия стоит и слева, и справа, - зато помогает отчество: рядом с ним
        слово с большой буквы фамилией и является.

        Соседа берем только с согласия словаря: имя, фамилия или слово, которого
        словарь не знает вовсе (экзотическая фамилия дороже лишней маски - тот
        же размен, что в _plausible). Должность и город словарь знает обычными
        словами, и они остаются на месте.
        """
        out = []
        for ent in found:
            if ent.type != "PERSON" or not self._has_patronymic(ent.text):
                continue
            left = self._LEFT_WORD.search(text[:ent.start])
            if left and self._looks_like_surname(left.group(1)):
                out.append(Entity("PERSON", text[left.start(1):ent.end],
                                  left.start(1), ent.end,
                                  text[left.start(1):ent.end].lower()))
                continue
            right = self._RIGHT_WORD.match(text[ent.end:])
            if right and self._looks_like_surname(right.group(1)):
                end = ent.end + right.end(1)
                out.append(Entity("PERSON", text[ent.start:end],
                                  ent.start, end, text[ent.start:end].lower()))
        return out

    def is_geography(self, word: str) -> bool:
        """Словарь знает это слово только географическим названием."""
        parses = [p for p in self._morph_vocab.parse(word.capitalize()) if p.is_known]
        return bool(parses) and all("Geox" in p.tag.grammemes for p in parses)

    def known_common_word(self, word: str) -> bool:
        """Словарь знает это слово обычным - не названием и не именем.

        Нужно там, где цена ложной маски высока: "Россия" из "Ромашка
        Россия" не должна закрывать слово "России" по всему документу, а
        "Ромашка", которого словарь не знает вовсе, - должна.
        """
        parses = [p for p in self._morph_vocab.parse(word.capitalize()) if p.is_known]
        if not parses:
            return False
        ok = _NAME_GRAMMEMES | {"Orgn"}
        return not any(g in ok for p in parses for g in p.tag.grammemes)

    def _has_patronymic(self, span: str) -> bool:
        for word in re.findall(r"[А-ЯЁа-яё]+", span):
            if any("Patr" in p.tag.grammemes for p in self._morph_vocab.parse(word)):
                return True
        return False

    def _looks_like_surname(self, word: str) -> bool:
        if word.lower() in STOP_TERMS:
            return False
        parses = self._morph_vocab.parse(word)
        if any(g in _NAME_GRAMMEMES for p in parses for g in p.tag.grammemes):
            return True
        return not any(p.is_known for p in parses)

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

    # Обрывок, а не название: NER склеивает соседние куски через служебные
    # знаки ("PERT + WBS", "Ромашка/Василек НЕ", "АСИ**"). Название организации
    # таких знаков внутри не содержит - кроме дефиса и амперсанда.
    _JUNK_INSIDE = re.compile(r"[+*/\\|]|\*\*")

    # Спан, начинающийся с отглагольного существительного, - это обязанность
    # из резюме ("Организация движения и учета документов", "Полное ведение
    # участка"), а не название. У настоящего названия первое слово - имя
    # собственное или правовая форма.
    _DUTY_HEAD = re.compile(
        r"^(?:полн\w+\s+)?(?:организация|ведение|проведение|подготовка|заключение"
        r"|обучение|консультирование|проверка|контроль|составление|оформление"
        r"|сопровождение|формирование|планирование|управление|взаимодействие"
        r"|обеспечение|разработка|внедрение|сдача|прием|учет|анализ)\b",
        re.IGNORECASE)

    def _is_junk_span(self, ent: Entity) -> bool:
        if self._DUTY_HEAD.match(ent.text.strip()):
            return True
        # Спан, начатый глаголом, - строка обязанностей ("Автоматизировал блок
        # адаптации"), а не название. Проверяем морфологией, а не списком:
        # глаголов в резюме столько же, сколько достижений.
        first = re.match(r"[А-ЯЁA-Za-zа-яё]+", ent.text.strip())
        if first:
            parses = [p for p in self._morph_vocab.parse(first.group().lower())
                      if p.is_known]
            if parses and all(p.tag.POS in {"VERB", "INFN"} for p in parses):
                return True
        if self._JUNK_INSIDE.search(ent.text):
            return True
        # Слово (или все слова) капсом, которые словарь знает обычными словами:
        # заголовки резюме - "РЕШЕНИЕ", "ОТКЛОНЕНА", "ПРОЕКТОВ". Незнакомое
        # словарю слово капсом не трогаем - это может быть аббревиатура-название.
        words = re.findall(r"[А-ЯЁ]{2,}", ent.text)
        if words and words == re.findall(r"[А-ЯЁа-яёA-Za-z]+", ent.text):
            known_common = []
            for word in words:
                parses = [p for p in self._morph_vocab.parse(word.capitalize())
                          if p.is_known]
                # Orgn - пометка словаря "название организации": так размечены
                # названия, давно вошедшие в словарь. Без
                # этой оговорки чистка съедала настоящего работодателя.
                ok = _NAME_GRAMMEMES | {"Orgn"}
                known_common.append(bool(parses) and not any(
                    g in ok for p in parses for g in p.tag.grammemes))
            if all(known_common):
                return True
        return False

    # Строка перечня инструментов. Работодателей в ней не бывает, а инструментов
    # столько, что стоп-список за ними не поспевает: на резюме аналитика в маски
    # ушли Looker, Grafana, Greenplum, Trino, Airflow, Miro за один прогон.
    # Заголовок бывает распространенным: не только "Стек:", но и "Инструменты
    # аналитики и визуализации:", "Технологии хранения и обработки данных:".
    _STACK_LINE = re.compile(
        # Без "^": match() и так привязывает к позиции, а "^" на ней НЕ
        # совпадает - только в начале строки текста. На этом правило молча не
        # срабатывало, хотя заголовок был прямо перед спаном.
        r"[ \t>*-]*(?:стек|навыки|инструменты|технологии|hard skills|tech stack"
        r"|владею|знание инструментов|дополнительно|языки и библиотеки"
        r"|базы данных|бд|аналитика|визуализация)[^:\n]{0,60}[:：]", re.IGNORECASE)

    def _in_stack_line(self, text: str, ent: Entity) -> bool:
        start = text.rfind("\n", 0, ent.start) + 1
        return bool(self._STACK_LINE.match(text, start))

    def _plausible(self, ent: Entity) -> bool:
        if self._is_junk_span(ent):
            return False
        # Географическое название - не человек. Прецедент: "России" из
        # "университет имени первого Президента России" уходило в маску
        # персоной, и в документе появлялся несуществующий сотрудник.
        # Тип LOC у нас свой и по умолчанию не маскируется - решает его
        # правило, а не эта проверка.
        if ent.type == "PERSON" and " " not in ent.text.strip():
            parses = [p for p in self._morph_vocab.parse(ent.text.strip().capitalize())
                      if p.is_known]
            if parses and all("Geox" in p.tag.grammemes for p in parses):
                return False

        """Отсев заведомого мусора NER на верстке резюме и выгрузок.

        Три правила, от общего к частному:

        1. Спан через перенос строки - не сущность. В колоночной верстке NER
           склеивал полстраницы в одну "организацию": от названия факультета до
           списка языков.
        2. Однословная персона, которую словарь знает как обычное слово, -
           не персона: "Аналитик", "Желаемая", "Транскрипт". Слово, которого в
           словаре нет вовсе, оставляем персоной - экзотическое имя дороже
           лишней маски.
        3. Многословная персона без единой граммемы имени - не персона:
           номенклатура товара ("ГИДРОПЛЕКС Тушь", "Крем АКВАЛЮКС"). См.
           _looks_like_fio.
        4. Термин из STOP_TERMS - служебное слово верстки, а не сущность.
           Сравнивается и целиком, и по голове составного термина (см. _TERM_TAIL).
        """
        if "\n" in ent.text:
            return False
        if _is_stop_term(ent.text):
            return False
        if ent.type == "PERSON":
            tokens = ent.text.split()
            if len(tokens) == 1:
                parses = self._morph_vocab.parse(ent.text)
                if any(p.is_known for p in parses):
                    return any(g in _NAME_GRAMMEMES for p in parses for g in p.tag.grammemes)
            elif not self._looks_like_fio(tokens):
                return False
        return True

    def looks_like_person(self, text: str) -> bool:
        """Похож ли спан на ФИО живого человека, а не на марку товара.

        Требование строже, чем у _looks_like_fio: там мы лишь отсеиваем явную
        номенклатуру, а здесь спрашиваем положительный признак - хотя бы один
        токен, который словарь знает как имя, фамилию или отчество. Одиночная
        незнакомая марка признака не даёт и человеком не считается.

        Включается флагом (Masker.ner_person_needs_fio) и только там, где текст
        заведомо не о людях - номенклатура товаров, артикулы. В обычном тексте
        правило вредно: экзотическая фамилия тоже не даёт признака.
        """
        for token in text.split():
            known = [p for p in self._morph_vocab.parse(token) if p.is_known]
            if any(g in _NAME_GRAMMEMES for p in known for g in p.tag.grammemes):
                return True
        return False

    def _looks_like_fio(self, tokens: list[str]) -> bool:
        """Похож ли многословный спан на ФИО, а не на название товара.

        Настоящее ФИО опознается по граммемам хотя бы одного токена: имя,
        фамилия или отчество. Если их нет НИ У ОДНОГО токена, а хотя бы один
        словарь знает как обычное слово - это номенклатура, а не человек:
        "ГИДРОПЛЕКС Тушь", "Крем АКВАЛЮКС", "Крем-мыло Ромашка".

        Проверка идет по всему спану, а не по каждому токену отдельно, ровно
        ради обратного случая: фамилия, совпадающая с обычным словом ("Шапка
        Иван Петрович"), остается человеком - граммемы есть у соседей.

        Спан целиком из слов, которых словарь не знает, оставляем человеком:
        экзотическое имя дороже лишней маски - тот же довод, что у
        однословного правила выше.

        Граммемы берутся только у ИЗВЕСТНЫХ разборов. У незнакомого слова
        pymorphy предсказывает их по суффиксу, и предсказание бывает уверенно
        неверным: "ГИДРОПЛЕКС" он размечает как имя, после чего "ГИДРОПЛЕКС Тушь"
        проходит за человека.
        """
        known_common = False
        for token in tokens:
            known = [p for p in self._morph_vocab.parse(token) if p.is_known]
            if any(g in _NAME_GRAMMEMES for p in known for g in p.tag.grammemes):
                return True
            if known:
                known_common = True
        return not known_common

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
