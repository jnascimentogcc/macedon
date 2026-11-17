"""Questions over two real public documents: a Portuguese public tender (AMA, 31 lots).

The documents are not in the repository (size, and they are not ours to redistribute). They are
passed to `run_real.py` with `--dir`; the two files it expects are named in `DOCUMENT_FILES`.

What makes this set harder than the synthetic ones:

* real PDFs: 83 and 116 pages, page headers and footers inside the text, headings that the
  extractor has to guess from font sizes;
* 31 lots described by near-identical sentences that differ only in a number (`lot-price`);
* facts that sit across a page break (`page-break`);
* the same rule stated twice with different values (`confusable`: vulnerability deadlines during
  execution and during warranty) or in both documents (`both-documents`);
* a price table written as numbered list items, and formula text.

Every `evidence` phrase is checked against the raw PDF text before anything is sent to a paid API.
Questions with `document=None` have no answer in the documents (checked by hand: the key words do
not appear in either file).
"""

from corpus import Question

CE = "CE_TicAPP_Lotes_VF_ama"
PROGRAMA = "Programa_do_procedimento_Lotes_VF_ama"

DOCUMENT_FILES = {CE: f"{CE}.pdf", PROGRAMA: f"{PROGRAMA}.pdf"}

NO_ANSWER = "Não há resposta nos documentos."

