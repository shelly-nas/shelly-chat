"""
RAG evaluation with RAGAS metrics, through the same pipeline the browser runs
(host/rag.py: expand and retrieve on the NAS, embed and generate with the
local Ollama).

Metrics always evaluated:
  faithfulness        - Is the answer grounded in the retrieved context?
  answer_relevancy    - Does the answer address the question?

Metrics evaluated only when ALL entries in eval_dataset.json have a non-empty
'ground_truth' field:
  context_precision   - Are the retrieved chunks relevant to the question?
  context_recall      - Did retrieval surface all information needed to answer?

Thresholds (override via environment variables):
  EVAL_FAITHFULNESS_THRESHOLD        default 0.7
  EVAL_ANSWER_RELEVANCY_THRESHOLD    default 0.7
  EVAL_CONTEXT_PRECISION_THRESHOLD   default 0.6
  EVAL_CONTEXT_RECALL_THRESHOLD      default 0.6

Usage (from host/, with requirements-eval.txt installed):
  pytest tests/eval -v -s
  python -m tests.eval.test_rag_eval     # standalone with printed report

Pre-requisites:
  - shelly-chat reachable at SHELLY_CHAT_URL, with the index EVAL_INDEX filled
  - Ollama running with the embedding model of the index and LLM_MODEL_NAME
"""

import json
import os
import pathlib

import pytest
import requests

import rag

EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:latest")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemma4:latest")
# The named index the questions are asked of.
EVAL_INDEX = os.getenv("EVAL_INDEX", "Alle documenten")

# ── thresholds ────────────────────────────────────────────────────────────────
THRESHOLD_FAITHFULNESS = float(os.getenv("EVAL_FAITHFULNESS_THRESHOLD", "0.7"))
THRESHOLD_ANSWER_RELEVANCY = float(os.getenv("EVAL_ANSWER_RELEVANCY_THRESHOLD", "0.7"))
THRESHOLD_CONTEXT_PRECISION = float(os.getenv("EVAL_CONTEXT_PRECISION_THRESHOLD", "0.6"))
THRESHOLD_CONTEXT_RECALL = float(os.getenv("EVAL_CONTEXT_RECALL_THRESHOLD", "0.6"))

DATASET_PATH = pathlib.Path(__file__).parent / "eval_dataset.json"


# ── pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline(question: str) -> tuple[str, list[str]]:
    """Answer one question; return the answer and the retrieved chunk texts."""
    try:
        result = rag.ask(question, index=EVAL_INDEX, llm_model=LLM_MODEL_NAME)
    except requests.RequestException as exc:
        pytest.fail(f"Pipeline failed for {question!r}: {exc}")
    return result["answer"], [c["content"] for c in result["contexts"]]


# ── RAGAS wrappers ────────────────────────────────────────────────────────────

def _build_ragas_llm_and_embeddings():
    """
    Wrap local Ollama models for RAGAS. Skips the test if dependencies are
    missing so that CI without RAGAS installed degrades gracefully.
    """
    try:
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from langchain_ollama import ChatOllama, OllamaEmbeddings
    except ImportError as exc:
        pytest.skip(f"RAGAS/langchain-ollama not installed: {exc}")

    llm = LangchainLLMWrapper(ChatOllama(model=LLM_MODEL_NAME, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(model=EMBED_MODEL)
    )
    return llm, embeddings


def _ragas_evaluate(samples_data: list[dict]) -> dict:
    """
    Build a RAGAS EvaluationDataset and run the configured metrics.

    Args:
        samples_data: list of dicts with keys: question, answer, contexts,
                      ground_truth (may be empty string).

    Returns:
        dict mapping metric name → mean score across all samples.
    """
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.metrics import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as exc:
        pytest.skip(f"RAGAS not installed: {exc}")

    llm, embeddings = _build_ragas_llm_and_embeddings()

    has_all_ground_truths = all(s.get("ground_truth") for s in samples_data)

    metrics = [
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=embeddings),
    ]
    if has_all_ground_truths:
        metrics += [
            ContextPrecision(llm=llm),
            ContextRecall(llm=llm),
        ]
    else:
        print(
            "\n[eval] 'ground_truth' missing for one or more entries — "
            "skipping context_precision and context_recall.\n"
            "Fill in the 'ground_truth' fields in tests/eval/eval_dataset.json "
            "to enable those metrics.\n"
        )

    ragas_samples = [
        SingleTurnSample(
            user_input=s["question"],
            response=s["answer"],
            retrieved_contexts=s["contexts"],
            reference=s["ground_truth"] if s.get("ground_truth") else None,
        )
        for s in samples_data
    ]

    dataset = EvaluationDataset(samples=ragas_samples)
    result = evaluate(dataset=dataset, metrics=metrics)
    return dict(result)


