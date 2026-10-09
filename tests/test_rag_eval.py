"""
RAG evaluation using RAGAS metrics against a FastAPI endpoint.

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

Usage:
  pytest tests/test_rag_eval.py -v -s
  python tests/test_rag_eval.py          # standalone with printed report

Pre-requisites:
  - FastAPI service running on http://localhost:8000
  - Use 'docker compose up' or 'uvicorn generating.app:app --port 8000'
"""

import json
import os
import pathlib
import sys

import pytest
import httpx

# ── make src importable when run directly ────────────────────────────────────
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Configuration from environment
EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:latest")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemma4:latest")

# ── configuration ─────────────────────────────────────────────────────────────
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")

# ── thresholds ────────────────────────────────────────────────────────────────
THRESHOLD_FAITHFULNESS = float(os.getenv("EVAL_FAITHFULNESS_THRESHOLD", "0.7"))
THRESHOLD_ANSWER_RELEVANCY = float(os.getenv("EVAL_ANSWER_RELEVANCY_THRESHOLD", "0.7"))
THRESHOLD_CONTEXT_PRECISION = float(os.getenv("EVAL_CONTEXT_PRECISION_THRESHOLD", "0.6"))
THRESHOLD_CONTEXT_RECALL = float(os.getenv("EVAL_CONTEXT_RECALL_THRESHOLD", "0.6"))

DATASET_PATH = pathlib.Path(__file__).parent / "eval_dataset.json"


# ── HTTP pipeline ─────────────────────────────────────────────────────────────

def _run_pipeline(question: str, session_id: str = "eval") -> tuple[str, list[str]]:
    """
    Run the full RAG pipeline for one question via FastAPI HTTP endpoint.

    Returns:
        answer          - validated LLM response string
        context_strings - list of raw retrieved chunk texts
    """
    try:
        with httpx.Client(timeout=120.0) as client:
            # Call the FastAPI chat endpoint
            response = client.post(
                f"{FASTAPI_BASE_URL}/api/chat",
                json={
                    "query": question,
                    "session_id": session_id,
                }
            )
            response.raise_for_status()
            
            # Parse the streaming response to extract answer and contexts
            answer_parts = []
            contexts = []
            
            for line in response.text.strip().split('\n'):
                if line.startswith('event: text'):
                    continue
                elif line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if data.get('type') == 'text':
                            answer_parts.append(data.get('content', ''))
                        elif data.get('type') == 'contexts':
                            contexts = data.get('data', [])
                    except json.JSONDecodeError:
                        continue
            
            answer = ''.join(answer_parts)
            context_strings = [ctx.get('content', '') for ctx in contexts]
            
            return answer, context_strings
            
    except httpx.RequestError as exc:
        pytest.fail(
            f"Failed to connect to FastAPI service at {FASTAPI_BASE_URL}: {exc}\n"
            f"Please ensure the service is running with:\n"
            f"  docker compose up\n"
            f"  -- or --\n"
            f"  uvicorn generating.app:app --port 8000"
        )
    except httpx.HTTPStatusError as exc:
        pytest.fail(
            f"FastAPI service returned error {exc.response.status_code}: {exc.response.text}"
        )


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
            "Fill in the 'ground_truth' fields in tests/eval_dataset.json "
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

    Runs every entry in tests/eval_dataset.json through the full pipeline
    (embed → retrieve → generate) and evaluates the outputs with RAGAS.
    Fails if any metric score falls below its configured threshold.
    """
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    assert dataset, "eval_dataset.json is empty — add questions to evaluate."

    samples_data: list[dict] = []
    for entry in dataset:
        question = entry["question"]
        # Use a unique session ID per test entry to avoid state interference
        session_id = f"eval_{hash(question) % 10000}"
        answer, contexts = _run_pipeline(question, session_id)
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


# ── standalone runner (python tests/test_rag_eval.py) ────────────────────────

if __name__ == "__main__":
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    samples_data = []
    for i, entry in enumerate(dataset, 1):
        question = entry["question"]
        # Use a unique session ID per test entry to avoid state interference
        session_id = f"eval_{hash(question) % 10000}"
        print(f"\n[{i}/{len(dataset)}] Q (session: {session_id}): {question}")
        answer, contexts = _run_pipeline(question, session_id)
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
