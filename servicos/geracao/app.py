# servico 3 - geracao: monta o prompt com o contexto e chama o llm.
#
# rodar: uvicorn servicos.geracao.app:app --port 8003
import logging
import math

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.fila import (
    ErroFila,
    FilaIndisponivel,
    FilaTimeout,
    FalhaNaRecuperacao,
    solicitar_busca,
)
from servicos.comum.llm import gerar, resposta_sem_llm
from servicos.geracao.avaliacao import avaliar

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Geracao - C2.A2")

# erros da busca pela fila que mostram a recuperacao fora do ar
FALHAS_BUSCA = (FilaIndisponivel, FilaTimeout, FalhaNaRecuperacao, ErroFila)

disjuntor = CircuitBreaker(limite_falhas=3, espera_segundos=20,
                           nome="disjuntor do llm")
disjuntor_busca = CircuitBreaker(limite_falhas=3, espera_segundos=20,
                                 conta_como_falha=FALHAS_BUSCA,
                                 nome="disjuntor da busca")

SEM_CONTEXTO = ("nao encontrei nos documentos indexados informacao para "
                "responder a pergunta.")


class Pergunta(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pergunta: str = Field(min_length=1)


# busca os trechos pela fila e confere se cada um tem texto.
def buscar_trechos(pergunta):
    resultados = solicitar_busca(pergunta)
    trechos = []
    for r in resultados:
        if not isinstance(r, dict) or not isinstance(r.get("texto"), str):
            raise ErroFila("recuperacao devolveu um trecho sem texto")
        trechos.append({"texto": r["texto"],
                        "origem": str(r.get("origem") or "desconhecida"),
                        "score": r.get("score")})
    return trechos


# uma fonte por documento, na ordem dos trechos, com a melhor nota dele.
def listar_fontes(trechos):
    fontes = {}
    for t in trechos:
        fontes.setdefault(t["origem"], t["score"])
    return [{"origem": o, "score": s} for o, s in fontes.items()]


# corpo da resposta, com a nota dela; com motivo, avisa que saiu sem o llm.
def montar_corpo(pergunta, trechos, resposta, motivo=None):
    contexto = [t["texto"] for t in trechos]
    return {"pergunta": pergunta, "resposta": resposta,
            "fontes": listar_fontes(trechos),
            "contexto": contexto,
            "degradado": motivo is not None, "motivo": motivo,
            "avaliacao": avaliar(pergunta, resposta, contexto)}


@app.post("/perguntar")
def perguntar(p: Pergunta):
    try:
        trechos = disjuntor_busca.chamar(buscar_trechos, p.pergunta)
    except CircuitoAberto as e:
        espera = max(1, math.ceil(e.restante))
        raise HTTPException(
            503, f"recuperacao indisponivel; nova tentativa em {espera} s",
            headers={"Retry-After": str(espera)}) from e
    except FilaIndisponivel as e:
        raise HTTPException(503, "fila de recuperacao indisponivel") from e
    except FilaTimeout as e:
        raise HTTPException(
            503, "tempo esgotado aguardando a recuperacao") from e
    except (FalhaNaRecuperacao, ErroFila) as e:
        raise HTTPException(502, str(e)) from e

    # sem trecho nenhum nao ha base para responder, entao nem chama o llm
    if not trechos:
        return montar_corpo(p.pergunta, trechos, SEM_CONTEXTO)

    try:
        resposta = disjuntor.chamar(gerar, p.pergunta, trechos)
    except CircuitoAberto:
        motivo = "circuito aberto"
    except Exception as e:
        log.warning("llm falhou (%s: %s); respondendo so com os trechos",
                    type(e).__name__, e)
        motivo = "llm indisponivel"
    else:
        return montar_corpo(p.pergunta, trechos, resposta)

    # sem llm, responde com os proprios trechos e avisa que degradou
    resposta = resposta_sem_llm(
        p.pergunta, trechos, f"RESPOSTA DEGRADADA - {motivo}")
    return montar_corpo(p.pergunta, trechos, resposta, motivo)


@app.get("/saude")
def saude():
    return {"status": "ok", "disjuntor": disjuntor.estado,
            "disjuntor_busca": disjuntor_busca.estado}
