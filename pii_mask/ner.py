"""Имена и организации через Natasha (slovnet NER, CPU, офлайн).

Ключ консистентности - нормальная форма спана: все словоформы одной персоны
("Иван Петров", "Ивана Петрова", "Иваном Петровым") дают один key и одну метку.
"""
from __future__ import annotations

from .recognizers import Entity

_TYPE_MAP = {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"}


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
        doc = self._Doc(text)
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
            out.append(Entity(etype, span.text, span.start, span.stop, key))
        return out
