# disjuntor de referencia da aula: protege uma chamada que pode falhar.
#
# fechado deixa passar tudo, aberto recusa na hora sem tentar, e meio deixa
# so uma chamada de teste passar para ver se o servico voltou.
import logging
import threading
import time

log = logging.getLogger("uvicorn.error")


# erro de quando o disjuntor recusa a chamada; diz quanto falta para o teste.
class CircuitoAberto(Exception):

    def __init__(self, mensagem="disjuntor aberto: chamada recusada",
                 restante=0.0):
        super().__init__(mensagem)
        self.restante = restante


class CircuitBreaker:

    # so os erros da lista contam como falha; o resto passa sem contar.
    def __init__(self, limite_falhas=5, espera_segundos=30,
                 conta_como_falha=(Exception,), nome="disjuntor"):
        self.limite_falhas = limite_falhas
        self.espera_segundos = espera_segundos
        self.conta_como_falha = conta_como_falha
        self.nome = nome
        self.falhas = 0
        self._estado = "fechado"
        self.aberto_em = 0.0
        self._teste = None  # marca da chamada de teste que esta rodando
        self._trava = threading.Lock()  # so uma thread mexe no estado

    # le o estado ja contando a espera, mesmo que ninguem tenha chamado.
    @property
    def estado(self):
        with self._trava:
            self._conferir_espera()
            return self._estado

    def chamar(self, funcao, *args, **kwargs):
        with self._trava:
            self._conferir_espera()
            if self._estado == "aberto":
                raise CircuitoAberto(
                    f"{self.nome} aberto: chamada recusada",
                    self.espera_segundos
                    - (time.monotonic() - self.aberto_em))
            teste = None
            if self._estado == "meio":
                if self._teste is not None:
                    raise CircuitoAberto(
                        f"{self.nome} em teste: chamada recusada")
                teste = self._teste = object()
        try:
            resultado = funcao(*args, **kwargs)
        except self.conta_como_falha:
            self._registrar_falha(teste)
            raise
        except BaseException:
            # erro que nao e do servico: so libera a vaga de teste
            with self._trava:
                if teste is not None and self._teste is teste:
                    self._teste = None
            raise
        self._registrar_sucesso()
        return resultado

    # passada a espera, o aberto vira meio e libera uma chamada de teste.
    def _conferir_espera(self):
        if (self._estado == "aberto"
                and time.monotonic() - self.aberto_em
                >= self.espera_segundos):
            self._estado = "meio"
            log.info("%s: espera acabou, deixa uma chamada de teste",
                     self.nome)

    def _registrar_falha(self, teste):
        with self._trava:
            self.falhas += 1
            if self.falhas >= self.limite_falhas or self._estado == "meio":
                if teste is not None:
                    log.warning("%s: chamada de teste falhou, aberto de novo",
                                self.nome)
                elif self._estado == "fechado":
                    log.warning("%s: aberto apos %d falhas seguidas",
                                self.nome, self.falhas)
                self._estado = "aberto"
                self.aberto_em = time.monotonic()
                self._teste = None

    def _registrar_sucesso(self):
        with self._trava:
            if self._estado != "fechado":
                log.info("%s: servico respondeu, fechado de novo", self.nome)
            self.falhas = 0
            self._estado = "fechado"
            self._teste = None
