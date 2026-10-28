"""Worker que consome buscas da fila e consulta o servico de recuperacao."""
import json
import logging
import os
import time

import requests
from redis import Redis
from redis.exceptions import RedisError

from servicos.comum.fila import NOME_FILA_BUSCA, TEMPO_VIDA_RESPOSTA

log = logging.getLogger("worker.recuperacao")
URL_RECUPERACAO = os.getenv(
    "URL_RECUPERACAO", "http://localhost:8002")
URL_REDIS = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def processar_mensagem(cliente: Redis, mensagem: str) -> None:
    try:
        tarefa = json.loads(mensagem)
        pergunta = tarefa["pergunta"]
        fila_resposta = tarefa["fila_resposta"]
        if not isinstance(pergunta, str) or not isinstance(fila_resposta, str):
            raise ValueError("campos da tarefa precisam ser textos")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        log.exception("mensagem invalida removida da fila")
        return

    try:
        resposta = requests.post(
            f"{URL_RECUPERACAO}/buscar",
            json={"pergunta": pergunta, "top_k": 3},
            timeout=10,
        )
        resposta.raise_for_status()
        resultados = resposta.json()["resultados"]
        if not isinstance(resultados, list):
            raise ValueError("recuperacao nao retornou uma lista de resultados")
        payload = {"resultados": resultados}
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        log.exception("falha ao recuperar contexto para uma tarefa")
        payload = {
            "erro": f"falha no servico de recuperacao ({type(e).__name__})"
        }

    cliente.lpush(fila_resposta, json.dumps(payload))
    cliente.expire(fila_resposta, TEMPO_VIDA_RESPOSTA)


def executar() -> None:
    cliente = Redis.from_url(URL_REDIS, decode_responses=True,
                             socket_connect_timeout=3)
    log.info("worker consumindo a fila %s", NOME_FILA_BUSCA)
    while True:
        try:
            tarefa = cliente.blpop(NOME_FILA_BUSCA, timeout=5)
            if tarefa is not None:
                processar_mensagem(cliente, tarefa[1])
        except RedisError:
            log.exception("Redis indisponivel; nova tentativa em 2 segundos")
            time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    executar()
