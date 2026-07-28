"""Аудитор не должен оставлять модель висеть в памяти после прогона.

Дефолт Ollama - keep_alive 5 минут: после батч-аудита модель занимает
полтора-два гигабайта, которые на маленькой машине нужны другим процессам.
"""
import json

import pii_mask.auditor as auditor


class _FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": json.dumps({"entities": []})}}


class _FakeClient:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, **kw):
        self.calls.append((url, json or {}))
        return _FakeResponse()


def _run(monkeypatch, text):
    calls = []
    monkeypatch.setattr(auditor.httpx, "Client", lambda **kw: _FakeClient(calls))
    auditor.audit(text)
    return calls


def test_client_ignores_environment_proxy(monkeypatch):
    """ALL_PROXY=socks5h://... в окружении не должен вставать между нами и Ollama.

    httpx разворачивает транспорт под прокси при создании клиента, до NO_PROXY,
    и без socksio падает ImportError - а наружу это выглядит как "Ollama недоступна".
    """
    kwargs = {}
    monkeypatch.setattr(auditor.httpx, "Client", lambda **kw: kwargs.update(kw) or _FakeClient([]))
    auditor._client(3.0)
    assert kwargs.get("trust_env") is False


def test_chunk_requests_carry_keep_alive(monkeypatch):
    calls = _run(monkeypatch, "Иван Петров пришел на встречу.")
    chat = [body for url, body in calls if url.endswith("/api/chat")]
    assert chat, "не было ни одного запроса к модели"
    assert all(
        b.get("keep_alive") for b in chat
    ), "keep_alive не задан - остается дефолт Ollama в 5 минут"


def test_model_unloaded_after_audit(monkeypatch):
    calls = _run(monkeypatch, "Иван Петров пришел на встречу.")
    url, body = calls[-1]
    assert body.get("keep_alive") == 0, "последним запросом должна идти выгрузка модели"


def test_unload_failure_does_not_break_audit(monkeypatch):
    """Выгрузка - гигиена памяти, а не часть контракта: ее падение не роняет аудит."""

    class _FailingUnload(_FakeClient):
        def post(self, url, json=None, **kw):
            if (json or {}).get("keep_alive") == 0:
                raise OSError("ollama ушла")
            return super().post(url, json=json, **kw)

    calls = []
    monkeypatch.setattr(auditor.httpx, "Client", lambda **kw: _FailingUnload(calls))
    assert auditor.audit("Иван Петров пришел на встречу.") == []
