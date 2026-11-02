# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado do repositório

Fase de pré-implementação: o repositório contém apenas `LICENSE` e `docs/Visão — Plataforma RAG de Documentos.md` (fonte de verdade do design, em português). Ainda não há código, build, lint nem testes — não invente comandos; defina-os quando a stack for criada. Documentação e comunicação são em português.

## O que é o projeto

Plataforma RAG de documentos (nome do repo: Macedon): recebe documentos, faz chunking preservando contexto, indexa em base vetorial e responde perguntas via API citando documento, versão, página e seção. Também gerencia versionamento e controle de acesso.

## Stack planejada

Python + FastAPI (valida JWT em toda requisição); Postgres + pgvector (índice HNSW) — sem banco vetorial dedicado no início; S3/MinIO para originais (um objeto por versão); fila de ingestão (Celery, RQ ou Arq) com workers; extração via Docling / PyMuPDF / python-docx; embeddings BGE-M3 (local) ou API; busca híbrida (vetorial + full-text do Postgres) com reranker (top 20–30 → top 5); geração por LLM; avaliação com RAGAS (30–50 perguntas). Pipeline escrito direto, **sem LangChain/LlamaIndex**.

Ingestão é assíncrona (upload responde na hora, processamento em worker); a consulta roda direto na API.

## Invariantes de arquitetura

- **Chunks pertencem à versão, não ao documento.** Tabelas: `documents` (identidade, ACL, `tenant_id`), `document_versions` (hash SHA-256, caminho S3, status `processing|active|archived`), `chunks` (texto, embedding, `version_id`, `section_id`, `position`, hash do texto, `embedding_model`, permissões).
- **Uma versão ativa por documento.** Busca padrão filtra `status = 'active'`; versão histórica só via parâmetro explícito em `/query`.
- **Troca atômica:** nova versão só vira ativa quando todos os chunks estiverem indexados; até lá a anterior responde.
- **Deduplicação** por hash do arquivo; **reaproveitamento de embeddings** por hash do texto do chunk.
- **Soft delete:** `DELETE` arquiva versões (preserva auditoria).
- **Modelo de embedding é registrado por chunk** e fixado desde o início; trocar exige reindexar (em paralelo, sem derrubar a busca).
- **Segurança na consulta:** ACL copiada para os chunks e aplicada *dentro* da query vetorial (nunca pós-filtro), com Row-Level Security do Postgres como segunda barreira. Auth, ACL/RLS e auditoria são prioridade da fase 1.
- **Prompt injection:** chunks delimitados no prompt e tratados como dados; nenhuma ferramenta com efeito colateral no fluxo de consulta.
- **Identidade:** Keycloak (OIDC/JWT) é o provedor padrão, mas só autentica e fornece claims (grupos, papéis, `tenant_id`). A API apenas valida o JWT, sem depender de APIs específicas do Keycloak, para permitir trocar de provedor. A autorização sobre documentos/chunks (ACL + RLS) fica na plataforma, nunca delegada ao Keycloak.
- Upload: validar tipo pelos bytes, limite de tamanho, parsing em worker isolado. LGPD: mascarar CPF/e-mail/telefone na ingestão (Presidio).

## Estratégia de chunking

Ordem de adoção: (1) corte estrutural (seção > parágrafo > frase; 500–800 tokens, 10–15% de overlap; tabelas/listas inteiras), (2) prefixo com caminho do documento antes do embedding, (4) parent-child (indexar ~200 tokens, entregar o bloco pai), com (5) expansão por vizinhos N±1 como fallback para texto não estruturado. (3) Contextual Retrieval só se a avaliação mostrar chunks ambíguos perdidos. Chunking semântico por embeddings está fora de escopo.

Regra de recuperação unificada: cada chunk guarda `doc_id`, `section_id`, `position`; se a seção couber em ~1500 tokens envia-se a seção inteira, senão a janela de vizinhos.

Qualquer mudança de chunking, modelo de embedding ou reranker deve ser medida com o conjunto de avaliação RAGAS.

## API planejada

`POST /documents`, `GET /documents/{id}`, `POST|GET /documents/{id}/versions`, `POST /documents/{id}/versions/{v}/activate` (também rollback), `DELETE /documents/{id}`, `POST /query` (resposta com fontes: documento, versão, página, seção).

## Questões em aberto

Volume esperado, embeddings local vs API, LLM e local de processamento, multi-tenant desde o início, formatos de arquivo iniciais. Veja o doc de visão antes de assumir qualquer uma dessas decisões.
