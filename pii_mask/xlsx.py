"""Маскировка книги Excel (.xlsx) без внешних зависимостей.

Книга - это zip с XML внутри, и текст в ней живет не только в ячейках:

- общая таблица строк `xl/sharedStrings.xml` (`<si>`) - так пишет 1С и почти все;
- инлайн прямо в листе (`<is>`) - реже, но встречается;
- комментарии к ячейкам (`xl/comments*.xml`) - текст и имя автора;
- печатные колонтитулы и текст цепочек примечаний;
- свойства файла (`docProps/core.xml`, `app.xml`, `custom.xml`).

Текст маскируется, сведения об авторах и строковые свойства очищаются без
реестра. Числа, даты и формулы не трогаются: порча числа тихо ломает свод.
Кэш формул может содержать ПД и пока не обрабатывается.

**Незнакомая часть с текстом - отказ, а не пропуск.** Надпись на диаграмме или
текстовое поле мы обезличивать не умеем; молча скопировать такую часть значит
выпустить ПД наружу без единой ошибки - ровно тот тихий отказ, ради которого
инструмент и существует. Поэтому `mask_workbook` останавливается и называет
часть. Чего инструмент по-прежнему НЕ трогает - названия листов: они лежат
атрибутом в `xl/workbook.xml`, и на них ссылаются формулы, так что переименование
книгу ломает.

Правки точечные, по текстовым узлам, и только там, где значение изменилось:
остальные части и неизменившиеся ячейки копируются байт в байт. Пересборка
книги через разбор и повторную сериализацию всего XML переставляет атрибуты и
объявления пространств имен, после чего Excel может отказаться открывать файл.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from .office_xml import (T_RE as _T_RE, clear_attrs, escape as _escape,
                         mask_values, runs_text, tag as _tag, unknown_text_parts,
                         unescape as _unescape, write_copy)

# Контейнеры текстовых узлов <t>: ячейка общей таблицы, ячейка листа, комментарий.
# Автор комментария хранится отдельным узлом, без <t>.
_ITEM_RE = {k: re.compile(_tag(k), re.S) for k in ("si", "is", "text", "author")}
# Колонтитул печати листа и текст цепочки примечаний - строкой, без <t>.
_ITEM_RE["hf"] = re.compile(_tag("(?:odd|even|first)(?:Header|Footer)"), re.S)
_ITEM_RE["tc"] = _ITEM_RE["text"]
_PLAIN = {"author", "hf", "tc"}

# Коды колонтитула: &L &C &R (часть), &P &N &D (поля), &"Шрифт,Жирный", &12, &KFF0000.
# Маскируем только текст между ними: "&LСоколова" распознаватель как имя не увидит.
_HF_CODE_RE = re.compile(r'(&(?:"[^"]*"|\d+|K[0-9A-Fa-f]{6}|K\d\d[+-]\d{3}|.))', re.S)

# Части, где мы умеем читать текст, в порядке обхода. Лист не обязан называться sheet1.xml.
_PART_KINDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^xl/sharedStrings\.xml$"), "si"),
    (re.compile(r"^xl/worksheets/[^/]+\.xml$"), "is"),
    (re.compile(r"^xl/worksheets/[^/]+\.xml$"), "hf"),
    (re.compile(r"^xl/comments\d*\.xml$"), "text"),
    (re.compile(r"^xl/threadedComments/[^/]+\.xml$"), "tc"),
)

# Авторы примечаний: имя и учетная запись.
_PERSONS = re.compile(r"^xl/persons/[^/]+\.xml$")
_PERSON_ATTRS = ("displayName", "userId")

# Части без пользовательского текста: разметка, оформление, связи.
_NO_TEXT = re.compile(
    r"^(\[Content_Types\]\.xml|_rels/|xl/_rels/|xl/styles\.xml|xl/theme/|"
    r"xl/workbook\.xml|xl/calcChain\.xml|xl/sharedStrings\.xml|"
    r"xl/worksheets/|xl/comments\d*\.xml|docProps/)"
)


def _sort_key(name: str) -> tuple:
    """sheet2 раньше sheet10; прочие имена - по алфавиту, но устойчиво."""
    m = re.search(r"(\d+)\.xml$", name)
    return (0, int(m.group(1)), "") if m else (1, 0, name)


def _parts(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Части с текстом и вид контейнера, в устойчивом порядке обхода."""
    out: list[tuple[str, str]] = []
    for rx, kind in _PART_KINDS:
        names = sorted((n for n in z.namelist() if rx.match(n)), key=_sort_key)
        out.extend((n, kind) for n in names)
    return out


def _unknown_text_parts(z: zipfile.ZipFile) -> list[str]:
    """Части с текстом, которые мы не разбираем: диаграммы, надписи, чужое."""
    return unknown_text_parts(z, {n for n, _ in _parts(z)}, _NO_TEXT)


def _item_value(body: bytes, kind: str) -> str:
    if kind in _PLAIN:
        return _unescape(body.decode("utf-8"))
    return runs_text(body)


