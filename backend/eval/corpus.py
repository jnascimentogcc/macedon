"""Synthetic evaluation corpus and question set for the retrieval baseline.

Every document is fictional and written in English. Each question names the document that holds
the answer and an `evidence` phrase that must appear in a retrieved passage for the retrieval to
count as a hit. Questions with `document=None` have no answer in the corpus: the system should say
so instead of inventing one. `acl` is the group allowed to read the document (None = everyone),
used by the access-control checks.

The scoped part (`SCOPED_DOCS`, `SCOPED_QUESTIONS`) covers collection and tag filters. The original
documents are placed in a collection tree and tagged (`PLACEMENT`), which does not change the
unscoped questions. The scoped documents are ingested after the unscoped baseline has been
measured, so their confusable passages never disturb it.
"""

from dataclasses import dataclass, field, replace

Section = tuple[str, list[str]]


@dataclass(frozen=True)
class Doc:
    name: str
    sections: list[Section]
    group: str | None = None
    collection: str | None = None  # slash-separated path in the collection tree
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Question:
    question: str
    document: str | None
    evidence: str | None
    reference: str
    tags: list[str] = field(default_factory=list)


DOCS: list[Doc] = [
    Doc(
        "Travel Policy",
        [
            (
                "Flights",
                [
                    "Economy class is required for flights shorter than six hours.",
                    "Business class needs written approval from a director and is only "
                    "allowed for flights longer than six hours.",
                ],
            ),
            (
                "Hotels",
                [
                    "The nightly hotel limit is 180 euros in capital cities and 120 euros "
                    "elsewhere.",
                    "Hotels must be booked through the corporate portal at least 14 days "
                    "before departure.",
                ],
            ),
            (
                "Meals",
                [
                    "The daily meal allowance is 45 euros. Alcohol is never reimbursed.",
                ],
            ),
            (
                "Claims",
                [
                    "Expense claims must be filed within 30 days of the end of the trip, "
                    "with original receipts attached.",
                ],
            ),
        ],
    ),
    Doc(
        "Employee Handbook",
        [
            (
                "Vacation",
                [
                    "Full-time employees accrue 25 days of paid vacation per year. Unused "
                    "days up to five can be carried over to the next year.",
                    "Vacation requests must be submitted at least 30 days in advance "
                    "through the HR portal.",
                ],
            ),
            (
                "Remote work",
                [
                    "Employees may work remotely up to three days per week.",
                    "Security policy SEC-204 requires a company VPN for every remote session.",
                ],
            ),
            (
                "Sick leave",
                [
                    "Employees must notify their manager before 10:00 on the first day of "
                    "sick leave. A medical certificate is required after three consecutive "
                    "days of absence.",
                ],
            ),
            (
                "Probation",
                [
                    "The probation period lasts six months. Either party may end the "
                    "contract with two weeks of notice during probation.",
                ],
            ),
        ],
    ),
    Doc(
        "Information Security Standard",
        [
            (
                "Passwords",
                [
                    "Passwords must have at least 14 characters and are rotated only after "
                    "a suspected compromise. Multi-factor authentication is mandatory for "
                    "all production systems.",
                ],
            ),
            (
                "Incident response",
                [
                    "Any suspected security incident must be reported to the security team "
                    "within one hour. The security team opens an incident ticket and "
                    "assigns a severity from S1 (critical) to S4 (low).",
                    "S1 incidents trigger a post-mortem that must be published within five "
                    "business days.",
                ],
            ),
            (
                "Data classification",
                [
                    "Data is classified as Public, Internal, Confidential or Restricted. "
                    "Restricted data must be encrypted at rest with AES-256 and may never "
                    "be stored on personal devices.",
                ],
            ),
            (
                "Backups",
                [
                    "Production databases are backed up every night and backups are "
                    "retained for 35 days. Restore tests run quarterly.",
                ],
            ),
        ],
    ),
    Doc(
        "Procurement Guidelines",
        [
            (
                "Approval thresholds",
                [
                    "Purchases below 1,000 euros need manager approval. Purchases between "
                    "1,000 and 25,000 euros need approval from the department head. "
                    "Anything above 25,000 euros requires a committee decision.",
                ],
            ),
            (
                "Supplier selection",
                [
                    "Purchases above 10,000 euros require at least three written quotes. "
                    "Exceptions need a sole-source justification signed by the CFO.",
                ],
            ),
            (
                "Payment terms",
                [
                    "The standard payment term is 45 days after invoice receipt. Early "
                    "payment discounts above 2 percent should be taken when cash allows.",
                ],
            ),
        ],
    ),
    Doc(
        "Customer Support Playbook",
        [
            (
                "Response targets",
                [
                    "First response time targets: 1 hour for priority P1, 4 hours for P2, "
                    "one business day for P3. Resolution targets are 8 hours, 3 days and "
                    "10 days respectively.",
                ],
            ),
            (
                "Escalation",
                [
                    "A P1 ticket that is not resolved within 4 hours is escalated to the "
                    "on-call engineering manager. The customer success lead must be "
                    "notified at the same time.",
                ],
            ),
            (
                "Refunds",
                [
                    "Support agents may grant refunds up to 200 euros without approval. "
                    "Larger refunds require sign-off from the support manager. Refunds are "
                    "issued to the original payment method within 7 days.",
                ],
            ),
        ],
    ),
    Doc(
        "Data Retention Policy",
        [
            (
                "Retention periods",
                [
                    "Invoices and accounting records are kept for 10 years. Employment "
                    "contracts are kept for the duration of employment plus 5 years. "
                    "Application logs are kept for 90 days.",
                ],
            ),
            (
                "Deletion requests",
                [
                    "Customer deletion requests must be completed within 30 days. The "
                    "privacy officer confirms the deletion in writing to the customer.",
                ],
            ),
            (
                "Legal hold",
                [
                    "When the legal team issues a legal hold, all deletion for the "
                    "affected records is suspended until the hold is lifted in writing.",
                ],
            ),
        ],
    ),
    Doc(
        "Engineering Onboarding",
        [
            (
                "First week",
                [
                    "New engineers receive a laptop on their first day and are paired with "
                    "a mentor for the first 90 days. Access to production is granted only "
                    "after completing the security training.",
                ],
            ),
            (
                "Code review",
                [
                    "Every change needs one approving review before merging. Changes that "
                    "touch authentication or database migrations need two reviewers, one "
                    "of them from the platform team.",
                ],
            ),
            (
                "Deployments",
                [
                    "Deployments to production happen on weekdays before 15:00. Friday "
                    "deployments are only allowed for hotfixes approved by the on-call "
                    "engineering manager.",
                ],
            ),
        ],
        group="engineering",
    ),
    Doc(
        "Contract Review Checklist",
        [
            (
                "Liability",
                [
                    "Liability caps must not exceed 12 months of fees. Uncapped liability "
                    "is only acceptable for confidentiality breaches and requires the "
                    "general counsel's approval.",
                ],
            ),
            (
                "Termination",
                [
                    "Customer contracts must allow termination for convenience with 90 "
                    "days of written notice. Auto-renewal clauses need a 60-day opt-out "
                    "window.",
                ],
            ),
            (
                "Governing law",
                [
                    "The preferred governing law is that of Portugal, with arbitration in "
                    "Lisbon. Other jurisdictions need legal approval.",
                ],
            ),
        ],
        group="legal",
    ),
]

