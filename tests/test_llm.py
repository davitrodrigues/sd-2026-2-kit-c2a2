import unittest
from unittest.mock import patch

from servicos.comum import llm

from tests.support import RespostaHTTP


class LlmTests(unittest.TestCase):
    def test_llm_envia_chave_configurada(self):
        """LLM: usa a chave configurada para autenticar a chamada."""
        chave = "chave-de-teste"
        with (
            patch.object(llm, "API_KEY", chave),
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
        cabecalho = requisicao.call_args.kwargs["headers"]["Authorization"]
        self.assertTrue(cabecalho.startswith("Bearer "))
        self.assertEqual(cabecalho.removeprefix("Bearer "), chave)
