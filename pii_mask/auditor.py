"""LLM-аудитор recall (опциональный): второй проход по уже замаскированному тексту.

Роль строго ограничена: локальная модель через Ollama только ПРЕДЛАГАЕТ кандидатов
("в тексте остались вот такие ПД"), найденное литеральным вхождением проверяется
кодом и уходит в обычный пайплайн масок. Модель никогда не переписывает текст.

Ловит то, что regex и NER пропускают: косвенные упоминания ("моя жена Оля"),
адреса без формата, ники, названия без орг-формы.
"""
from __future__ import annotations

import json
import logging
import os

import httpx

from .recognizers import Entity

log = logging.getLogger("pii_mask.auditor")

OLLAMA_URL = os.environ.get("PII_MASK_OLLAMA_URL", "http://127.0.0.1:11434")
AUDITOR_MODEL = os.environ.get("PII_MASK_AUDITOR_MODEL", "qwen3:1.7b")
CHUNK_CHARS = 2500  # под маленький контекст CPU-модели

_ALLOWED_TYPES = {"PERSON", "ORG", "PHONE", "EMAIL", "ADDRESS", "NICKNAME", "OTHER"}
# ADDRESS/NICKNAME/OTHER схлопываем в PERSON-подобную метку не по типу, а по факту:
# для маскировки важен сам спан, тип влияет только на имя метки.
_TYPE_FALLBACK = {"ADDRESS": "LOC", "NICKNAME": "TG", "OTHER": "PERSON"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string"},
                },
                "required": ["text", "type"],
            },
        }
    },
    "required": ["entities"],
}

_PROMPT = """Ты аудитор персональных данных. Ниже фрагмент рабочего текста, в котором персданные УЖЕ заменены на метки {{TYPE_N}}, фейковые телефоны +7 000 ... и адреса userN@example.com. Найди персональные данные, которые ОСТАЛИСЬ незамаскированными: имена и фамилии людей, названия компаний, телефоны, email, домашние адреса, ники и логины.

Правила:
- Верни JSON: {"entities": [{"text": "...", "type": "PERSON|ORG|PHONE|EMAIL|ADDRESS|NICKNAME|OTHER"}]}.
- В text копируй подстроку ИЗ ТЕКСТА ДОСЛОВНО, без изменений.
- Метки {{...}}, фейковые +7 000 и userN@example.com не включай - они уже замаскированы.
- Должности, роли, города, даты, деньги, технологии - НЕ персданные, не включай.
- Если ничего не осталось - верни {"entities": []}.

Текст:
"""


def ollama_alive(timeout: float = 3.0) -> bool:
    try:
        httpx.get(f"{OLLAMA_URL}/api/version", timeout=timeout).raise_for_status()
        return True
    except Exception:
        return False


def _chunks(text: str) -> list[str]:
    parts, buf, size = [], [], 0
    for para in text.split("\n\n"):
        if size + len(para) > CHUNK_CHARS and buf:
            parts.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 2
    if buf:
        parts.append("\n\n".join(buf))
    return parts


def audit(masked_text: str, timeout: float = 600.0) -> list[Entity]:
    """Вернуть кандидатов, найденных локальной LLM в уже замаскированном тексте."""
    found: list[Entity] = []
    with httpx.Client(timeout=timeout) as client:
        for chunk in _chunks(masked_text):
            try:
                resp = client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": AUDITOR_MODEL,
                        "messages": [{"role": "user", "content": _PROMPT + chunk}],
                        "format": _SCHEMA,
                        "stream": False,
                        "options": {"temperature": 0},
                    },
                )
                resp.raise_for_status()
                data = json.loads(resp.json()["message"]["content"])
            except Exception as exc:  # аудит - улучшение recall, не точка отказа
                log.warning("auditor chunk failed: %s", exc)
                continue
            for item in data.get("entities", []):
                literal = str(item.get("text", "")).strip()
                etype = str(item.get("type", "OTHER")).upper()
                if not literal or len(literal) < 2 or etype not in _ALLOWED_TYPES:
                    continue
                etype = _TYPE_FALLBACK.get(etype, etype)
                # только литеральные вхождения: модель не источник истины по офсетам
                start = masked_text.find(literal)
                while start != -1:
                    found.append(Entity(etype, literal, start, start + len(literal), literal.lower()))
                    start = masked_text.find(literal, start + 1)
    return found