PLACEMENT: dict[str, tuple[str, list[str]]] = {
    "Travel Policy": ("Group/Policies", ["travel", "finance"]),
    "Employee Handbook": ("Group/Policies", ["hr"]),
    "Information Security Standard": ("Group/Security", ["security"]),
    "Procurement Guidelines": ("Group/Policies", ["finance"]),
    "Customer Support Playbook": ("Group/Support", ["support"]),
    "Data Retention Policy": ("Group/Security", ["security", "legal"]),
    "Engineering Onboarding": ("Group/Engineering", ["engineering", "hr"]),
    "Contract Review Checklist": ("Group/Legal", ["legal"]),
}
DOCS = [
    replace(doc, collection=PLACEMENT[doc.name][0], tags=PLACEMENT[doc.name][1]) for doc in DOCS
]

# Regional variants that answer the same questions as the group-wide documents with other facts.
SCOPED_DOCS: list[Doc] = [
    Doc(
        "Germany Travel Addendum",
        [
            (
                "Flights",
                [
                    "For the German subsidiary, business class needs written approval from "
                    "the regional director and is allowed for flights longer than four hours.",
                ],
            ),
            (
                "Hotels",
                [
                    "The nightly hotel limit for the German subsidiary is 150 euros in "
                    "capital cities and 100 euros elsewhere.",
                ],
            ),
            (
                "Claims",
                [
                    "German subsidiary expense claims must be filed within 20 days of the "
                    "end of the trip.",
                ],
            ),
        ],
        collection="Subsidiaries/Germany",
        tags=["travel", "germany"],
    ),
    Doc(
        "Brazil Travel Addendum",
        [
            (
                "Flights",
                [
                    "For the Brazilian subsidiary, business class needs written approval "
                    "from the country manager and is allowed for flights longer than five "
                    "hours.",
                ],
            ),
            (
                "Hotels",
                [
                    "The nightly hotel limit for the Brazilian subsidiary is 600 reais in "
                    "capital cities and 400 reais elsewhere.",
                ],
            ),
            (
                "Claims",
                [
                    "Brazilian subsidiary expense claims must be filed within 15 days of "
                    "the end of the trip.",
                ],
            ),
        ],
        collection="Subsidiaries/Brazil",
        tags=["travel", "brazil"],
    ),
    Doc(
        "Germany Handbook Addendum",
        [
            (
                "Vacation",
                [
                    "Employees of the German subsidiary accrue 30 days of paid vacation per year.",
                ],
            ),
            (
                "Remote work",
                [
                    "German employees may work remotely up to two days per week.",
                ],
            ),
        ],
        collection="Subsidiaries/Germany",
        tags=["hr", "germany"],
    ),
]
ALL_DOCS: list[Doc] = [*DOCS, *SCOPED_DOCS]


