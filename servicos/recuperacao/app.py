# servico 2 - recuperacao: dada uma pergunta, acha os trechos mais parecidos.
#
# rodar: uvicorn servicos.recuperacao.app:app --port 8002
import logging
import os
import threading

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from servicos.comum.embeddings import Vetorizador, similaridade

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Recuperacao - C2.A2")
URL_INGESTAO = os.getenv("URL_INGESTAO", "http://localhost:8001")
# erros que contam como ingestao fora do ar ou resposta estranha
FALHAS = (requests.RequestException, ValueError)

# copia do indice da ingestao; quando a versao muda, e trocada por uma nova.
CACHE = None
TRAVA = threading.Lock()  # deixa so uma recarga rodar por vez


class Consulta(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pergunta: str = Field(min_length=1)
    top_k: int = Field(3, ge=1, le=20)


# formato que a ingestao devolve; se vier diferente, conta como falha.
class Item(BaseModel):
    texto: str
    origem: str
    vetor: list[float]


class Indice(BaseModel):
    versao: int
    itens: list[Item]


class Saude(BaseModel):
    versao: int


# pergunta para a ingestao qual e a versao atual do indice.
def versao_na_ingestao():
    r = requests.get(f"{URL_INGESTAO}/saude", timeout=10)
    r.raise_for_status()
    return Saude.model_validate(r.json()).versao


# baixa o indice e ajusta um vetorizador igual ao da ingestao.
def baixar_indice():
    r = requests.get(f"{URL_INGESTAO}/indice", timeout=10)
    r.raise_for_status()
    indice = Indice.model_validate(r.json())
    if not indice.itens:
        return {"versao": indice.versao, "itens": [], "vetorizador": None}

    # com os mesmos textos sai o mesmo vetorizador que a ingestao usou
    vetorizador = Vetorizador()
    vetorizador.ajustar([i.texto for i in indice.itens])
    tamanho = len(vetorizador.vetorizar(indice.itens[0].texto))
    refazer = any(len(i.vetor) != tamanho for i in indice.itens)
    if refazer:
        log.warning("vetores da versao %d nao batem com o vetorizador local; "
                    "recalculando aqui", indice.versao)
    itens = [{"texto": i.texto, "origem": i.origem,
              "vetor": vetorizador.vetorizar(i.texto) if refazer else i.vetor}
             for i in indice.itens]
    return {"versao": indice.versao, "itens": itens,
            "vetorizador": vetorizador}


# devolve o indice em cache e so baixa de novo quando a versao muda.
def obter_indice():
    global CACHE
    cache = CACHE
    try:
        versao = versao_na_ingestao()
        if cache is not None and cache["versao"] == versao:
            return cache
        with TRAVA:
            # outra busca pode ter recarregado enquanto esta esperava
            atual = CACHE
            if atual is None or atual["versao"] != versao:
                atual = baixar_indice()
                CACHE = atual
                log.info("indice carregado: versao %d, %d documentos",
                         atual["versao"], len(atual["itens"]))
            return atual
    except FALHAS as e:
        cache = CACHE
        if cache is None:
            raise HTTPException(
                502, f"nao foi possivel ler o indice da ingestao "
                     f"({type(e).__name__}) e ainda nao ha copia em cache")
        log.warning("ingestao falhou (%s: %s); usando o indice em cache, "
                    "versao %d", type(e).__name__, e, cache["versao"])
        return cache


# devolve os trechos mais parecidos com a pergunta, do maior para o menor.
@app.post("/buscar")
def buscar(consulta: Consulta):
    indice = obter_indice()
    if not indice["itens"]:
        return {"resultados": []}

    pergunta = indice["vetorizador"].vetorizar(consulta.pergunta)
    achados = []
    for item in indice["itens"]:
        score = similaridade(pergunta, item["vetor"])
        if score > 0:  # zero quer dizer nenhuma palavra em comum
            achados.append((score, item))
    achados.sort(key=lambda a: a[0], reverse=True)
    return {"resultados": [
        {"texto": i["texto"], "origem": i["origem"], "score": round(s, 4)}
        for s, i in achados[:consulta.top_k]]}


# mostra qual versao do indice esta guardada aqui.
@app.get("/saude")
def saude():
    cache = CACHE
    if cache is None:
        return {"status": "ok", "versao_indice": None, "documentos": 0}
    return {"status": "ok", "versao_indice": cache["versao"],
            "documentos": len(cache["itens"])}
