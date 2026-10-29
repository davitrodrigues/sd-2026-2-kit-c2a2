"""Runner de testes com saida legivel e cores opcionais."""
import argparse
import os
import sys
import time
import unittest
from pathlib import Path


CORES = {
    "APROVADO": "\033[32m",
    "FALHOU": "\033[31m",
    "ERRO": "\033[31m",
    "IGNORADO": "\033[33m",
    "FALHA ESPERADA": "\033[33m",
    "SUCESSO INESPERADO": "\033[32m",
}
RESET = "\033[0m"


class ResultadoColorido(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity, colorido):
        super().__init__(stream, descriptions, verbosity)
        self.colorido = colorido
        self.inicios = {}

    def getDescription(self, test):
        return test.shortDescription() or test.id()

    def startTest(self, test):
        self.inicios[test] = time.perf_counter()
        super().startTest(test)

    def _write_status(self, test, status):
        if status == "ok":
            rotulo = "APROVADO"
        elif status == "FAIL":
            rotulo = "FALHOU"
        elif status == "ERROR":
            rotulo = "ERRO"
        elif status.startswith("skipped"):
            rotulo = "IGNORADO" + status[len("skipped"):]
        elif status == "expected failure":
            rotulo = "FALHA ESPERADA"
        elif status == "unexpected success":
            rotulo = "SUCESSO INESPERADO"
        else:
            rotulo = status.upper()

        inicio = self.inicios.get(test, time.perf_counter())
        duracao = time.perf_counter() - inicio
        cor = CORES.get(rotulo.split(":", maxsplit=1)[0].strip())
        if self.colorido and cor:
            rotulo = f"{cor}{rotulo}{RESET}"
        self.stream.write(f"{rotulo} ({duracao:.3f} s)\n")
        self.stream.flush()

    def stopTest(self, test):
        self.inicios.pop(test, None)
        super().stopTest(test)


class RunnerColorido(unittest.TextTestRunner):
    def __init__(self, *args, colorido=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.colorido = colorido

    def _makeResult(self):
        return ResultadoColorido(
            self.stream,
            self.descriptions,
            self.verbosity,
            self.colorido,
        )


def main():
    parser = argparse.ArgumentParser(description="Executa os testes do RAG.")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="controle de cores (padrao: auto)",
    )
    args = parser.parse_args()

    colorido = (
        args.color == "always"
        or (
            args.color == "auto"
            and sys.stdout.isatty()
            and "NO_COLOR" not in os.environ
        )
    )

    raiz = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(raiz / "tests"),
        top_level_dir=str(raiz),
    )
    print("\n=== Testes automatizados | RAG ===\n", file=sys.stderr, flush=True)
    resultado = RunnerColorido(
        verbosity=2,
        colorido=colorido,
    ).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