def in_scope(doc: Doc, collection: str | None, tags: list[str]) -> bool:
    """Whether a query scoped to a collection subtree and to all of these tags can see the doc."""
    if collection is not None and not (
        doc.collection == collection or (doc.collection or "").startswith(collection + "/")
    ):
        return False
    return set(tags) <= set(doc.tags)


QUESTIONS: list[Question] = [
    # Travel Policy
    Question(
        "What is the nightly hotel limit in capital cities?",
        "Travel Policy",
        "180 euros in capital cities",
        "180 euros per night in capital cities.",
    ),
    Question(
        "Who has to approve business class flights?",
        "Travel Policy",
        "written approval from a director",
        "A director, in writing, and only for flights over six hours.",
    ),
    Question(
        "How long do I have to file an expense claim after a trip?",
        "Travel Policy",
        "within 30 days",
        "Within 30 days of the end of the trip, with original receipts.",
    ),
    Question(
        "Is alcohol reimbursed on business trips?",
        "Travel Policy",
        "Alcohol is never reimbursed",
        "No, alcohol is never reimbursed.",
    ),
    Question(
        "How early must hotels be booked?",
        "Travel Policy",
        "at least 14 days",
        "At least 14 days before departure, through the corporate portal.",
    ),
    # Employee Handbook
    Question(
        "How many vacation days do employees get per year?",
        "Employee Handbook",
        "25 days of paid vacation",
        "25 days of paid vacation per year.",
    ),
    Question(
        "How many unused vacation days can I carry over?",
        "Employee Handbook",
        "up to five can be carried over",
        "Up to five unused days can be carried over to the next year.",
    ),
    Question(
        "What does SEC-204 require?",
        "Employee Handbook",
        "SEC-204 requires a company VPN",
        "A company VPN for every remote session.",
        ["identifier"],
    ),
    Question(
        "When does a sick employee need a medical certificate?",
        "Employee Handbook",
        "after three consecutive days",
        "After three consecutive days of absence.",
    ),
    Question(
        "How long is the probation period?",
        "Employee Handbook",
        "probation period lasts six months",
        "Six months.",
    ),
    Question(
        "How many days per week can I work remotely?",
        "Employee Handbook",
        "up to three days per week",
        "Up to three days per week.",
    ),
    # Information Security Standard
    Question(
        "What is the minimum password length?",
        "Information Security Standard",
        "at least 14 characters",
        "At least 14 characters.",
    ),
    Question(
        "How fast must a security incident be reported?",
        "Information Security Standard",
        "within one hour",
        "Within one hour, to the security team.",
    ),
    Question(
        "What encryption is required for Restricted data?",
        "Information Security Standard",
        "AES-256",
        "AES-256 at rest, and never on personal devices.",
    ),
    Question(
        "How long are production backups retained?",
        "Information Security Standard",
        "retained for 35 days",
        "35 days.",
    ),
    Question(
        "When must the post-mortem of a critical incident be published?",
        "Information Security Standard",
        "within five business days",
        "Within five business days, for S1 incidents.",
    ),
    # Procurement Guidelines
    Question(
        "Who approves a purchase of 5,000 euros?",
        "Procurement Guidelines",
        "approval from the department head",
        "The department head.",
        ["multi-hop"],
    ),
    Question(
        "How many quotes are needed for a 15,000 euro purchase?",
        "Procurement Guidelines",
        "at least three written quotes",
        "At least three written quotes.",
        ["multi-hop"],
    ),
    Question(
        "What is the standard payment term for suppliers?",
        "Procurement Guidelines",
        "45 days after invoice receipt",
        "45 days after invoice receipt.",
    ),
    # Customer Support Playbook
    Question(
        "What is the first response target for a P2 ticket?",
        "Customer Support Playbook",
        "4 hours for P2",
        "4 hours.",
    ),
    Question(
        "When is a P1 ticket escalated?",
        "Customer Support Playbook",
        "not resolved within 4 hours",
        "When it is not resolved within 4 hours, to the on-call engineering manager.",
    ),
    Question(
        "Up to what amount can an agent refund without approval?",
        "Customer Support Playbook",
        "up to 200 euros without approval",
        "200 euros.",
    ),
    # Data Retention Policy
    Question(
        "How long are invoices kept?",
        "Data Retention Policy",
        "kept for 10 years",
        "10 years.",
    ),
    Question(
        "How long do we have to complete a customer deletion request?",
        "Data Retention Policy",
        "within 30 days",
        "Within 30 days.",
    ),
    Question(
        "What happens to deletions when there is a legal hold?",
        "Data Retention Policy",
        "deletion for the affected records is suspended",
        "Deletion is suspended until the hold is lifted in writing.",
    ),
    # Engineering Onboarding (group: engineering)
    Question(
        "How many reviewers does a database migration need?",
        "Engineering Onboarding",
        "need two reviewers",
        "Two reviewers, one from the platform team.",
        ["acl:engineering"],
    ),
    Question(
        "Can we deploy to production on Fridays?",
        "Engineering Onboarding",
        "Friday deployments are only allowed for hotfixes",
        "Only hotfixes approved by the on-call engineering manager.",
        ["acl:engineering"],
    ),
    # Contract Review Checklist (group: legal)
    Question(
        "What is the maximum liability cap in customer contracts?",
        "Contract Review Checklist",
        "12 months of fees",
        "12 months of fees.",
        ["acl:legal"],
    ),
    Question(
        "What notice period must customer contracts allow for termination?",
        "Contract Review Checklist",
        "90 days of written notice",
        "90 days of written notice.",
        ["acl:legal"],
    ),
    # Paraphrased questions (no shared keywords with the evidence)
    Question(
        "Can I take my laptop home and connect from there?",
        "Employee Handbook",
        "up to three days per week",
        "Remote work is allowed up to three days per week, with a VPN.",
        ["paraphrase"],
    ),
    Question(
        "Who do I call when something suspicious happens on my account?",
        "Information Security Standard",
        "within one hour",
        "Report it to the security team within one hour.",
        ["paraphrase"],
    ),
    # No answer in the corpus
    Question(
        "What is the parental leave policy?",
        None,
        None,
        "There is no answer in the documents.",
        ["no-answer"],
    ),
    Question(
        "How much is the annual training budget per engineer?",
        None,
        None,
        "There is no answer in the documents.",
        ["no-answer"],
    ),
    Question(
        "What is the company's dress code?",
        None,
        None,
        "There is no answer in the documents.",
        ["no-answer"],
    ),
]


