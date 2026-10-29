# da uma nota simples a resposta: se usa os documentos e trata da pergunta.
import re

from servicos.comum.texto import palavras

# parte da resposta que precisa vir dos documentos para a nota ser boa.
FUNDAMENTACAO_BOA = 0.7
# parte da pergunta que a resposta precisa tocar para a nota ser boa.
COBERTURA_BOA = 0.5
# com menos apoio que isto nos documentos a resposta e fraca.
FUNDAMENTACAO_FRACA = 0.4
# letras do comeco da palavra que contam, para juntar formas parecidas.
TAMANHO_RAIZ = 5

# linhas que so enfeitam a resposta, como o aviso todo entre colchetes.
MOLDURA = re.compile(r"\s*(\[[^\]]*\]\s*$|pergunta:|fontes:)",
                     re.IGNORECASE)
# texto que o modo simulado poe antes dos trechos.
PREFIXO = re.compile(r"\s*com base nos documentos recuperados:",
                     re.IGNORECASE)


# tira da resposta as linhas de moldura e deixa so o conteudo.
def _conteudo(resposta):
    return "\n".join(PREFIXO.sub("", linha, count=1)
                     for linha in resposta.splitlines()
                     if not MOLDURA.match(linha))


# corta plural e fim da palavra, para particao e particoes contarem igual.
def _raizes(texto):
    raizes = set()
    for p in palavras(texto):
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        raizes.add(p[:TAMANHO_RAIZ])
    return raizes


# escolhe a nota e uma frase curta dizendo o motivo.
def _nota(fundamentacao, cobertura):
    if fundamentacao >= FUNDAMENTACAO_BOA and cobertura >= COBERTURA_BOA:
        return "boa", "resposta apoiada nos documentos e cobre a pergunta"
    fraca = fundamentacao < FUNDAMENTACAO_FRACA or cobertura == 0
    motivos = []
    if fundamentacao < FUNDAMENTACAO_FRACA:
        motivos.append("pouco apoiada nos documentos")
    elif fundamentacao < FUNDAMENTACAO_BOA:
        motivos.append("apoiada so em parte nos documentos")
    if cobertura == 0:
        motivos.append("nao trata do que foi perguntado")
    elif cobertura < COBERTURA_BOA:
        motivos.append("cobre so parte da pergunta")
    nota = "fraca" if fraca else "regular"
    return nota, "resposta " + " e ".join(motivos)


# mede se a resposta se apoia no contexto e se cobre a pergunta.
def avaliar(pergunta: str, resposta: str, contexto: list[str]) -> dict:
    textos = [t for t in contexto or [] if t and t.strip()]
    if not textos:
        return {"fundamentacao": None, "cobertura_pergunta": None,
                "nota": "sem contexto",
                "observacao": "nenhum documento foi recuperado para apoiar "
                              "a resposta"}

    na_resposta = _raizes(_conteudo(resposta or ""))
    na_pergunta = _raizes(pergunta or "")
    no_contexto = _raizes(" ".join(textos))

    # pergunta sem palavra importante nao tem o que cobrir
    cobertura = 1.0
    if na_pergunta:
        cobertura = round(len(na_pergunta & na_resposta) / len(na_pergunta), 2)

    if not na_resposta:
        return {"fundamentacao": 0.0, "cobertura_pergunta": cobertura,
                "nota": "fraca",
                "observacao": "resposta vazia, sem conteudo para avaliar"}

    fundamentacao = round(len(na_resposta & no_contexto) / len(na_resposta), 2)
    nota, observacao = _nota(fundamentacao, cobertura)
    return {"fundamentacao": fundamentacao, "cobertura_pergunta": cobertura,
            "nota": nota, "observacao": observacao}
