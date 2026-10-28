"""
Servico 3 - GERACAO: monta o prompt com o contexto e chama o LLM.

TAREFA 3: proteger a chamada ao LLM com o circuit breaker.

Rodar: uvicorn servicos.geracao.app:app --port 8003
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.fila import (
    ErroFila,
    FilaIndisponivel,
    FilaTimeout,
    FalhaNaRecuperacao,
    solicitar_busca,
)
from servicos.comum.llm import gerar

app = FastAPI(title="Geracao - C2.A2")

disjuntor = CircuitBreaker(limite_falhas=3, espera_segundos=20)


class Pergunta(BaseModel):
    pergunta: str


@app.post("/perguntar")
def perguntar(p: Pergunta):
    try:
        resultados = solicitar_busca(p.pergunta)
    except FilaIndisponivel as e:
        raise HTTPException(503, "fila de recuperacao indisponivel") from e
    except FilaTimeout as e:
        raise HTTPException(
            503, "tempo esgotado aguardando a recuperacao") from e
    except (FalhaNaRecuperacao, ErroFila) as e:
        raise HTTPException(502, str(e)) from e

    contexto = [t["texto"] for t in resultados]

    try:
        resposta = disjuntor.chamar(gerar, p.pergunta, contexto)
    except CircuitoAberto as e:
        raise HTTPException(
            status_code=503,
            detail="servico de geracao temporariamente indisponivel: circuito aberto",
        ) from e

    return {"pergunta": p.pergunta, "resposta": resposta, "contexto": contexto}


@app.get("/saude")
def saude():
    return {"status": "ok", "disjuntor": disjuntor.estado}
