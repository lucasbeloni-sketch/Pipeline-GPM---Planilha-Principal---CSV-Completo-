"""
Utilitários compartilhados pelos scripts do pipeline.

Centraliza o que era duplicado entre os três compiladores:
- configuração de logging;
- carregamento das credenciais da service account (secret ou arquivo local);
- execução de requisições do google-api-python-client com retry/backoff.

O retry baseado em callable usado pelo bloco3 (gspread) é mantido naquele
script, pois depende de outra biblioteca e de outra assinatura.
"""

import os
import sys
import json
import time
import base64
import socket
import logging

from google.oauth2.service_account import Credentials
from googleapiclient.errors import HttpError


def setup_logging(level=logging.INFO) -> None:
    """
    Configura o logging para stdout com nível e horário. Idempotente:
    chamadas repetidas (ou de múltiplos scripts) não duplicam handlers.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Silencia ruído INFO de bibliotecas de terceiros (ex.: a mensagem
    # "file_cache is only supported with oauth2client<4.0.0" do googleapiclient).
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)


# Configura o logging assim que o módulo é importado, garantindo que mesmo
# logs de nível de módulo dos scripts sejam capturados.
setup_logging()

# Caminho do arquivo de credenciais para execução local.
# Honra GOOGLE_APPLICATION_CREDENTIALS quando definido (padrão do bloco3).
LOCAL_CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")

API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "300"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "5"))

# Evita travas indefinidas em chamadas de rede.
socket.setdefaulttimeout(API_TIMEOUT_SECONDS)


def load_service_account_credentials(scopes) -> Credentials:
    """
    Carrega credenciais da service account de duas formas:
    1) Secret GOOGLE_CREDENTIALS_B64 (usado no GitHub Actions);
    2) Arquivo local service_account.json (ou GOOGLE_APPLICATION_CREDENTIALS),
       para testes locais.
    """
    credentials_b64 = os.getenv("GOOGLE_CREDENTIALS_B64", "").strip()
    if credentials_b64:
        logging.info("Usando credenciais da variável GOOGLE_CREDENTIALS_B64...")
        info = json.loads(base64.b64decode(credentials_b64).decode("utf-8"))
        return Credentials.from_service_account_info(info, scopes=scopes)

    if os.path.exists(LOCAL_CREDENTIALS_FILE):
        logging.info(f"Usando credenciais do arquivo local: {LOCAL_CREDENTIALS_FILE}")
        return Credentials.from_service_account_file(LOCAL_CREDENTIALS_FILE, scopes=scopes)

    raise FileNotFoundError(
        "Credenciais não encontradas. Defina GOOGLE_CREDENTIALS_B64 "
        f"ou adicione {LOCAL_CREDENTIALS_FILE}."
    )


def execute_with_retries(request, description: str = "requisição"):
    """
    Executa uma requisição do google-api-python-client com retry e backoff
    exponencial para erros transitórios (429/5xx) e timeouts de rede.
    """
    last_error = None
    for attempt in range(API_MAX_RETRIES):
        try:
            return request.execute(num_retries=2)
        except HttpError as e:
            last_error = e
            status = getattr(e.resp, "status", None)
            retryable = status in {429, 500, 502, 503, 504}
            if not retryable or attempt == API_MAX_RETRIES - 1:
                raise
            wait_seconds = 2 ** attempt
            logging.warning(f"Falha HTTP em {description} (status={status}). Tentando novamente em {wait_seconds}s...")
            time.sleep(wait_seconds)
        except (TimeoutError, socket.timeout, OSError) as e:
            last_error = e
            if attempt == API_MAX_RETRIES - 1:
                raise
            wait_seconds = 2 ** attempt
            logging.warning(f"Timeout/erro de rede em {description}. Tentando novamente em {wait_seconds}s...")
            time.sleep(wait_seconds)
    raise last_error