def _item_values(body: bytes, kind: str) -> list[str]:
    """Значения контейнера для маскировки: у колонтитула - куски текста между кодами."""
    value = _item_value(body, kind)
    return _HF_CODE_RE.split(value)[0::2] if kind == "hf" else [value]


def cell_texts(path: str | Path) -> list[str]:
    """Весь текст книги, который мы умеем обезличивать, в устойчивом порядке."""
    values: list[str] = []
    with zipfile.ZipFile(path) as z:
        parts = _parts(z)
        for name in dict.fromkeys(name for name, _ in parts):
            blob = z.read(name)
            containers = sorted((m.start(), m.end()) for part, kind in parts if part == name
                                for m in _ITEM_RE[kind].finditer(blob))
            container = 0
            for node in _T_RE.finditer(blob):
                if not (node.group(1) or b"").strip():
                    continue
                while container < len(containers) and containers[container][1] <= node.start():
                    container += 1
                if (container == len(containers) or containers[container][0] > node.start()
                        or containers[container][1] < node.end()):
                    raise ValueError("в книге есть текст вне поддерживаемого контейнера: " + name)
        for name, kind in parts:
            for item in _ITEM_RE[kind].finditer(z.read(name)):
                values.extend(_item_values(item.group(1), kind))
    return values


def _rewrite_part(blob: bytes, kind: str, values: list[str], cursor: int) -> tuple[bytes, int]:
    def one(match: re.Match) -> bytes:
        nonlocal cursor
        body = match.group(1)
        old = _item_value(body, kind)
        if kind == "hf":
            pieces = _HF_CODE_RE.split(old)
            n = len(pieces[0::2])
            pieces[0::2], cursor = values[cursor:cursor + n], cursor + n
            new = "".join(pieces)
        else:
            new, cursor = values[cursor], cursor + 1
        whole = match.group(0)
        head = whole[:match.start(1) - match.start(0)]
        tail = whole[match.end(1) - match.start(0):]

        if old == new:
            return whole      # значение не изменилось - оформление цело

        payload = _escape(new).encode("utf-8")
        if kind in _PLAIN:
            return head + payload + tail

        first = True

        def run(_t: re.Match) -> bytes:
            nonlocal first
            name = _t.group(0)[1:].split(None, 1)[0].split(b">", 1)[0].rstrip(b"/")
            if not first:
                return b"<" + name + b"/>"      # весь текст ячейки пишем в первый узел
            first = False
            return b"<" + name + b' xml:space="preserve">' + payload + b"</" + name + b">"

        return head + _T_RE.sub(run, body) + tail

    return _ITEM_RE[kind].sub(one, blob), cursor


def rewrite(src: str | Path, dst: str | Path, values: list[str]) -> None:
    """Собрать копию книги с подставленными значениями.

    `values` - ровно то, что вернул `cell_texts` для этой же книги, в том же
    порядке. Рассинхрон длины - это сдвиг подстановки по всей книге, поэтому он
    ошибка, а не повод обрезать по короткому списку.
    """
    src, dst = Path(src), Path(dst)
    if dst.exists() and src.samefile(dst):
        # Запись открывает тот же путь на "w" и обнуляет его ДО первого чтения:
        # книга уничтожалась целиком, а падало уже на усечённом архиве.
        raise ValueError("нельзя писать поверх исходной книги - укажи другой файл")
    have = cell_texts(src)
    if len(values) != len(have):
        raise ValueError(
            f"значений {len(values)}, а текстовых узлов в книге {len(have)} - "
            "подстановка сдвинулась бы по всей книге")

    cursor = 0
    with zipfile.ZipFile(src) as zin:
        # Курсор обязан идти в том же порядке, в котором значения отдал
        # cell_texts, а порядок частей в архиве свой - поэтому правим по _parts,
        # накапливая результат, и только потом пишем архив.
        done: dict[str, bytes] = {}
        for name, kind in _parts(zin):
            blob = done.get(name) or zin.read(name)
            blob, cursor = _rewrite_part(blob, kind, values, cursor)
            done[name] = blob
        for name in zin.namelist():
            if _PERSONS.match(name):
                done[name] = clear_attrs(zin.read(name), _PERSON_ATTRS)
            elif re.match(r"^xl/comments\d*\.xml$", name):
                blob = done.get(name, zin.read(name))
                done[name] = _ITEM_RE["author"].sub(
                    lambda m: m.group(0)[:m.start(1) - m.start()] + m.group(0)[m.end(1) - m.start():],
                    blob)
        write_copy(zin, dst, done)


# Правовые формы: по ним книга сама объявляет, кто в ней контрагент.
_LEGAL_FORM = re.compile(
    r"\b(ООО|ЗАО|ОАО|ПАО|НАО|АО|ИП|АНО|НКО|ФГУП|ГУП|МУП|ФГБУ)\b", re.IGNORECASE)
_WORD_SPLIT = re.compile(r"[^\w\-]+")


