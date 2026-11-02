# Macedon

Document RAG platform: it receives documents, splits them into chunks while preserving context, indexes them in a vector store and answers questions through an API, citing the source document and version. Open-source project. See the full design in [docs/vision.md](docs/vision.md).

## About the name

"Macedon" comes from the idea of *divide and conquer*, which fits RAG well: documents are split into chunks so that each question can be answered by conquering only the relevant pieces. The phrase is often attributed, among other remote origins, to Philip II of Macedon.

## Warning: data is sent to external APIs

This project sends the content of documents to external APIs. All inference (embeddings, answer generation and reranking) is performed by third-party services, OpenAI by default. Nothing runs locally, and **there is no masking of personal or sensitive data**: content is sent as is.

Before using it with sensitive information, check with each configured provider:

- **Processing location:** the region where data is processed and whether data residency options exist.
- **Retention:** how long requests are stored and whether they may be used to train models.
- **Legal and contractual fit:** whether sending the data is compatible with data protection law (e.g. GDPR, LGPD) and your organization's obligations.

Anyone adopting the project can configure other providers, and the responsibility for this assessment lies with whoever operates it.