@dataclass(frozen=True)
class ScopedQuestion:
    """A question asked inside a collection subtree and/or a tag filter.

    `document` is the document that answers it within the scope (None when nothing in scope
    does, so the system must abstain). `compare_unscoped` also asks it without the scope, to
    measure what the scope adds when similar documents compete. `acl` repeats it as a user
    outside the restricted document's group, who must get no passage of it.
    """

    question: str
    document: str | None
    evidence: str | None
    reference: str
    kind: str
    collection: str | None = None
    tags: list[str] = field(default_factory=list)
    compare_unscoped: bool = False
    acl: bool = False


NO_ANSWER = "There is no answer in the documents."
HOTEL = "What is the nightly hotel limit in capital cities?"
CLAIMS = "How long do I have to file an expense claim after a trip?"
BUSINESS = "Who has to approve business class flights?"
VACATION = "How many vacation days do employees get per year?"
PAYMENT = "What is the standard payment term for invoices?"

SCOPED_QUESTIONS: list[ScopedQuestion] = [
    # Ambiguous: similar documents compete, the scope picks one
    ScopedQuestion(
        HOTEL,
        "Germany Travel Addendum",
        "150 euros in capital cities",
        "150 euros in capital cities (German subsidiary).",
        "ambiguous",
        collection="Subsidiaries/Germany",
        compare_unscoped=True,
    ),
    ScopedQuestion(
        HOTEL,
        "Brazil Travel Addendum",
        "600 reais in capital cities",
        "600 reais in capital cities (Brazilian subsidiary).",
        "ambiguous",
        collection="Subsidiaries/Brazil",
        compare_unscoped=True,
    ),
    ScopedQuestion(
        HOTEL,
        "Travel Policy",
        "180 euros in capital cities",
        "180 euros in capital cities.",
        "ambiguous",
        collection="Group/Policies",
        compare_unscoped=True,
    ),
    ScopedQuestion(
        CLAIMS,
        "Brazil Travel Addendum",
        "within 15 days",
        "Within 15 days of the end of the trip.",
        "ambiguous",
        collection="Subsidiaries/Brazil",
        compare_unscoped=True,
    ),
    ScopedQuestion(
        BUSINESS,
        "Germany Travel Addendum",
        "regional director",
        "The regional director, in writing.",
        "ambiguous",
        tags=["germany"],
        compare_unscoped=True,
    ),
    ScopedQuestion(
        VACATION,
        "Germany Handbook Addendum",
        "30 days of paid vacation",
        "30 days of paid vacation per year.",
        "ambiguous",
        collection="Subsidiaries",
        compare_unscoped=True,
    ),
    # Tags: all of them must match
    ScopedQuestion(
        BUSINESS,
        "Brazil Travel Addendum",
        "country manager",
        "The country manager, in writing.",
        "ambiguous",
        tags=["travel", "brazil"],
        compare_unscoped=True,
    ),
    # Subtree: a scope on the parent includes its children and excludes its siblings
    ScopedQuestion(
        VACATION,
        "Employee Handbook",
        "25 days of paid vacation",
        "25 days of paid vacation per year.",
        "subtree",
        collection="Group",
        compare_unscoped=True,
    ),
    ScopedQuestion(
        "How many days per week can employees work remotely?",
        "Germany Handbook Addendum",
        "up to two days per week",
        "Up to two days per week.",
        "subtree",
        collection="Subsidiaries",
    ),
    # In scope, nothing to compete with
    ScopedQuestion(
        "How long are production database backups retained?",
        "Information Security Standard",
        "retained for 35 days",
        "35 days.",
        "in-scope",
        collection="Group/Security",
    ),
    ScopedQuestion(
        PAYMENT,
        "Procurement Guidelines",
        "45 days after invoice receipt",
        "45 days after invoice receipt.",
        "in-scope",
        tags=["finance"],
    ),
    # Nothing in scope answers: abstain and show nothing from outside the scope
    ScopedQuestion(
        "How long does the probation period last?",
        None,
        None,
        NO_ANSWER,
        "out-of-scope",
        collection="Subsidiaries/Brazil",
    ),
    ScopedQuestion(
        "What is the daily meal allowance?",
        None,
        None,
        NO_ANSWER,
        "out-of-scope",
        collection="Subsidiaries",
    ),
    ScopedQuestion(
        PAYMENT,
        None,
        None,
        NO_ANSWER,
        "out-of-scope",
        tags=["finance", "germany"],
    ),
    # Access control still applies inside a scope
    ScopedQuestion(
        "How many reviewers does a database migration need?",
        "Engineering Onboarding",
        "two reviewers",
        "Two reviewers, one of them from the platform team.",
        "acl",
        collection="Group/Engineering",
        acl=True,
    ),
    ScopedQuestion(
        "What notice period must customer contracts allow for termination?",
        "Contract Review Checklist",
        "90 days of written notice",
        "90 days of written notice.",
        "acl",
        tags=["legal"],
        acl=True,
    ),
]
