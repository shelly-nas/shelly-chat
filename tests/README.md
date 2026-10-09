# Testing Framework & Evaluation

Comprehensive testing suite for the RAG system, including unit tests, integration tests, and evaluation metrics for retrieval accuracy and response quality.

## Directory Contents

```
tests/
├── README.md              # This documentation
├── __init__.py           # Python package initialization
├── conftest.py           # Pytest configuration and fixtures
├── test_rag_eval.py      # RAG evaluation test suite
├── eval_dataset.json     # Test questions and expected answers
└── reports/              # Generated test reports and metrics
    ├── coverage/         # Code coverage reports
    ├── benchmarks/       # Performance benchmark results
    └── evaluations/      # RAG quality evaluation results
```

## Test Categories

### 1. Unit Tests

- **Component Testing** - Individual service and function validation
- **Configuration Testing** - Environment variable and setting validation
- **Utility Testing** - Helper functions and data processing utilities

### 2. Integration Tests

- **End-to-End Pipeline** - Document ingestion through response generation
- **Service Communication** - API endpoints and service integration
- **Database Operations** - Vector storage and retrieval functionality

### 3. RAG Evaluation

- **Retrieval Accuracy** - Source relevance and ranking quality
- **Response Quality** - Answer correctness and citation accuracy
- **Performance Benchmarks** - Speed and resource utilization metrics

## Quick Start

### Prerequisites

- **System Services** - All RAG components running locally
- **Test Data** - Sample documents and evaluation questions
- **Python Environment** - Testing dependencies installed

### Running Tests

**Basic Test Suite:**

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests with verbose output
python -m pytest tests/ -v

# Run specific test category
python -m pytest tests/test_rag_eval.py -v

# Run with coverage reporting
python -m pytest tests/ --cov=src --cov=indexing --cov=generating
```

**RAG Evaluation:**

```bash
# Run comprehensive RAG evaluation
python -m pytest tests/test_rag_eval.py::test_rag_evaluation -v -s

# Generate evaluation report
python tests/test_rag_eval.py --generate-report
```

### Test Configuration

**Environment Setup:**

```bash
# Test-specific environment variables
export TEST_QDRANT_URL=http://localhost:6333
export TEST_OLLAMA_URL=http://localhost:11434
export TEST_DATA_DIR=./test_documents
export EVALUATION_DATASET=./tests/eval_dataset.json
```

## RAG Evaluation Framework

### Evaluation Metrics

**Retrieval Metrics:**

- **Precision@K** - Relevant documents in top-K results
- **Recall@K** - Coverage of all relevant documents
- **Mean Reciprocal Rank (MRR)** - Ranking quality of first relevant result
- **NDCG@K** - Normalized discounted cumulative gain

**Response Quality Metrics:**

- **BLEU Score** - N-gram overlap with reference answers
- **ROUGE Score** - Summary quality and coverage
- **BERTScore** - Semantic similarity using embeddings
- **Citation Accuracy** - Correctness of source references

**Performance Metrics:**

- **Response Latency** - Time from query to first/last token
- **Throughput** - Queries handled per second
- **Resource Usage** - Memory and CPU utilization
- **Cache Hit Rate** - Efficiency of caching layers

### Evaluation Dataset

**Structure of `eval_dataset.json`:**

```json
{
  "metadata": {
    "version": "1.0",
    "created": "2024-01-15",
    "description": "RAG evaluation questions and ground truth answers"
  },
  "test_cases": [
    {
      "id": 1,
      "question": "What are the main requirements for remote work?",
      "category": "policy",
      "difficulty": "easy",
      "expected_sources": [
        {
          "file_path": "hr_handbook.pdf",
          "page_number": 23,
          "section": "Remote Work Policy"
        }
      ],
      "reference_answer": "Remote work requires manager approval, VPN access, and weekly check-ins as outlined in section 4.2.",
      "evaluation_criteria": {
        "must_include": ["manager approval", "VPN", "check-ins"],
        "should_cite": ["hr_handbook.pdf"]
      }
    }
  ]
}
```

**Test Case Categories:**

- **Factual** - Direct information lookup
- **Analytical** - Synthesis across multiple sources
- **Comparative** - Contrasting different policies or procedures
- **Temporal** - Date-sensitive or version-specific information

### Running Evaluations

**Comprehensive Evaluation:**

```python
# tests/test_rag_eval.py
import json
import pytest
from evaluation.metrics import calculate_rag_metrics
from evaluation.dataset import load_evaluation_dataset

