import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from servicos.comum import fila, llm
from servicos.comum.circuit_breaker import CircuitBreaker
from servicos.geracao import app as geracao
from servicos.ingestao import app as ingestao
from servicos.ingestao import armazenamento
from servicos.recuperacao import app as recuperacao
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


class PipelineRagTests(unittest.TestCase):
    def test_persistencia_fila_worker_recuperacao_e_pergunta(self):
        documentos = [
            ingestao.Documento(
                texto="O teorema CAP exige escolher consistencia ou "
                      "disponibilidade durante uma particao de rede.",
                origem="teorema_cap.txt",
            ),
            ingestao.Documento(
                texto="Raft usa eleicao de lider e log replicado para "
                      "consenso distribuido.",
                origem="consenso_raft.txt",
            ),
        ]

        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "indice.joblib"
            salvar = armazenamento.salvar
            with (
                patch.object(
                    ingestao,
                    "ESTADO",
                    {"versao": 0, "documentos": [], "vetorizador": None},
                ),
                patch.object(
                    armazenamento,
                    "salvar",
                    side_effect=lambda estado: salvar(estado, str(caminho)),
                ),
            ):
                indexacao = ingestao.indexar(documentos)

            self.assertEqual(indexacao["indexados"], 2)
            estado_salvo = armazenamento.carregar(str(caminho))
            self.assertEqual(estado_salvo["versao"], 1)
            with patch.object(ingestao, "ESTADO", estado_salvo):
                indice_salvo = ingestao.indice()
                saude_ingestao = ingestao.saude()

            def obter_ingestao(url, timeout):
                corpo = (saude_ingestao if url.endswith("/saude")
                         else indice_salvo)
                return RespostaHTTP(corpo)

            redis_falso = RedisEmMemoria()

            def chamar_recuperacao(url, json, timeout):
                resultado = recuperacao.buscar(
                    recuperacao.Consulta(**json))
                return RespostaHTTP(resultado)

            with (
                patch.object(recuperacao, "CACHE", None),
                patch.object(recuperacao, "URL_INGESTAO", "http://ingestao"),
                patch.object(
                    recuperacao.requests,
                    "get",
                    side_effect=obter_ingestao,
                ),
                patch.object(
                    worker.requests,
                    "post",
                    side_effect=chamar_recuperacao,
                ),
                patch.object(fila, "_cliente_redis", return_value=redis_falso),
                patch.object(llm, "API_KEY", ""),
                patch.object(llm, "FORCAR_FALHA", False),
                patch.object(geracao, "disjuntor", CircuitBreaker()),
                patch.object(
                    geracao,
                    "disjuntor_busca",
                    CircuitBreaker(),
                ),
            ):
                pergunta = geracao.perguntar(
                    geracao.Pergunta(
                        pergunta="O que CAP diz sobre particao de rede?"
                    )
                )

        self.assertIn("teorema_cap.txt", [f["origem"] for f in pergunta["fontes"]])
        self.assertIn("particao de rede", pergunta["contexto"][0])
        self.assertIn("MODO SIMULADO", pergunta["resposta"])
        self.assertFalse(pergunta["degradado"])
        self.assertEqual(pergunta["avaliacao"]["nota"], "boa")

    def test_disjuntor_aberto_retorna_503(self):
        disjuntor = CircuitBreaker(limite_falhas=3, espera_segundos=60)

        def falhar():
            raise RuntimeError("falha simulada")

        for _ in range(3):
            with self.assertRaises(RuntimeError):
                disjuntor.chamar(falhar)

        with (
            patch.object(geracao, "disjuntor", disjuntor),
            patch.object(
                geracao,
                "disjuntor_busca",
                CircuitBreaker(),
            ),
            patch.object(
                geracao,
                "solicitar_busca",
                return_value=[{
                    "texto": "O teorema CAP trata de consistencia.",
                    "origem": "teorema_cap.txt",
                    "score": 0.8,
                }],
            ),
        ):
            with self.assertRaises(HTTPException) as erro:
                geracao.perguntar(geracao.Pergunta(pergunta="O que e CAP?"))

        self.assertEqual(erro.exception.status_code, 503)
        self.assertIn("Retry-After", erro.exception.headers)

    def test_llm_envia_chave_configurada(self):
        with (
            patch.object(llm, "API_KEY", "chave-de-teste"),
            patch.object(llm, "FORCAR_FALHA", False),
            patch.object(
                llm.requests,
                "post",
                return_value=RespostaHTTP({
                    "choices": [{"message": {"content": "resposta"}}]
                }),
            ) as requisicao,
        ):
            resultado = llm._chamar_api("prompt")

        self.assertEqual(resultado, "resposta")
        self.assertEqual(
            requisicao.call_args.kwargs["headers"]["Authorization"],
            "Bearer chave-de-teste",
        )


if __name__ == "__main__":
    unittest.main()
