import unittest
from unittest.mock import patch

from fastapi import HTTPException

from servicos.comum.circuit_breaker import CircuitBreaker
from servicos.geracao import app as geracao


class ResilienciaTests(unittest.TestCase):
    def test_disjuntor_aberto_retorna_503(self):
        """Resiliencia: disjuntor aberto recusa chamadas com HTTP 503."""
        disjuntor = CircuitBreaker(limite_falhas=3, espera_segundos=60)

        def falhar():
            raise RuntimeError("falha simulada")

        with self.assertLogs("uvicorn.error", level="WARNING") as registros:
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    disjuntor.chamar(falhar)
        self.assertIn("aberto apos 3 falhas", registros.output[0])

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