REAL_QUESTIONS: list[Question] = [
    # Direct lookups in the specifications (caderno de encargos).
    Question(
        "Em quantos dias é feito o pagamento das faturas?",
        CE,
        "30 dias a contar da data da receção das faturas",
        "30 dias a contar da data da receção das faturas.",
        tags=["lookup", "paraphrase"],
    ),
    Question(
        "Qual é o preço contratual global do concurso?",
        CE,
        "31.741.794,40",
        "31.741.794,40 euros, acrescido de IVA.",
        tags=["lookup", "number"],
    ),
    Question(
        "Qual o tribunal competente para resolver litígios do contrato?",
        CE,
        "Tribunal Administrativo de Círculo de Lisboa",
        "O Tribunal Administrativo de Círculo de Lisboa.",
        tags=["lookup"],
    ),
    Question(
        "Qual é o número do concurso público?",
        CE,
        "184/2023/CPI/CD",
        "184/2023/CPI/CD.",
        tags=["identifier"],
    ),
    Question(
        "Em que consiste o Lote 5?",
        CE,
        "serviços para gestão de conteúdos e UX writing",
        "Serviços para gestão de conteúdos e UX writing em serviços digitais.",
        tags=["lookup", "lot"],
    ),
    # Same sentence for 31 lots, only the number changes.
    Question(
        "Qual o preço contratual do Lote 5?",
        CE,
        "Lote 5 o preço contratual é de 1.020.000,00 €",
        "1.020.000,00 €.",
        tags=["lot-price", "number"],
    ),
    Question(
        "Quanto custa o Lote 12?",
        CE,
        "Lote 12 o preço contratual é de 301.302,40 €",
        "301.302,40 €.",
        tags=["lot-price", "number", "paraphrase"],
    ),
    Question(
        "Qual o valor estimado em 2025 para o lote 22?",
        CE,
        "Lote 22 o preço contratual é de 710.707,20 €",
        "222.096,00 € em 2025.",
        tags=["lot-price", "number"],
    ),
    Question(
        "Qual é o preço contratual do lote 30?",
        CE,
        "Lote 30 o preço contratual é de 1.488.320,00 €",
        "1.488.320,00 €.",
        tags=["lot-price", "number"],
    ),
    # Penalties.
    Question(
        "Qual o limite máximo acumulado das sanções pecuniárias?",
        CE,
        "não pode exceder 20 % do preço contratual",
        "20% do preço contratual, elevado a 30% em certos casos.",
        tags=["lookup", "number"],
    ),
    Question(
        "Que penalidade se aplica por falhar os mecanismos de acompanhamento?",
        CE,
        "10% do preço a pagar no mês em que ocorre o incumprimento",
        "10% do preço a pagar no mês do incumprimento.",
        tags=["lookup", "paraphrase"],
    ),
    # Facts that sit across a page break.
    Question(
        "Até que data cessa o contrato do lote 13?",
        CE,
        "previsivelmente até 31 de dezembro de 2024",
        "Previsivelmente até 31 de dezembro de 2024.",
        tags=["page-break"],
    ),
    Question(
        "Quais os lotes cujos contratos produzem efeitos a partir de 1 de janeiro de 2025?",
        CE,
        "lotes 3, 12, 26 e 27",
        "Os lotes 3, 12, 26 e 27.",
        tags=["lookup", "page-break"],
    ),
    # Same rule, two values.
    Question(
        "Qual o prazo para resolver vulnerabilidades críticas durante o período de garantia?",
        CE,
        "Critical: 10 dias seguidos",
        "10 dias seguidos (5 dias seguidos durante a execução do contrato).",
        tags=["confusable"],
    ),
    Question(
        "Qual o prazo para resolver vulnerabilidades críticas durante a execução do contrato?",
        CE,
        "Critical: 5 dias seguidos",
        "5 dias seguidos (10 dias seguidos no período de garantia).",
        tags=["confusable"],
    ),
    Question(
        "Em quantos dias úteis deve começar a prestação dos serviços após a celebração?",
        CE,
        "no máximo até 10 dias úteis",
        "No máximo até 10 dias úteis.",
        tags=["lookup"],
    ),
    # Tender programme.
    Question(
        "Até que horas e dia se podem entregar as propostas?",
        PROGRAMA,
        "até às 23:59 horas do 33.º",
        "Até às 23:59 horas do 33.º dia a contar do envio do anúncio.",
        tags=["lookup"],
    ),
    Question(
        "Durante quanto tempo os concorrentes têm de manter as propostas?",
        PROGRAMA,
        "120 (cento e vinte) dias",
        "120 dias a contar do termo do prazo de apresentação.",
        tags=["lookup", "number"],
    ),
    Question(
        "Como se calcula a pontuação global de cada proposta?",
        PROGRAMA,
        "0,2*Preço + 0,8*Adequação da Equipa",
        "PGP = 0,2*Preço + 0,8*Adequação da Equipa.",
        tags=["formula", "paraphrase"],
    ),
    Question(
        "Qual o valor da caução a prestar pelo adjudicatário?",
        PROGRAMA,
        "no valor de 5% do preço contratual",
        "5% do preço contratual.",
        tags=["lookup", "number"],
    ),
    Question(
        "Em que lotes não é exigida caução?",
        PROGRAMA,
        "exceto nos Lotes 11, 12, 13, 16, 24, 25, 26, 27, 28 e 31",
        "Lotes 11, 12, 13, 16, 24, 25, 26, 27, 28 e 31.",
        tags=["lookup", "lot"],
    ),
    Question(
        "Quantos dias tem o adjudicatário para entregar os documentos de habilitação?",
        PROGRAMA,
        "no prazo de 10 dias a contar da notificação da decisão de adjudicação",
        "10 dias a contar da notificação da adjudicação.",
        tags=["lookup"],
    ),
    Question(
        "Quando é que os interessados podem pedir esclarecimentos sobre as peças?",
        PROGRAMA,
        "no primeiro terço do prazo fixado para a apresentação das propostas",
        "No primeiro terço do prazo de apresentação das propostas.",
        tags=["lookup", "paraphrase"],
    ),
    # Stated in both documents.
    Question(
        "Que percentagem dos pagamentos pode a AMA reter se não houver caução?",
        CE,
        "retenção de 10% do valor dos pagamentos",
        "10% do valor dos pagamentos a efetuar.",
        tags=["both-documents"],
    ),
    # Nothing in the documents answers these.
    Question(
        "Quantos funcionários tem a AMA?",
        None,
        None,
        NO_ANSWER,
        tags=["no-answer"],
    ),
    Question(
        "Qual o preço contratual do Lote 40?",
        None,
        None,
        NO_ANSWER,
        tags=["no-answer"],
    ),
    Question(
        "Qual a sede social do adjudicatário no Porto?",
        None,
        None,
        NO_ANSWER,
        tags=["no-answer"],
    ),
]