def supported_names(src: str | Path) -> tuple[str, ...]:
    """Слова из ячеек с правовой формой - имена, которые книга назвала своими.

    Нужны строгому режиму распознавателя: фамилию "Метелина" словарь не знает
    ровно так же, как марку "Аквабрис", и отличает их только документ. Ячейка
    "ИП Метелина Лилия Вячеславовна" объявляет Метелину контрагентом, и дальше
    фамилия маскируется даже там, где стоит одна. Рядом с маркой правовой формы
    нет нигде в книге, поэтому в список она не попадает.
    """
    names: set[str] = set()
    for value in cell_texts(src):
        if not _LEGAL_FORM.search(value):
            continue
        for word in _WORD_SPLIT.split(value):
            if len(word) >= 3 and not word.isdigit() and not _LEGAL_FORM.fullmatch(word):
                names.add(word.lower())
    return tuple(sorted(names))


# Ячейка листа с координатой. Значение либо ссылка в общую таблицу (t="s"),
# либо инлайн (t="inlineStr"), либо число - последнее нас не интересует.
_CELL_RE = re.compile(
    rb'<c\s+r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_V_RE = re.compile(rb"<(?:\w+:)?v>(.*?)</(?:\w+:)?v>", re.S)

# Подписи реквизитов: слово рядом с числом делает число реквизитом.
_REQ_LABEL = re.compile(r"^\s*(ИНН|КПП|ОГРН|ОГРНИП|БИК|СНИЛС|ОКПО|ОКТМО)\s*:?\s*$",
                        re.IGNORECASE)
_DIGITS_ONLY = re.compile(r"^\s*\d{5,20}\s*$")


def _col_num(letters: bytes) -> int:
    n = 0
    for ch in letters.decode():
        n = n * 26 + (ord(ch) - 64)
    return n


def _sheet_grid(z: zipfile.ZipFile, name: str, shared: list[str]) -> dict[tuple[int, int], str]:
    """Текстовые значения листа по координатам (строка, колонка)."""
    grid: dict[tuple[int, int], str] = {}
    for m in _CELL_RE.finditer(z.read(name)):
        col, row, attrs, body = _col_num(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        if body is None:
            continue
        if b't="s"' in attrs:
            v = _V_RE.search(body)
            if v is not None:
                idx = int(v.group(1))
                if 0 <= idx < len(shared):
                    grid[(row, col)] = shared[idx]
        elif b't="inlineStr"' in attrs:
            grid[(row, col)] = _item_value(body, "is")
    return grid


def labelled_numbers(src: str | Path) -> frozenset[str]:
    """Числа, у которых в соседней ячейке стоит подпись реквизита.

    Подпись в бухгалтерских формах живет отдельной ячейкой слева или сверху
    ("A9=ИНН", "B9=6083778353"), а маскировка идет по одной ячейке и соседей не
    видит. Без этой сверки строгий режим отсекал артикулы вместе с настоящими
    реквизитами - одинаковые на вид десятизначные числа.
    """
    out: set[str] = set()
    with zipfile.ZipFile(src) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            blob = z.read("xl/sharedStrings.xml")
            shared = [_item_value(i.group(1), "si") for i in _ITEM_RE["si"].finditer(blob)]
        for name in (n for n in z.namelist() if re.match(r"^xl/worksheets/[^/]+\.xml$", n)):
            grid = _sheet_grid(z, name, shared)
            for (row, col), value in grid.items():
                if not _DIGITS_ONLY.match(value):
                    continue
                left = grid.get((row, col - 1), "")
                above = grid.get((row - 1, col), "")
                if _REQ_LABEL.match(left) or _REQ_LABEL.match(above):
                    out.add(value.strip())
    return frozenset(out)


def mask_workbook(src: str | Path, dst: str | Path, masker, mapping: dict | None = None) -> dict:
    """Замаскировать книгу целиком: на входе .xlsx, на выходе .xlsx и реестр.

    Значения маскируются по одному, а не одной склейкой: распознаватель умеет
    поглощать перенос строки внутри названия, из-за чего число строк меняется, и
    любая схема "склеить и разрезать обратно" разъезжается по ячейкам. Реестр
    при этом общий на всю книгу - одна сущность получает одну метку везде.
    """
    with zipfile.ZipFile(src) as z:
        unknown = _unknown_text_parts(z)
    if unknown:
        raise ValueError(
            "в книге есть текст, который я не умею обезличивать: "
            + ", ".join(unknown)
            + " - скопировать её как есть значит выпустить ПД наружу молча")

    # Строгому режиму нужны опорные имена, а видит книгу целиком только эта
    # функция: маскировщик работает по одной ячейке и соседних не знает.
    if getattr(masker, "ner_person_needs_fio", False) and not masker.supported_names:
        masker.supported_names = frozenset(supported_names(src))
    # То же самое для реквизитов: подпись стоит в соседней ячейке, и увидеть её
    # может только тот, кто смотрит на таблицу целиком.
    if getattr(masker, "inn_needs_label", False) and not masker.trusted_numbers:
        masker.trusted_numbers = labelled_numbers(src)

    masked, mapping = mask_values(cell_texts(src), masker, mapping)
    rewrite(src, dst, masked)
    return mapping
