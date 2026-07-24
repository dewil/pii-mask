"""HTTP-фасад: roundtrip через API, health, защита от недоступного аудитора."""
from fastapi.testclient import TestClient

from pii_mask.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_mask_unmask_roundtrip():
    src = "Звонил Петр Орлов, тел +7 915 000-11-22"
    r = client.post("/mask", json={"text": src})
    assert r.status_code == 200
    body = r.json()
    assert "Орлов" not in body["masked_text"]
    assert "+7 915 000-11-22" not in body["masked_text"]

    r2 = client.post("/unmask", json={"text": body["masked_text"], "mapping": body["mapping"]})
    assert r2.status_code == 200
    assert "Петр Орлов" in r2.json()["text"]
    assert "+7 915 000-11-22" in r2.json()["text"]


def test_audit_fail_closed(monkeypatch):
    # Ollama лежит + запрошен audit -> 503, а не тихая маскировка без аудита
    import pii_mask.auditor as auditor

    monkeypatch.setattr(auditor, "ollama_alive", lambda *a, **k: False)
    r = client.post("/mask", json={"text": "Иван Петров", "audit": True})
    assert r.status_code == 503