def test_rag_evaluation():
    """Run comprehensive RAG system evaluation."""

    # Load test questions
    dataset = load_evaluation_dataset("eval_dataset.json")
    results = []

    for test_case in dataset["test_cases"]:
        # Query the RAG system
        response = query_rag_system(test_case["question"])

        # Calculate metrics
        metrics = calculate_rag_metrics(
            response=response,
            reference=test_case["reference_answer"],
            expected_sources=test_case["expected_sources"]
        )

        results.append({
            "test_id": test_case["id"],
            "question": test_case["question"],
            "category": test_case["category"],
            "metrics": metrics,
            "response": response
        })

    # Generate evaluation report
    generate_evaluation_report(results)

    # Assert overall performance thresholds
    avg_precision = sum(r["metrics"]["precision"] for r in results) / len(results)
    assert avg_precision >= 0.7, f"Average precision {avg_precision} below threshold"
```

## Performance Benchmarking

### Benchmark Categories

**Indexing Performance:**

```python
def test_indexing_performance(benchmark):
    """Benchmark document indexing speed."""

    test_documents = load_test_documents(count=100)

    def run_indexing():
        run_indexing_pipeline(test_documents)

    # Run benchmark with timing
    result = benchmark(run_indexing)

    # Assert performance requirements
    assert result.avg < 2.0, f"Indexing too slow: {result.avg}s per document"
```

**Query Performance:**

```python
def test_query_performance(benchmark):
    """Benchmark query response times."""

    test_queries = [
        "What is the vacation policy?",
        "How do I request equipment?",
        "What are the security requirements?"
    ]

    def run_queries():
        for query in test_queries:
            query_rag_system(query)

    result = benchmark(run_queries)

    # Assert latency requirements
    assert result.avg < 3.0, f"Query latency too high: {result.avg}s"
```

**Memory Usage:**

```python
import psutil
import pytest

def test_memory_usage():
    """Monitor memory usage during operations."""

    process = psutil.Process()
    initial_memory = process.memory_info().rss

    # Perform memory-intensive operations
    run_large_document_indexing()
    run_concurrent_queries(count=50)

    final_memory = process.memory_info().rss
    memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB

    # Assert memory usage is reasonable
    assert memory_increase < 500, f"Memory usage increased by {memory_increase}MB"
```

## Test Fixtures & Utilities

### Pytest Configuration (`conftest.py`)

**Common Fixtures:**

```python
import pytest
from qdrant_client import QdrantClient
from indexing.indexer import run_indexing_pipeline

@pytest.fixture(scope="session")
def test_qdrant_client():
    """Provide Qdrant client for testing."""
    client = QdrantClient(url="http://localhost:6333")
    yield client

@pytest.fixture(scope="function")
def clean_collections(test_qdrant_client):
    """Ensure clean collections for each test."""
    # Clear test collections before test
    test_qdrant_client.delete(
        collection_name="test_chunks_child",
        points_selector=models.FilterSelector(must=[])
    )
    yield
    # Cleanup after test if needed

@pytest.fixture
def sample_documents():
    """Provide sample documents for testing."""
    return [
        {
            "file_path": "test_doc1.pdf",
            "content": "Sample document content for testing...",
            "metadata": {"page_count": 5, "size": "42KB"}
        },
        # ... more test documents
    ]

@pytest.fixture
def mock_ollama_server():
    """Mock Ollama server for testing without external dependencies."""
    with mock.patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = {
            'embedding': [0.1] * 768  # Mock 768-dim embedding
        }
        yield mock_post
```

### Test Utilities

**RAG System Testing Helpers:**

```python
# tests/utils.py
from typing import List, Dict, Any

def query_rag_system(question: str, session_id: str = "test") -> Dict[str, Any]:
    """Query the RAG system and return structured response."""

    import requests

    response = requests.post("http://localhost:8000/api/chat", json={
        "message": question,
        "session_id": session_id,
        "stream": False
    })

    return response.json()

def assert_citation_accuracy(response: Dict[str, Any], expected_sources: List[str]):
    """Validate that response cites expected sources."""

    cited_sources = [s['file_path'] for s in response.get('sources', [])]

    for expected in expected_sources:
        assert any(expected in cited for cited in cited_sources), \
            f"Expected source {expected} not found in citations"

def calculate_response_similarity(response: str, reference: str) -> float:
    """Calculate semantic similarity between response and reference."""

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')

    embeddings = model.encode([response, reference])
    similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]

    return similarity
```

## Continuous Testing

### GitHub Actions Integration

**Test Workflow (`.github/workflows/test.yml`):**

```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      qdrant:
        image: qdrant/qdrant
        ports:
          - 6333:6333
        options: >-
          --health-cmd "curl -f http://localhost:6333/health || exit 1"
          --health-interval 30s
          --health-timeout 10s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v3
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: |
          uv pip install --system -r requirements.txt
          uv pip install --system pytest pytest-cov pytest-benchmark

      - name: Initialize test database
        run: python vector-db/init_collections.py

      - name: Run tests with coverage
        run: |
          pytest tests/ --cov=src --cov=indexing --cov=generating \
            --cov-report=xml --cov-report=html

      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### Pre-commit Hooks

