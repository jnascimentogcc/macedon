"""Score the answers saved by run.py with RAGAS (LLM-as-judge; calls paid APIs).

    uv run --group eval python eval/ragas_score.py [--results eval/results/baseline.json]

Adds faithfulness (is the answer supported by the retrieved passages), response relevancy and
answer correctness (a binary judge against the reference answer) to the results file. The judge
uses the same provider settings as the application.
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AspectCritic, Faithfulness, ResponseRelevancy

from macedon.config import get_settings


class FixedTemperatureChatOpenAI(ChatOpenAI):
    """RAGAS sets its own temperature on every call; some models accept only the default."""

    def _get_request_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = super()._get_request_payload(*args, **kwargs)
        payload.pop("temperature", None)
        return payload


def main(results_path: Path) -> None:
    settings = get_settings()
    if settings.openai_api_key is None:
        raise SystemExit("MACEDON_OPENAI_API_KEY is not set")
    key = settings.openai_api_key.get_secret_value()

    report = json.loads(results_path.read_text(encoding="utf-8"))
    rows = [r for r in report["rows"] if r["document"] is not None]
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": r["question"],
                "retrieved_contexts": r["contexts"],
                "response": r["answer"],
                "reference": r["reference"],
            }
            for r in rows
        ]
    )
    llm = LangchainLLMWrapper(
        FixedTemperatureChatOpenAI(
            model=settings.llm_model, api_key=key, base_url=settings.openai_base_url
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=settings.embedding_model, api_key=key, base_url=settings.openai_base_url
        )
    )
    correct = AspectCritic(
        name="answer_correct",
        llm=llm,
        definition=(
            "Return 1 if the response states the same key fact as the reference answer "
            "(wording and extra detail do not matter, a contradicting or missing key fact does)."
        ),
    )
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), ResponseRelevancy(), correct],
        llm=llm,
        embeddings=embeddings,
    )
    frame = result.to_pandas()
    metric_columns = ["faithfulness", "answer_relevancy", "answer_correct"]
    scores: dict[str, float] = {}
    for column in metric_columns:
        values = [v for v in frame[column].tolist() if v == v]  # drop NaN
        scores[column] = round(statistics.fmean(values), 4) if values else float("nan")
    for row, (_, scored) in zip(rows, frame.iterrows(), strict=True):
        row["ragas"] = {
            c: (None if scored[c] != scored[c] else float(scored[c])) for c in metric_columns
        }
    report["ragas"] = {"judge": settings.llm_model, "scores": scores}
    results_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("eval/results/baseline.json"))
    main(parser.parse_args().results)
