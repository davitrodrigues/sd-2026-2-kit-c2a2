# servico 1 - ingestao: recebe documentos, gera os vetores e salva no disco.
#
# rodar: uvicorn servicos.ingestao.app:app --port 8001
import logging
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from servicos.comum.embeddings import Vetorizador
from servicos.ingestao import armazenamento

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Ingestao - C2.A2")

# a cada indexacao o estado inteiro e trocado por um novo, sem mexer no antigo.
ESTADO = (armazenamento.carregar()
          or {"versao": 0, "documentos": [], "vetorizador": None})
TRAVA = threading.Lock()  # deixa so uma indexacao rodar por vez

log.info("indice: %d documentos, versao %d (%s)", len(ESTADO["documentos"]),
         ESTADO["versao"], armazenamento.CAMINHO)


class Documento(BaseModel):
    texto: str
    origem: str = "desconhecida"


# diz se o texto tem pelo menos uma palavra que o tf-idf entende.
def tem_vocabulario(texto):
    try:
        Vetorizador().ajustar([texto])
        return True
    except ValueError:
        return False


@app.post("/indexar")
def indexar(docs: list[Documento]):
    global ESTADO
    if not docs:
        raise HTTPException(422, "envie ao menos um documento")
    invalidos = [i for i, d in enumerate(docs) if not tem_vocabulario(d.texto)]
    if invalidos:
        raise HTTPException(
            422, f"documentos sem nenhuma palavra de 2 ou mais letras nas "
                 f"posicoes {invalidos}; nada foi indexado")

    with TRAVA:
        atual = ESTADO
        pares = [(d["texto"], d["origem"]) for d in atual["documentos"]]
        vistos = set(pares)
        for d in docs:
            if (d.texto, d.origem) not in vistos:
                vistos.add((d.texto, d.origem))
                pares.append((d.texto, d.origem))
        indexados = len(pares) - len(atual["documentos"])

        if indexados:
            # ajusta com todos os textos, assim todo vetor tem o mesmo tamanho
            vetorizador = Vetorizador()
            vetorizador.ajustar([t for t, _ in pares])
            novo = {"versao": atual["versao"] + 1,
                    "documentos": [{"texto": t, "origem": o,
                                    "vetor": vetorizador.vetorizar(t)}
                                   for t, o in pares],
                    "vetorizador": vetorizador}
            try:
                armazenamento.salvar(novo)
            except OSError as e:
                log.exception("falha ao gravar o indice")
                raise HTTPException(
                    500, f"falha ao gravar o indice ({e}); nada foi alterado")
            ESTADO = novo
        final = ESTADO

    return {"indexados": indexados, "ignorados": len(docs) - indexados,
            "total": len(final["documentos"]), "versao": final["versao"]}


# o servico de recuperacao usa esta rota para buscar o indice.
@app.get("/indice")
def indice():
    estado = ESTADO
    return {"total": len(estado["documentos"]), "versao": estado["versao"],
            "itens": [{"texto": d["texto"], "origem": d["origem"],
                       "vetor": d["vetor"]} for d in estado["documentos"]]}


@app.get("/saude")
def saude():
    estado = ESTADO
    return {"status": "ok", "documentos": len(estado["documentos"]),
            "versao": estado["versao"]}
