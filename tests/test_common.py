"""Testes de common (retry e carregamento de credenciais)."""
import pytest
from googleapiclient.errors import HttpError

import common


class FakeRequest:
    """Simula um request do google-api-python-client.

    `behaviors` é uma lista: cada item é o valor a retornar ou uma exceção
    a levantar, na ordem das chamadas a .execute().
    """

    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.calls = 0

    def execute(self, num_retries=0):
        comportamento = self.behaviors[self.calls]
        self.calls += 1
        if isinstance(comportamento, Exception):
            raise comportamento
        return comportamento


def _http_error(status):
    resp = type("Resp", (), {"status": status, "reason": "x"})()
    return HttpError(resp, b"erro")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Evita esperas reais de backoff durante os testes."""
    monkeypatch.setattr(common.time, "sleep", lambda *_: None)


def test_sucesso_primeira_tentativa():
    req = FakeRequest([42])
    assert common.execute_with_retries(req) == 42
    assert req.calls == 1


def test_retry_em_erro_de_rede_e_sucesso():
    req = FakeRequest([TimeoutError(), 99])
    assert common.execute_with_retries(req) == 99
    assert req.calls == 2


def test_retry_em_http_5xx_e_sucesso():
    req = FakeRequest([_http_error(503), "ok"])
    assert common.execute_with_retries(req) == "ok"
    assert req.calls == 2


def test_http_nao_retryable_levanta_imediatamente():
    req = FakeRequest([_http_error(404), "nunca"])
    with pytest.raises(HttpError):
        common.execute_with_retries(req)
    assert req.calls == 1  # não tentou de novo


def test_esgota_tentativas(monkeypatch):
    monkeypatch.setattr(common, "API_MAX_RETRIES", 3)
    req = FakeRequest([TimeoutError(), TimeoutError(), TimeoutError()])
    with pytest.raises(TimeoutError):
        common.execute_with_retries(req)
    assert req.calls == 3


def test_load_credentials_sem_fonte_levanta(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_B64", raising=False)
    monkeypatch.setattr(common, "LOCAL_CREDENTIALS_FILE", str(tmp_path / "nao_existe.json"))
    with pytest.raises(FileNotFoundError):
        common.load_service_account_credentials(["scope"])
