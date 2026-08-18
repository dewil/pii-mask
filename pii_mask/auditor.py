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
import re

import httpx

from .recognizers import Entity

log = logging.getLogger("pii_mask.auditor")

OLLAMA_URL = os.environ.get("PII_MASK_OLLAMA_URL", "http://127.0.0.1:11434")
AUDITOR_MODEL = os.environ.get("PII_MASK_AUDITOR_MODEL", "qwen3:1.7b")
CHUNK_CHARS = 2500  # под маленький контекст CPU-модели
# Держим модель загруженной между кусками одного документа, но не дольше:
# дефолт Ollama - 5 минут, и все это время полтора-два гигабайта заняты впустую.
# Ноль здесь был бы хуже дефолта - модель перезагружалась бы на каждом куске.
KEEP_ALIVE = os.environ.get("PII_MASK_KEEP_ALIVE", "60s")

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


def _client(timeout: float) -> httpx.Client:
    """Клиент до Ollama - всегда мимо прокси из окружения.

    Ollama по определению локальная, а `ALL_PROXY=socks5h://...` (типовой случай
    на машине с прокси-каскадом) httpx применяет ко всем схемам и разворачивает
    транспорт прямо при создании клиента - до всякого NO_PROXY. Без socksio это
    ImportError, который выглядит как "Ollama недоступна".
    """
    return httpx.Client(timeout=timeout, trust_env=False)


def ollama_alive(timeout: float = 3.0) -> bool:
    try:
        with _client(timeout) as client:
            client.get(f"{OLLAMA_URL}/api/version").raise_for_status()
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


_morph_vocab = None


def _plausible_candidate(etype: str, text: str) -> bool:
    """Отсев мусора аудитора теми же правилами, что и у NER.

    Маленькая модель щедра на кандидатов: на резюме она предлагала должности
    ("Ведущий системный аналитик", "Аналитик") как персон. Пропустить такое хуже,
    чем не найти ПД: должность превращается в {{PERSON_1}}, и текст перестает
    читаться - ровно тот вред, ради которого в NER заведены STOP_TERMS.

    Два правила:

    1. Родовой термин из STOP_TERMS - не сущность, кто бы его ни предложил.
    2. PERSON обязан содержать слово, похожее на имя: либо словарь знает его как
       имя/фамилию/отчество, либо не знает вовсе (экзотическое имя дороже лишней
       маски). Фраза, целиком состоящая из известных нарицательных, персоной
       не является.

    Проверка морфологическая и модели не грузит: MorphVocab - это словарь pymorphy,
    а не нейросеть NER.
    """
    from .ner import _NAME_GRAMMEMES, _is_stop_term

    if _is_stop_term(text):
        return False
    if etype != "PERSON":
        return True

    # Перечисление через запятую - не человек. Модель охотно отдает целую строку
    # ("Jira, SQL, Python") одной персоной, а маска на списке навыков уничтожает
    # смысл абзаца. Проверяем части: родовой термин хотя бы в одной - и это список,
    # а не имя. Только для PERSON: у организаций запятая перед формой законна
    # ("Ромашка, ООО"), и та же проверка отбросила бы настоящее название.
    parts = [p.strip() for p in text.split(",")]
    if len(parts) > 1 and any(_is_stop_term(p) for p in parts):
        return False

    global _morph_vocab
    if _morph_vocab is None:
        from natasha import MorphVocab

        _morph_vocab = MorphVocab()
    for word in re.findall(r"[^\W\d_]{2,}", text, re.UNICODE):
        parses = _morph_vocab.parse(word.capitalize())
        known = [p for p in parses if p.is_known]
        if not known:
            return True  # слова нет в словаре - может быть редким именем
        if any(g in _NAME_GRAMMEMES for p in known for g in p.tag.grammemes):
            return True
    return False


def audit(masked_text: str, timeout: float = 600.0) -> list[Entity]:
    """Вернуть кандидатов, найденных локальной LLM в уже замаскированном тексте."""
    found: list[Entity] = []
    with _client(timeout) as client:
        for chunk in _chunks(masked_text):
            try:
                resp = client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": AUDITOR_MODEL,
                        "messages": [{"role": "user", "content": _PROMPT + chunk}],
                        "format": _SCHEMA,
                        "stream": False,
                        "think": False,  # для thinking-моделей (qwen3): аудит - экстракция, не рассуждение
                        "keep_alive": KEEP_ALIVE,
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
                if not _plausible_candidate(etype, literal):
                    continue
                # только литеральные вхождения: модель не источник истины по офсетам
                start = masked_text.find(literal)
                while start != -1:
                    found.append(Entity(etype, literal, start, start + len(literal), literal.lower()))
                    start = masked_text.find(literal, start + 1)
        _unload(client)
    return found


def _unload(client) -> None:
    """Выгрузить модель из памяти сразу, не дожидаясь keep_alive.

    Гигиена памяти, а не часть контракта: аудит уже отработал, и падение
    выгрузки не повод терять результат.
    """
    try:
        client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": AUDITOR_MODEL, "keep_alive": 0},
        ).raise_for_status()
    except Exception as exc:
        log.warning("не удалось выгрузить модель: %s", exc)
