# cliente do llm, com modo simulado para funcionar sem internet.
#
# com a chave da api no ambiente chama o llm de verdade; sem ela, monta a
# resposta com os trechos recuperados. nunca escreva a chave no codigo.
import logging
import os
import time

import requests

log = logging.getLogger("uvicorn.error")

API_KEY = os.getenv("LLM_API_KEY", "")
API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
MODELO = os.getenv("LLM_MODELO", "gpt-4o-mini")
# tempo maximo de cada tentativa, em segundos
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "5"))
TENTATIVAS = max(1, int(os.getenv("LLM_TENTATIVAS", "3")))
# liga uma falha de mentira para mostrar a retentativa e o disjuntor
FORCAR_FALHA = os.getenv("LLM_FORCAR_FALHA", "").lower() in ("1", "true")


# erro que pode sumir sozinho, por isso vale tentar de novo.
class FalhaTransitoria(Exception):
    pass


# aceita texto puro ou o trecho da recuperacao com texto e origem.
def _texto(trecho):
    return trecho["texto"] if isinstance(trecho, dict) else str(trecho)


def _origem(trecho):
    if isinstance(trecho, dict):
        return trecho.get("origem") or "desconhecida"
    return "desconhecida"


# lista as origens sem repetir, na ordem em que aparecem.
def origens(contexto):
    return list(dict.fromkeys(_origem(t) for t in contexto))


# resposta feita so com os trechos, usada no modo simulado e na degradada.
def resposta_sem_llm(pergunta, contexto, aviso):
    trechos = " ".join(_texto(t) for t in contexto)[:600]
    return (
        f"[{aviso}]\n"
        f"Pergunta: {pergunta}\n"
        f"Com base nos documentos recuperados: {trechos}\n"
        f"fontes: {', '.join(origens(contexto))}"
    )


def _simulado(pergunta, contexto):
    return resposta_sem_llm(
        pergunta, contexto, "MODO SIMULADO - sem LLM_API_KEY configurada")


# numera os trechos pela fonte, assim o [n] bate com a lista de fontes.
def montar_prompt(pergunta, contexto):
    numero = {o: n for n, o in enumerate(origens(contexto), start=1)}
    trechos = "\n".join(f"[{numero[_origem(t)]}] ({_origem(t)}) {_texto(t)}"
                        for t in contexto)
    return (
        "Responda a pergunta usando SOMENTE os trechos abaixo. "
        "Cite os trechos usados com o numero entre colchetes, como [1]. "
        "Se a resposta nao estiver nos trechos, diga que nao sabe.\n\n"
        f"Trechos:\n{trechos}\n\nPergunta: {pergunta}"
    )


# uma chamada a api; erro de rede, 429 e 5xx viram falha transitoria.
def _chamar_api(prompt):
    if FORCAR_FALHA:
        raise FalhaTransitoria("falha forcada para demonstracao")
    try:
        resposta = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODELO,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2},
            timeout=TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as e:
        raise FalhaTransitoria(type(e).__name__) from e
    if resposta.status_code == 429 or resposta.status_code >= 500:
        raise FalhaTransitoria(f"http {resposta.status_code}")
    resposta.raise_for_status()
    return resposta.json()["choices"][0]["message"]["content"]


# tenta de novo so em falha transitoria, esperando 1, 2, 4 segundos.
def _chamar_com_retentativa(prompt):
    for tentativa in range(1, TENTATIVAS + 1):
        inicio = time.monotonic()
        try:
            texto = _chamar_api(prompt)
        except FalhaTransitoria as e:
            gasto = time.monotonic() - inicio
            if tentativa == TENTATIVAS:
                log.warning("llm: tentativa %d/%d falhou em %.2f s (%s); "
                            "desistindo", tentativa, TENTATIVAS, gasto, e)
                raise
            espera = 2 ** (tentativa - 1)
            log.warning("llm: tentativa %d/%d falhou em %.2f s (%s); "
                        "nova tentativa em %d s",
                        tentativa, TENTATIVAS, gasto, e, espera)
            time.sleep(espera)
        except Exception as e:
            log.warning("llm: tentativa %d/%d com erro que nao se repete "
                        "(%s: %s)", tentativa, TENTATIVAS,
                        type(e).__name__, e)
            raise
        else:
            log.info("llm: tentativa %d/%d ok em %.2f s", tentativa,
                     TENTATIVAS, time.monotonic() - inicio)
            return texto


# monta o prompt com os trechos recuperados e chama o llm.
def gerar(pergunta: str, contexto: list) -> str:
    if not API_KEY and not FORCAR_FALHA:
        return _simulado(pergunta, contexto)
    return _chamar_com_retentativa(montar_prompt(pergunta, contexto))