**Quality Checks (`.pre-commit-config.yaml`):**

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-check
        name: pytest-check
        entry: pytest
        language: system
        args: [tests/unit_tests/, -v]
        always_run: true
        pass_filenames: false

      - id: evaluation-smoke-test
        name: evaluation-smoke-test
        entry: pytest
        language: system
        args: [tests/test_rag_eval.py::test_basic_rag_functionality, -v]
        always_run: true
        pass_filenames: false
```

## Evaluation Reports

### Automated Report Generation

**Evaluation Report Structure:**

```python
def generate_evaluation_report(results: List[Dict]) -> Dict:
    """Generate comprehensive evaluation report."""

    report = {
        "summary": {
            "total_questions": len(results),
            "avg_precision": calculate_avg_metric(results, "precision"),
            "avg_recall": calculate_avg_metric(results, "recall"),
            "avg_response_time": calculate_avg_metric(results, "response_time"),
            "citation_accuracy": calculate_citation_accuracy(results)
        },
        "category_breakdown": group_by_category(results),
        "failure_analysis": identify_problem_areas(results),
        "recommendations": generate_recommendations(results),
        "detailed_results": results
    }

    # Save report with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"tests/reports/evaluations/rag_eval_{timestamp}.json"

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    return report
```

**Sample Report Output:**

```json
{
  "summary": {
    "total_questions": 50,
    "avg_precision": 0.84,
    "avg_recall": 0.78,
    "avg_response_time": 2.3,
    "citation_accuracy": 0.92
  },
  "category_breakdown": {
    "policy": { "precision": 0.89, "recall": 0.85 },
    "technical": { "precision": 0.76, "recall": 0.68 },
    "procedural": { "precision": 0.91, "recall": 0.82 }
  },
  "failure_analysis": {
    "common_issues": [
      "Missing citations for complex multi-step procedures",
      "Lower accuracy on technical documentation",
      "Inconsistent handling of policy exceptions"
    ]
  }
}
```

## Debugging Failed Tests

### Common Test Failures

**Service Connection Issues:**

```python
def test_service_health():
    """Verify all required services are accessible."""

    # Test Qdrant connection
    try:
        client = QdrantClient(url="http://localhost:6333")
        health = client.get_collections()
        assert "chunks_child" in [c.name for c in health.collections]
    except Exception as e:
        pytest.fail(f"Qdrant connection failed: {e}")

    # Test Ollama connection
    try:
        response = requests.get("http://localhost:11434/api/tags")
        assert response.status_code == 200
    except Exception as e:
        pytest.fail(f"Ollama connection failed: {e}")
```

**Data Quality Issues:**

```python
def test_retrieval_quality():
    """Validate that retrieval returns relevant results."""

    query = "What is the vacation policy?"
    results = query_rag_system(query)

    # Check that sources are relevant
    sources = results.get('sources', [])
    assert len(sources) > 0, "No sources returned"

    # Verify similarity scores are reasonable
    avg_similarity = sum(s['similarity'] for s in sources) / len(sources)
    assert avg_similarity >= 0.6, f"Low similarity scores: {avg_similarity}"

    # Check citation consistency
    response_text = results.get('response', '')
    citation_count = len(re.findall(r'\[\d+\]', response_text))
    assert citation_count <= len(sources), "More citations than sources"
```

### Test Debugging Tools

**Verbose Test Output:**

```bash
# Run tests with maximum verbosity
pytest tests/test_rag_eval.py -vvv -s

# Show local variables on failure
pytest tests/test_rag_eval.py --tb=long

# Run single test with debugging
pytest tests/test_rag_eval.py::test_specific_function -vvv -s --pdb
```

**Log Analysis:**

```python
import logging
logging.basicConfig(level=logging.DEBUG)

def test_with_detailed_logging():
    """Test with comprehensive logging enabled."""

    logger = logging.getLogger(__name__)

    logger.debug("Starting RAG evaluation test")
    response = query_rag_system("test question")
    logger.debug(f"Response received: {response}")

    # Log intermediate steps for debugging
    for i, source in enumerate(response.get('sources', [])):
        logger.debug(f"Source {i}: similarity={source['similarity']}")
```

## Integration with Development Workflow

### Quality Gates

Tests serve as quality gates throughout development:

**Pre-commit Quality Checks:**

- Unit tests must pass before commit
- Code coverage thresholds enforced
- Basic RAG functionality smoke tests

**Pull Request Validation:**

- Full test suite execution
- Performance regression detection
- Evaluation metric comparisons

**Release Validation:**

- Comprehensive RAG evaluation
- Performance benchmarking
- End-to-end integration tests

### Continuous Monitoring

**Production Health Checks:**

- Subset of evaluation questions run regularly
- Performance metrics tracked over time
- Alert thresholds for quality degradation

For additional testing configurations and advanced evaluation techniques, see the individual test files and the project's CI/CD documentation.
