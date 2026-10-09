"""Общие части для форматов Office Open XML (.docx, .xlsx): zip-архив с XML внутри."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape as _sax_escape

# Ссылки на символы: числовые (`&#10;` - перевод строки в ячейке) и пять именованных из XML.
_REF_RE = re.compile(r"&(?:#x([0-9A-Fa-f]+)|#(\d+)|(amp|lt|gt|quot|apos));")
_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}

# Кавычки ограничивают значение атрибута: символ > внутри них не закрывает тег.
ATTRS = rb'''(?:\s+(?:[^>"']|"[^"]*"|'[^']*')*)?'''
_OPEN_TAG_RE = re.compile(rb"<[\w:.-]+" + ATTRS + rb"/?>")
_XML_TOKEN_RE = re.compile(
    rb"<!\[CDATA\[.*?\]\]>|<!--.*?-->|<\?.*?\?>|(?P<tag>" + _OPEN_TAG_RE.pattern + rb")", re.S)
_ATTRIBUTE_RE = re.compile(
    rb'''(?P<name>[\w:.-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)''', re.S)

# Текстовый узел <t> (в Word - <w:t>), в том числе пустой <t/>: он узел не открывает.
T_RE = re.compile(rb"<(?:\w+:)?t" + ATTRS + rb"(?<!/)>(.*?)</(?:\w+:)?t>|<(?:\w+:)?t" + ATTRS + rb"/>", re.S)
# Любой непустой текстовый узел - чтобы заметить текст в частях, которые мы не разбираем.
ANY_T_RE = re.compile(rb"<(?:\w+:)?t" + ATTRS + rb"(?<!/)>([^<]+)</(?:\w+:)?t>", re.S)

# Свойства файла, где бывают имена: кто сохранил, о чем документ, чья организация.
_PROPERTY_FIELDS = {
    "docProps/core.xml": ("creator", "lastModifiedBy", "title", "subject",
                          "description", "keywords", "category"),
    "docProps/app.xml": ("Company", "Manager"),
    "docProps/custom.xml": ("lpwstr", "lpstr", "bstr"),
}


def unescape(text: str) -> str:
    """Разобрать ссылки на символы за ОДИН проход.

    Последовательная замена (сперва `&amp;`, потом числовые) разбирает результат
    собственной работы: `&amp;#10;` - это литерал `&#10;`, а после двух проходов
    он превратился бы в перевод строки. Один проход слева направо - ровно то,
    что делает настоящий XML-парсер.
    """
    def one(m: re.Match) -> str:
        if m.group(1):
            return chr(int(m.group(1), 16))
        if m.group(2):
            return chr(int(m.group(2)))
        return _NAMED[m.group(3)]

    return _REF_RE.sub(one, text)


def escape(text: str, attr: bool = False) -> str:
    """Экранировать текст узла. `\\r` пишем ссылкой, иначе парсер заменит его на `\\n`.

    В значении атрибута еще кавычку и переводы строк: парсер свернул бы их в пробел.
    """
    if attr:
        return _sax_escape(text, {'"': "&quot;", "'": "&apos;", "\n": "&#10;", "\t": "&#9;", "\r": "&#13;"})
    return _sax_escape(text).replace("\r", "&#13;")


def tag(name: str) -> bytes:
    """Тег с необязательным префиксом пространства имен: `<si>` и `<x:si>`; пустой `<si/>` не в счет."""
    return rb"<(?:\w+:)?" + name.encode() + ATTRS + rb"(?<!/)>(.*?)</(?:\w+:)?" + name.encode() + rb">"


def runs_text(body: bytes) -> str:
    """Текст контейнера: все его узлы <t> подряд."""
    runs = [m.group(1) or b"" for m in T_RE.finditer(body)]
    return unescape(b"".join(runs).decode("utf-8"))


def unknown_text_parts(z: zipfile.ZipFile, known: set[str], no_text: re.Pattern) -> list[str]:
    """Части с текстом, которые мы не разбираем: диаграммы, надписи, чужое."""
    bad = []
    for n in z.namelist():
        if n in known or no_text.match(n) or not n.endswith(".xml"):
            continue
        if any(m.group(1).strip() for m in ANY_T_RE.finditer(z.read(n))):
            bad.append(n)
    return sorted(bad)


def strip_properties(name: str, blob: bytes) -> bytes:
    """Вычистить из свойств файла поля, где бывают имена."""
    fields = _PROPERTY_FIELDS.get(name, ())
    if not fields:
        return blob
    parser = expat.ParserCreate()
    stack: list[int | None] = []
    edits: list[tuple[int, int]] = []

    def start(tag_name: str, _attrs: dict) -> None:
        opening = _OPEN_TAG_RE.match(blob, parser.CurrentByteIndex)
        # Expat reports the end of <tag/> after the tag; it has no body to clear.
        selected = tag_name.split(":")[-1] in fields and not opening.group().endswith(b"/>")
        stack.append(opening.end() if selected else None)

    def end(_tag_name: str) -> None:
        body_start = stack.pop()
        if body_start is not None:
            edits.append((body_start, parser.CurrentByteIndex))

    parser.StartElementHandler, parser.EndElementHandler = start, end
    # Byte offsets preserve all surrounding XML; CDATA contents are never tags.
    parser.Parse(blob, True)
    out, cursor = [], 0
    for start_, end_ in sorted(edits, key=lambda e: (e[0], -e[1])):
        if start_ >= cursor:
            out.append(blob[cursor:start_])
            cursor = end_
    out.append(blob[cursor:])
    return b"".join(out)


def clear_attrs(blob: bytes, names: tuple[str, ...]) -> bytes:
    """Опустошить значения атрибутов с этими именами, с любым префиксом."""
    def attr(m: re.Match) -> bytes:
        if m.group("name").decode().split(":")[-1] not in names:
            return m.group(0)
        return m.group(0)[:m.start("value") - m.start()] + m.group(0)[m.end("value") - m.start():]

    def token(m: re.Match) -> bytes:
        return _ATTRIBUTE_RE.sub(attr, m.group()) if m.group("tag") else m.group()

    # Consume every attribute as a whole; literals inside another value are data.
    return _XML_TOKEN_RE.sub(token, blob)


def write_copy(zin: zipfile.ZipFile, dst: str | Path, done: dict[str, bytes]) -> None:
    """Записать копию архива: части из `done` - новые, прочие - как были, свойства - без имен."""
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            blob = done[info.filename] if info.filename in done else zin.read(info.filename)
            zout.writestr(info, strip_properties(info.filename, blob))


def mask_values(values: list[str], masker, mapping: dict | None) -> tuple[list[str], dict]:
    """Замаскировать значения по порядку; пустые и пробельные - как есть."""
    masked = []
    for value in values:
        if not value.strip():
            masked.append(value)
            continue
        out, mapping = masker.mask(value, mapping)
        masked.append(out)
    return masked, mapping
