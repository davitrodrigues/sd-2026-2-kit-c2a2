# TAREFAS - Trabalho C2.A2 (RAG Distribuido)

## Nucleo obrigatorio

- [X] **1. Persistir o indice** - `servicos/ingestao/app.py`
      O indice hoje some ao reiniciar. Guarde em arquivo ou banco vetorial.

- [X] **2. Busca por similaridade** - `servicos/recuperacao/app.py`
      Vetorizar a pergunta, comparar com cada documento e devolver os top_k. (Aula 9/10)

- [X] **3. Circuit breaker no LLM** - `servicos/geracao/app.py`
      Envolver a chamada `gerar(...)` com `disjuntor.chamar(...)` e devolver 503
      quando o circuito estiver aberto. (Aula 11)

- [X] **4. Mensageria** - novo worker + `docker-compose.yml`
      Ao menos UMA etapa do fluxo deve passar por fila, e nao por chamada direta. (Aula 8)

- [ ] **5. Fluxo completo** - de ponta a ponta
      Pergunta entra em /perguntar e sai uma resposta fundamentada nos documentos.

- [X] **6. README com diagrama** da arquitetura dos tres servicos.

## Extensoes opcionais

- [X] Reordenar os trechos por relevancia (reranking)
- [X] Citar quais documentos embasaram a resposta
- [X] Avaliacao automatica simples da qualidade da resposta
- [ ] Trocar TF-IDF por embeddings de verdade (sentence-transformers)

## Antes de entregar

- [X] Desligue a internet: o modo simulado do LLM mantem o sistema de pe?
- [X] Derrube o servico de recuperacao: o disjuntor abre como esperado?
- [X] A chave da API esta FORA do codigo (em variavel de ambiente)?
