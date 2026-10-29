import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servicos.comum import fila, llm
from servicos.comum.circuit_breaker import CircuitBreaker
from servicos.geracao import app as geracao
from servicos.ingestao import app as ingestao
from servicos.ingestao import armazenamento
from servicos.recuperacao import app as recuperacao
from servicos.worker import app as worker

from tests.support import RedisEmMemoria, RespostaHTTP


class PipelineRagTests(unittest.TestCase):
    def test_persistencia_fila_worker_recuperacao_e_pergunta(self):
        """Fluxo completo: pergunta recebe resposta baseada nos documentos."""
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

        origens = [fonte["origem"] for fonte in pergunta["fontes"]]
        self.assertIn("teorema_cap.txt", origens)
        self.assertIn("particao de rede", pergunta["contexto"][0])
        self.assertIn("MODO SIMULADO", pergunta["resposta"])
        self.assertFalse(pergunta["degradado"])
        self.assertEqual(pergunta["avaliacao"]["nota"], "boa")
