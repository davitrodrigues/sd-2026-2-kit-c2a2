"""Comunicacao de requisicao/resposta para a busca via fila Redis."""
import json
import os
import uuid

from redis import Redis
from redis.exceptions import RedisError

NOME_FILA_BUSCA = "busca:pendente"
TIMEOUT_SEGUNDOS = int(os.getenv("FILA_TIMEOUT_SEGUNDOS", "30"))
TEMPO_VIDA_RESPOSTA = 60


class ErroFila(Exception):
    """Resposta recebida da fila nao corresponde ao formato esperado."""


class FilaIndisponivel(Exception):
    """Redis nao aceitou ou nao respondeu a uma operacao de fila."""


class FilaTimeout(Exception):
    """Worker nao respondeu dentro do prazo configurado."""


class FalhaNaRecuperacao(Exception):
    """Worker nao conseguiu recuperar os trechos solicitados."""


def _cliente_redis():
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=TIMEOUT_SEGUNDOS + 5,
    )


def solicitar_busca(pergunta: str) -> list:
    """Enfileira a busca e aguarda a resposta do worker correspondente."""
    cliente = _cliente_redis()
    id_requisicao = uuid.uuid4().hex
    fila_resposta = f"busca:resposta:{id_requisicao}"
    mensagem = json.dumps({
        "id": id_requisicao,
        "pergunta": pergunta,
        "fila_resposta": fila_resposta,
    })

    try:
        cliente.rpush(NOME_FILA_BUSCA, mensagem)
        resposta = cliente.blpop(fila_resposta, timeout=TIMEOUT_SEGUNDOS)
    except RedisError as e:
        raise FilaIndisponivel from e
    finally:
        cliente.close()

    if resposta is None:
        raise FilaTimeout

    try:
        payload = json.loads(resposta[1])
    except (IndexError, TypeError, json.JSONDecodeError) as e:
        raise ErroFila("resposta invalida recebida da fila") from e

    if not isinstance(payload, dict):
        raise ErroFila("resposta invalida recebida da fila")
    if "erro" in payload:
        raise FalhaNaRecuperacao(payload["erro"])
    resultados = payload.get("resultados")
    if not isinstance(resultados, list):
        raise ErroFila("resposta da fila nao contem resultados validos")
    return resultados
