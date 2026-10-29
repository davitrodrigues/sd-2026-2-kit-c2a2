# funcoes simples de texto usadas no reranking e na avaliacao da resposta.
import re
import unicodedata

# palavras muito comuns que nao ajudam a dizer do que o texto trata.
PALAVRAS_VAZIAS = {
    "que", "qual", "quais", "como", "para", "por", "com", "sem", "uma", "umas",
    "uns", "dos", "das", "nas", "num", "numa", "pelo", "pela", "pelos",
    "pelas", "ele", "ela", "eles", "elas", "isso", "isto", "esse", "essa",
    "este", "esta", "sao", "ser", "foi", "tem", "mais", "muito", "entre",
    "sobre", "quando", "onde", "porque", "diz", "faz", "seu", "sua", "the",
    "and",
}


# devolve as palavras importantes do texto, em minusculo e sem acento.
def palavras(texto):
    simples = unicodedata.normalize("NFKD", texto.lower())
    simples = "".join(c for c in simples if not unicodedata.combining(c))
    return {p for p in re.findall(r"[a-z0-9]{3,}", simples)
            if p not in PALAVRAS_VAZIAS}
