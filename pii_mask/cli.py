"""CLI: pii-mask mask|unmask|serve.

Пайплайн транскриптов:
    pii-mask mask встреча.md              -> встреча.masked.md + встреча.mapping.json
    <masked уходит в облачную LLM, ответ сохраняется в answer.md>
    pii-mask unmask answer.md --mapping встреча.mapping.json

mapping-файл содержит оригиналы ПД: права 600, в git не коммитить (*.mapping.json
в .gitignore), удалять вместе с задачей.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core import DEFAULT_TYPES, Masker


def _read(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def _write(dst: str | None, content: str) -> None:
    if dst is None or dst == "-":
        sys.stdout.write(content)
        return
    Path(dst).write_text(content, encoding="utf-8")


def _load_mapping(path: str | None) -> dict | None:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return None


def _save_mapping(path: str, mapping: dict) -> None:
    p = Path(path)
    p.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(p, 0o600)


def cmd_mask(args: argparse.Namespace) -> int:
    if args.file == "-" and not args.mapping:
        print("для stdin обязателен --mapping", file=sys.stderr)
        return 2

    stem = None if args.file == "-" else Path(args.file).with_suffix("")
    out = args.output or (f"{stem}.masked.md" if stem else None)
    mapping_path = args.mapping or f"{stem}.mapping.json"

    types = tuple(t.strip().upper() for t in args.types.split(",")) if args.types else DEFAULT_TYPES
    org_names = ()
    if getattr(args, "org_dict", None):
        from .recognizers import load_org_dict

        org_names = load_org_dict(args.org_dict)
    masker = Masker(types=types, ner=not args.no_ner, org_names=org_names)
    text = _read(args.file)
    mapping = _load_mapping(mapping_path)  # существующий mapping продолжаем

    if args.audit:
        masked, mapping = masker.mask_with_audit(text, mapping)
    else:
        masked, mapping = masker.mask(text, mapping)

    _write(out, masked)
    _save_mapping(mapping_path, mapping)
    n = len(mapping["labels"])
    print(f"замаскировано сущностей: {n}; mapping: {mapping_path}", file=sys.stderr)

    # Сколько записей словаря реально сработало. Без этой строки запись, не давшая
    # ни одного совпадения, ничем себя не выдает: словарь молчит одинаково и когда
    # он подошел к документу, и когда его составили не под этот текст.
    if org_names:
        used = {rec["key"] for rec in mapping["labels"].values() if rec["type"] == "ORG"}
        hit = [nm for nm in org_names if " ".join(nm.lower().split()) in used]
        print(f"словарь организаций: сработало {len(hit)} из {len(org_names)}", file=sys.stderr)
        if len(hit) < len(org_names):
            idle = [nm for nm in org_names if nm not in hit]
            shown = ", ".join(idle[:5]) + (f" и еще {len(idle) - 5}" if len(idle) > 5 else "")
            print(f"  не встретились в тексте: {shown}", file=sys.stderr)
    return 0


def cmd_unmask(args: argparse.Namespace) -> int:
    mapping = _load_mapping(args.mapping)
    if mapping is None:
        print(f"mapping не найден: {args.mapping}", file=sys.stderr)
        return 2
    restored = Masker(ner=False).unmask(_read(args.file), mapping)
    _write(args.output, restored)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="pii-mask", description="Маскировка ПД перед облачной LLM")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("mask", help="замаскировать файл или stdin (-)")
    p.add_argument("file")
    p.add_argument("-o", "--output", help="куда писать masked (дефолт <stem>.masked.md, для stdin - stdout)")
    p.add_argument("--mapping", help="файл mapping (дефолт <stem>.mapping.json; существующий продолжается)")
    p.add_argument("--audit", action="store_true", help="второй проход локальной LLM (Ollama)")
    p.add_argument("--no-ner", action="store_true", help="без Natasha NER (только форматные ПД)")
    p.add_argument("--types", help=f"типы через запятую (дефолт {','.join(DEFAULT_TYPES)})")
    p.add_argument("--org-dict", dest="org_dict",
                   help="файл со списком названий организаций (по одному на строку); "
                        "нужен там, где у названия нет ни кавычек, ни орг-формы")
    p.set_defaults(func=cmd_mask)

    p = sub.add_parser("unmask", help="вернуть оригиналы в ответ модели")
    p.add_argument("file")
    p.add_argument("--mapping", required=True)
    p.add_argument("-o", "--output", help="дефолт stdout")
    p.set_defaults(func=cmd_unmask)

    p = sub.add_parser("serve", help="поднять HTTP API (микросервис)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8377)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":  # python -m pii_mask.cli
    main()