# ── pytest test ───────────────────────────────────────────────────────────────

@pytest.mark.slow
def test_rag_quality():
    """
    End-to-end RAG quality gate.

    Runs every entry in tests/eval/eval_dataset.json through the full pipeline
    (embed → retrieve → generate) and evaluates the outputs with RAGAS.
    Fails if any metric score falls below its configured threshold.
    """
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    assert dataset, "eval_dataset.json is empty — add questions to evaluate."

    samples_data: list[dict] = []
    for entry in dataset:
        question = entry["question"]
        answer, contexts = _run_pipeline(question)
        samples_data.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": entry.get("ground_truth", ""),
            }
        )

    scores = _ragas_evaluate(samples_data)

    # ── report ────────────────────────────────────────────────────────────────
    print("\n── RAGAS Evaluation Results ─────────────────────────────────────")
    thresholds = {
        "faithfulness": THRESHOLD_FAITHFULNESS,
        "answer_relevancy": THRESHOLD_ANSWER_RELEVANCY,
        "context_precision": THRESHOLD_CONTEXT_PRECISION,
        "context_recall": THRESHOLD_CONTEXT_RECALL,
    }
    for metric, score in scores.items():
        threshold = thresholds.get(metric, 0.0)
        status = "PASS" if score >= threshold else "FAIL"
        print(f"  {metric:<30}  {score:.3f}  (threshold {threshold:.2f})  [{status}]")
    print("─────────────────────────────────────────────────────────────────\n")

    # ── assertions ────────────────────────────────────────────────────────────
    if "faithfulness" in scores:
        assert scores["faithfulness"] >= THRESHOLD_FAITHFULNESS, (
            f"Faithfulness {scores['faithfulness']:.3f} below threshold "
            f"{THRESHOLD_FAITHFULNESS}. The model may be hallucinating."
        )
    if "answer_relevancy" in scores:
        assert scores["answer_relevancy"] >= THRESHOLD_ANSWER_RELEVANCY, (
            f"AnswerRelevancy {scores['answer_relevancy']:.3f} below threshold "
            f"{THRESHOLD_ANSWER_RELEVANCY}. Answers are not addressing the questions."
        )
    if "context_precision" in scores:
        assert scores["context_precision"] >= THRESHOLD_CONTEXT_PRECISION, (
            f"ContextPrecision {scores['context_precision']:.3f} below threshold "
            f"{THRESHOLD_CONTEXT_PRECISION}. Retrieved chunks contain too much noise."
        )
    if "context_recall" in scores:
        assert scores["context_recall"] >= THRESHOLD_CONTEXT_RECALL, (
            f"ContextRecall {scores['context_recall']:.3f} below threshold "
            f"{THRESHOLD_CONTEXT_RECALL}. Retrieval is missing key information."
        )


# ── standalone runner (python -m tests.eval.test_rag_eval) ────────────────────────

if __name__ == "__main__":
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    samples_data = []
    for i, entry in enumerate(dataset, 1):
        question = entry["question"]
        print(f"\n[{i}/{len(dataset)}] Q: {question}")
        answer, contexts = _run_pipeline(question)
        print(f"  answer  : {answer[:200]}{'...' if len(answer) > 200 else ''}")
        print(f"  chunks  : {len(contexts)} retrieved")
        samples_data.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": entry.get("ground_truth", ""),
            }
        )

    scores = _ragas_evaluate(samples_data)

    print("\n── RAGAS Evaluation Results ─────────────────────────────────────")
    thresholds = {
        "faithfulness": THRESHOLD_FAITHFULNESS,
        "answer_relevancy": THRESHOLD_ANSWER_RELEVANCY,
        "context_precision": THRESHOLD_CONTEXT_PRECISION,
        "context_recall": THRESHOLD_CONTEXT_RECALL,
    }
    for metric, score in scores.items():
        threshold = thresholds.get(metric, 0.0)
        status = "PASS" if score >= threshold else "FAIL"
        print(f"  {metric:<30}  {score:.3f}  (threshold {threshold:.2f})  [{status}]")
    print("─────────────────────────────────────────────────────────────────")
