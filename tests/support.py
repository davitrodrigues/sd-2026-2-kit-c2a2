"""Fakes compartilhados pelos testes de integracao."""
from servicos.comum import fila
from servicos.worker import app as worker


class RespostaHTTP:
    def __init__(self, corpo):
        self.corpo = corpo
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.corpo


class RedisEmMemoria:
    def __init__(self):
        self.filas = {}

    def rpush(self, nome, mensagem):
        if nome == fila.NOME_FILA_BUSCA:
            worker.processar_mensagem(self, mensagem)
        else:
            self.filas.setdefault(nome, []).append(mensagem)

    def lpush(self, nome, mensagem):
        self.filas.setdefault(nome, []).insert(0, mensagem)

    def blpop(self, nome, timeout):
        mensagens = self.filas.get(nome, [])
        return (nome, mensagens.pop()) if mensagens else None

    def expire(self, nome, segundos):
        return True

    def close(self):
        pass
