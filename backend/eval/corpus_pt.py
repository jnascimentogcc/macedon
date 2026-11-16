"""Portuguese evaluation corpus, built to stress the lexical half of hybrid search.

The main corpus is English and easy. The keyword search uses the Postgres `simple` text search
configuration, which does no stemming and no accent folding, so a question that uses another
inflection than the document ("reembolsadas" against "reembolso") or drops accents ("rescisao")
gets nothing from the lexical side. Every question below is written that way on purpose, and most
use no word that the evidence phrase shares verbatim, so the vector side cannot be the only reason
for a hit. Compare `evidence_hit@k` and `mrr` before and after a change to the text search
configuration (see `run_pt.py`).

Questions with `document=None` have no answer in the corpus.
"""

from corpus import Doc, Question

PT_DOCS: list[Doc] = [
    Doc(
        "Politica de Reembolso",
        [
            (
                "Despesas de viagem",
                [
                    "As despesas de hospedagem serao reembolsadas ate o limite diario de 350 "
                    "reais, mediante apresentacao da nota fiscal original.",
                    "Refeicoes durante viagens a servico tem teto de 90 reais por dia.",
                ],
            ),
            (
                "Prazos",
                [
                    "O pedido de reembolso deve ser protocolado em ate 20 dias corridos apos o "
                    "retorno da viagem. Pedidos fora do prazo exigem justificativa da diretoria.",
                ],
            ),
            (
                "Aprovações",
                [
                    "Reembolsos acima de 2000 reais precisam ser aprovados pelo gerente "
                    "financeiro antes do pagamento.",
                ],
            ),
        ],
    ),
    Doc(
        "Contrato de Prestação de Serviços",
        [
            (
                "Rescisão",
                [
                    "Qualquer das partes pode rescindir o contrato mediante aviso prévio de 45 "
                    "dias, comunicado por escrito.",
                    "A multa rescisória corresponde a 10 por cento do valor restante do contrato.",
                ],
            ),
            (
                "Confidencialidade",
                [
                    "As informações confidenciais devem ser armazenadas em ambiente criptografado "
                    "e descartadas em ate 90 dias apos o encerramento do contrato.",
                ],
            ),
            (
                "Pagamento",
                [
                    "As faturas vencem 28 dias apos a emissão. Atrasos geram juros de 1 por "
                    "cento ao mes.",
                ],
            ),
        ],
    ),
    Doc(
        "Manual de Segurança da Informação",
        [
            (
                "Acesso remoto",
                [
                    "O acesso remoto aos sistemas internos exige VPN corporativa e autenticação "
                    "em dois fatores, conforme a norma NSI-317.",
                ],
            ),
            (
                "Incidentes",
                [
                    "Colaboradores que identificarem um incidente devem notificar a equipe de "
                    "segurança em ate 2 horas, pelo canal de plantão.",
                ],
            ),
            (
                "Dispositivos",
                [
                    "Computadores portáteis devem ter o disco cifrado e receber atualizações "
                    "automáticas de segurança.",
                ],
            ),
        ],
    ),
]

NO_ANSWER = "Não há resposta nos documentos."

PT_QUESTIONS: list[Question] = [
    # Different inflection of the same word (stemming).
    Question(
        "Quais despesas de hospedagem podem ser reembolsadas e até quanto?",
        "Politica de Reembolso",
        "limite diario de 350 reais",
        "O reembolso de hospedagem vai até 350 reais por dia.",
        tags=["morphology"],
    ),
    Question(
        "Quem precisa aprovar um reembolso grande?",
        "Politica de Reembolso",
        "aprovados pelo gerente financeiro",
        "O gerente financeiro, para valores acima de 2000 reais.",
        tags=["morphology"],
    ),
    Question(
        "Como devem ser armazenados os dados confidenciais?",
        "Contrato de Prestação de Serviços",
        "armazenadas em ambiente criptografado",
        "Em ambiente criptografado.",
        tags=["morphology"],
    ),
    Question(
        "Quando vencem as faturas emitidas?",
        "Contrato de Prestação de Serviços",
        "vencem 28 dias",
        "28 dias após a emissão.",
        tags=["morphology"],
    ),
    # Accents dropped by the user.
    Question(
        "Qual o aviso previo para rescisao do contrato?",
        "Contrato de Prestação de Serviços",
        "aviso prévio de 45 dias",
        "45 dias, por escrito.",
        tags=["accent"],
    ),
    Question(
        "Qual a multa rescisoria?",
        "Contrato de Prestação de Serviços",
        "10 por cento do valor restante",
        "10 por cento do valor restante do contrato.",
        tags=["accent"],
    ),
    Question(
        "Como deve ser a seguranca de um notebook da empresa?",
        "Manual de Segurança da Informação",
        "disco cifrado",
        "Disco cifrado e atualizações automáticas.",
        tags=["accent", "paraphrase"],
    ),
    # Identifiers and exact terms.
    Question(
        "O que diz a norma NSI-317?",
        "Manual de Segurança da Informação",
        "norma NSI-317",
        "Exige VPN e autenticação em dois fatores para acesso remoto.",
        tags=["identifier"],
    ),
    # Paraphrase with little word overlap.
    Question(
        "Em quanto tempo devo avisar a segurança sobre um problema?",
        "Manual de Segurança da Informação",
        "em ate 2 horas",
        "Em até 2 horas.",
        tags=["paraphrase"],
    ),
    Question(
        "Posso pedir reembolso depois de um mês da viagem?",
        "Politica de Reembolso",
        "20 dias corridos",
        "Só com justificativa da diretoria, pois o prazo é de 20 dias.",
        tags=["paraphrase"],
    ),
    Question(
        "Qual o teto de gasto com comida em viagem?",
        "Politica de Reembolso",
        "teto de 90 reais",
        "90 reais por dia.",
        tags=["paraphrase"],
    ),
    # Nothing in the corpus answers these.
    Question(
        "Qual é o salário do diretor financeiro?",
        None,
        None,
        NO_ANSWER,
        tags=["no-answer"],
    ),
    Question(
        "Quantos dias de férias o contrato prevê?",
        None,
        None,
        NO_ANSWER,
        tags=["no-answer"],
    ),
]
