import unittest
from io import StringIO

from tests.__main__ import RunnerColorido


class RunnerOutputTests(unittest.TestCase):
    def test_runner_apresenta_nome_status_e_duracao(self):
        """Runner: mostra descricao, resultado e tempo de cada teste."""

        class CasoExemplo(unittest.TestCase):
            def test_fluxo(self):
                """Fluxo demonstrativo: resposta validada."""
                self.assertTrue(True)

        saida = StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CasoExemplo)
        resultado = RunnerColorido(
            stream=saida,
            verbosity=2,
            colorido=False,
        ).run(suite)
        relatorio = saida.getvalue()

        self.assertTrue(resultado.wasSuccessful())
        self.assertIn(
            "Fluxo demonstrativo: resposta validada. ... APROVADO",
            relatorio,
        )
        self.assertRegex(relatorio, r"APROVADO \(\d+\.\d{3} s\)")
        self.assertNotIn("test_fluxo (", relatorio)
