"""FastAPI backend — LlamaIndex retrieval + Ollama streaming LLM.

Retrieval flow (per SETUP.md):
  User query
    → [optional] query expansion: abbreviation dict lookup (abbreviations.json)
    → embed (qwen3-embedding:latest via Ollama)
    → vector search child nodes (Qdrant, top-K)
    → SentenceTransformerRerank (top-N)
    → AutoMergingRetriever (parent nodes where merge threshold met)
    → Ollama LLM (streamed via SSE)
    → StreamingResponse
"""

import json
import logging
import os
import subprocess
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from qdrant_client.http.exceptions import UnexpectedResponse as QdrantUnexpectedResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from llama_index.core import Settings, StorageContext, PromptTemplate
from llama_index.core import VectorStoreIndex
from llama_index.core.indices.query.schema import QueryBundle
from llama_index.core.schema import NodeRelationship
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from generating.generator import get_llm
from generating.query_expander import expand_query_from_dict
from generating import indexing_runner
from indexing.lock import indexing_lock, lock_path_for

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# Configuration from environment
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_CHILD_COLLECTION = os.getenv("QDRANT_CHILD_COLLECTION", "chunks_child")
EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "20"))
RERANKER_TOP_N = int(os.getenv("RERANKER_TOP_N", "5"))
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
AUTOMERGE_THRESHOLD = float(os.getenv("AUTOMERGE_THRESHOLD", "0.5"))
DOCSTORE_PATH = os.getenv("DOCSTORE_PATH", "vector-db/docstore.json")
LLM_SYSTEM_PROMPT = os.getenv("LLM_SYSTEM_PROMPT", "You are a helpful assistant.")
NO_ANSWER_RESPONSE = os.getenv("NO_ANSWER_RESPONSE", "I could not find this in the provided sources.")
CHAT_HISTORY_MAX_TURNS = int(os.getenv("CHAT_HISTORY_MAX_TURNS", "10"))
QUERY_MAX_LENGTH = int(os.getenv("QUERY_MAX_LENGTH", "2000"))
VERBOSE = os.getenv("VERBOSE", "0") == "1"
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemma4:latest")
QUERY_EXPANSION_TOP_K = int(os.getenv("QUERY_EXPANSION_TOP_K", "5"))
QUERY_EXPANSION_TIMEOUT = 60.0
ABBREVIATIONS_PATH = os.getenv("ABBREVIATIONS_PATH", "vector-db/abbreviations.json")
OLLAMA_API_TIMEOUT = 10  # Timeout in seconds for Ollama management API calls (/api/ps, unload)

# ── Resource Management Helpers ───────────────────────────────────────────────

def list_loaded_ollama_models(base_url: str = OLLAMA_BASE_URL) -> list:
    """Get list of currently loaded models from Ollama."""
    try:
        # Format the base_url to ensure it has the correct scheme
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        
        # Use the Ollama API endpoint to list running models
        response = requests.get(f"{base_url}/api/ps", timeout=OLLAMA_API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            # Ollama /api/ps returns {'models': [{'name': ..., 'size': ..., ...}, ...]}
            return data.get('models', [])
        else:
            if VERBOSE:
                logger.warning(f"Failed to list loaded models: HTTP {response.status_code}")
            return []
            
    except requests.exceptions.RequestException as e:
        if VERBOSE:
            logger.error(f"Error connecting to Ollama API: {e}")
        return []
    except Exception as e:
        if VERBOSE:
            logger.error(f"Error listing loaded models: {e}")
        return []

def unload_ollama_model(model_name: str, base_url: str = OLLAMA_BASE_URL) -> bool:
    """Unload a specific model from Ollama to free memory."""
    try:
        # Format the base_url to ensure it has the correct scheme
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        
        # Use the correct Ollama API endpoint to unload the model
        # Send a request with keep_alive=0 to unload the model immediately
        response = requests.post(
            f"{base_url}/api/generate", 
            json={
                "model": model_name,
                "keep_alive": 0,
                "prompt": ""
            }, 
            timeout=OLLAMA_API_TIMEOUT
        )
        
        if response.status_code == 200:
            if VERBOSE:
                logger.info(f"Successfully unloaded model: {model_name}")
            return True
        else:
            if VERBOSE:
                logger.warning(f"Failed to unload model {model_name}: HTTP {response.status_code}")
            return False
    except Exception as e:
        if VERBOSE:
            logger.error(f"Error unloading model {model_name}: {e}")
        return False

def wait_for_model_unload(model_name: str, max_wait_seconds: int = 10) -> bool:
    """Wait for a model to be completely unloaded from Ollama."""
    import time
    
    for i in range(max_wait_seconds):
        try:
            loaded_models = list_loaded_ollama_models()
            model_names = [m.get('name', '') for m in loaded_models]
            
            if model_name not in model_names:
                if VERBOSE:
                    logger.info(f"Model {model_name} successfully unloaded after {i+1}s")
                return True
                
            if VERBOSE and i == 0:
                logger.info(f"Waiting for {model_name} to unload...")
                
            time.sleep(1)
        except Exception as e:
            if VERBOSE:
                logger.warning(f"Error checking model status: {e}")
            time.sleep(1)
    
    if VERBOSE:
        logger.warning(f"Model {model_name} still loaded after {max_wait_seconds}s timeout")
    return False

# ── LlamaIndex global setup ───────────────────────────────────────────────────

_llm = get_llm()
Settings.llm = _llm

# Set placeholder embedding model for VectorStoreIndex initialization
# This will be overridden per request for actual embedding operations
_placeholder_embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
Settings.embed_model = _placeholder_embed_model

_qdrant_client = QdrantClient(url=QDRANT_URL)
_vector_store = QdrantVectorStore(
    client=_qdrant_client,
    collection_name=QDRANT_CHILD_COLLECTION,
)

_docstore_path = Path(DOCSTORE_PATH)
_docstore = (
    SimpleDocumentStore.from_persist_path(str(_docstore_path))
    if _docstore_path.exists()
    else SimpleDocumentStore()
)
logger.info(
    "Docstore loaded: %d nodes from '%s'",
    len(_docstore.docs),
    _docstore_path if _docstore_path.exists() else "(empty — file not found)",
)

_storage_context = StorageContext.from_defaults(
    vector_store=_vector_store,
    docstore=_docstore,
)
_index = VectorStoreIndex.from_vector_store(
    _vector_store,
    storage_context=_storage_context,
)

# Retriever will be created per request with temporary embed model

def reload_retrieval_state() -> None:
    """Reload docstore and rebuild index after indexing completes."""
    global _docstore, _storage_context, _index
    # Shared lock: block while an indexer holds the exclusive write lock so we
    # never read docstore.json mid-rewrite.
    with indexing_lock(lock_path_for(DOCSTORE_PATH), exclusive=False):
        new_docstore = (
            SimpleDocumentStore.from_persist_path(str(_docstore_path))
            if _docstore_path.exists()
            else SimpleDocumentStore()
        )
    new_storage_context = StorageContext.from_defaults(
        vector_store=_vector_store,
        docstore=new_docstore,
    )
    new_index = VectorStoreIndex.from_vector_store(
        _vector_store,
        storage_context=new_storage_context,
    )
    _docstore = new_docstore
    _storage_context = new_storage_context
    _index = new_index
    logger.info("Retrieval state reloaded: %d nodes in docstore", len(_docstore.docs))

_reranker = SentenceTransformerRerank(
    model=RERANKER_MODEL_NAME,
    top_n=RERANKER_TOP_N,
)

# QA prompt template — context + question, no manual string concatenation.
_QA_TEMPLATE = PromptTemplate(
    "SOURCES:\n"
    "{context_str}\n\n"
    "QUESTION: {query_str}\n\n"
    "ANSWER:"
)

# ── FastAPI application ───────────────────────────────────────────────────────

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/status")
def status():
    result = {"backend": "healthy"}

    try:
        resp = requests.get(f"{QDRANT_URL}/healthz", timeout=2)
        result["qdrant"] = "healthy" if resp.ok else "unhealthy"
    except Exception:
        result["qdrant"] = "unreachable"

    try:
        resp = requests.get(OLLAMA_BASE_URL, timeout=2)
        result["ollama"] = "healthy" if resp.ok else "unhealthy"
    except Exception:
        result["ollama"] = "unreachable"

    return result

@app.get("/api/models/status")
async def models_status():
    """Get status of currently loaded models in Ollama."""
    try:
        loaded_models = list_loaded_ollama_models()
        return {
            "status": "success",
            "loaded_models": loaded_models,
            "embed_model": EMBED_MODEL,
            "llm_model": _llm.model,
            "behavior": "Sequential: embed model unloaded after embedding, LLM loaded for generation",
            "embed_model_timeout": OLLAMA_API_TIMEOUT,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/models/unload")
async def unload_model(model_name: str = None):
    """Manually unload a specific model or the embedding model."""
    target_model = model_name or EMBED_MODEL
    try:
        success = unload_ollama_model(target_model)
        
        return {
            "status": "success" if success else "partial_success",
            "message": f"Attempted to unload {target_model}",
            "unload_success": success,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/models/cleanup")
async def cleanup_all_models():
    """Force cleanup of all loaded models."""
    try:
        loaded_models = list_loaded_ollama_models()
        unloaded = []
        
        for model in loaded_models:
            model_name = model.get('name', '')
            if unload_ollama_model(model_name):
                unloaded.append(model_name)
        
        return {
            "status": "success",
            "message": "Cleanup completed",
            "unloaded_models": unloaded,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ── Indexing endpoints ────────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    full_reindex: bool = False
    build_abbreviations: bool = False


@app.post("/api/index", status_code=202)
async def trigger_index(request: IndexRequest = IndexRequest()):
    """Start a background indexing run. Returns 409 if already running."""
    try:
        indexing_runner.start_indexing(
            full_reindex=request.full_reindex,
            build_abbreviations=request.build_abbreviations,
            on_complete=reload_retrieval_state,
        )
    except RuntimeError:
        raise HTTPException(status_code=409, detail="Indexering is al bezig.")
    return {"status": "started"}


@app.get("/api/index/status")
async def index_status():
    """Return current indexing state: idle | running | done | error."""
    return indexing_runner.get_status()


# ── Per-session state ─────────────────────────────────────────────────────────

_MAX_SESSIONS = 100
_sessions: dict[str, dict] = {}
_session_timestamps: dict[str, float] = {}


def _get_session(session_id: str) -> dict:
    """Return session dict for *session_id*, creating it if absent."""
    now = time.time()
    if session_id not in _sessions and len(_sessions) >= _MAX_SESSIONS:
        oldest = min(_session_timestamps, key=_session_timestamps.get)
        _sessions.pop(oldest, None)
        _session_timestamps.pop(oldest, None)
    if session_id not in _sessions:
        _sessions[session_id] = {"chat_history": []}
    _session_timestamps[session_id] = now
    return _sessions[session_id]


# ── Path-safety helper ────────────────────────────────────────────────────────

_SAFE_BASE = Path("data").resolve()


def _safe_path(raw: str) -> Path:
    """Resolve *raw* and raise 403 if it escapes DATA_DIRECTORY."""
    try:
        resolved = Path(raw).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path.")
    if _SAFE_BASE != resolved and _SAFE_BASE not in resolved.parents:
        raise HTTPException(status_code=403, detail="Access to this path is not allowed.")
    return resolved


# ── Request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    query_expansion_enabled: Optional[bool] = None

    @field_validator("query")
    @classmethod
    def query_length(cls, v: str) -> str:
        if len(v) > QUERY_MAX_LENGTH:
            raise ValueError(
                f"Query exceeds maximum allowed length of {QUERY_MAX_LENGTH} characters."
            )
        return v


class ResetRequest(BaseModel):
    session_id: str = "default"


# ── Chat endpoint ─────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def event_stream():
        session_data = _get_session(request.session_id)

        # Log initial state
        if VERBOSE:
            loaded_models = list_loaded_ollama_models()
            logger.info(f"STARTING REQUEST: {len(loaded_models)} models currently loaded")

        original_embed_model = Settings.embed_model

        if VERBOSE:
            logger.info(f"USER QUERY: {request.query}")
            logger.info(f"RETRIEVAL CONFIG: top_k={RETRIEVAL_TOP_K}, rerank_top_n={RERANKER_TOP_N}")

        # 1. Query expansion — fast dict lookup (no model loading needed)
        effective_query = request.query
        effective_expansion_enabled = request.query_expansion_enabled is not False

        applied_expansions: list = []
        if effective_expansion_enabled:
            try:
                effective_query, applied_expansions = expand_query_from_dict(
                    request.query, ABBREVIATIONS_PATH
                )
            except Exception as exc:
                logger.warning("Query expansion failed: %s", exc)

        yield f"event: expansions\ndata: {json.dumps(applied_expansions)}\n\n"

        # 2. Main retrieval — load embedding model
        temp_embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
        Settings.embed_model = temp_embed_model

        try:
            # Create temporary retriever with the embedding model
            base_retriever = _index.as_retriever(similarity_top_k=RETRIEVAL_TOP_K)
            retriever = AutoMergingRetriever(
                base_retriever,
                _storage_context,
                simple_ratio_thresh=AUTOMERGE_THRESHOLD,
                verbose=bool(VERBOSE),
            )

            # 3. Retrieve + merge nodes (AutoMergingRetriever, sync approach)
            try:
                # Use synchronous retrieve instead of aretrieve to avoid async issues
                nodes = retriever.retrieve(effective_query)
                
                if VERBOSE:
                    logger.info(f"RETRIEVED NODES: {len(nodes)} total")
                    for i, node in enumerate(nodes):
                        meta = node.metadata or {}
                        parent_id = node.node.parent_node.node_id[:12] if node.node.parent_node else "None"
                        in_store = (
                            "in docstore" if node.node.parent_node and _docstore.docs.get(node.node.parent_node.node_id)
                            else ("not in docstore" if node.node.parent_node else "—")
                        )
                        logger.info(f"  [{i+1}] ID: {node.node_id[:12]}... | Score: {node.score:.4f} | "
                                  f"Parent: {parent_id} ({in_store}) | "
                                  f"File: {meta.get('file_path', 'unknown')} | "
                                  f"Content: {node.get_content()}")
                        
            except QdrantUnexpectedResponse as exc:
                logger.error(
                    "Qdrant retrieval failed — collection may not exist yet. "
                    "Run the indexer first. Details: %s",
                    exc,
                )
                yield (
                    f"event: error\ndata: {json.dumps({'message': 'Vector store niet gevonden. Indexeer de documenten eerst.'})}\n\n"
                )
                return
            except ValueError as exc:
                if "not found" in str(exc):
                    logger.error(
                        "Docstore/Qdrant out of sync — parent node missing: %s. "
                        "Run the indexer with --full-reindex to fix.",
                        exc,
                    )
                    yield (
                        f"event: error\ndata: {json.dumps({'message': 'Index is niet synchroon. Voer een volledige herindexering uit.'})}\n\n"
                    )
                    return
                raise
        finally:
            # 3. Clean up embedding model after retrieval - hardcode always unload
            if VERBOSE:
                logger.info(f"CLEANING UP: Releasing embedding model and unloading from Ollama")
            Settings.embed_model = original_embed_model
            temp_embed_model = None
            
            # Always unload embed model to ensure sequential behavior
            try:
                if unload_ollama_model(EMBED_MODEL):
                    # Wait for the model to be completely unloaded
                    if wait_for_model_unload(EMBED_MODEL, max_wait_seconds=10):
                        if VERBOSE:
                            logger.info(f"Embedding model {EMBED_MODEL} successfully unloaded and verified")
                    else:
                        if VERBOSE:
                            logger.warning(f"Embedding model {EMBED_MODEL} unload verification timed out")
                else:
                    if VERBOSE:
                        logger.warning(f"Failed to unload embedding model: {EMBED_MODEL}")
            except Exception as e:
                if VERBOSE:
                    logger.error(f"Error unloading embedding model: {e}")
            
            # Add a small delay to ensure clean transition
            import time
            time.sleep(0.5)

        if VERBOSE:
            logger.info(f"Embedding phase complete. LLM will be loaded on-demand for generation.")

        # 4. Rerank retrieved nodes, then build the contexts payload.
        # Both steps run outside the retrieval try/finally above, so without
        # their own handler any exception here (e.g. a reranker failure, or a
        # merged parent node missing an expected field) would propagate out of
        # the generator uncaught — StreamingResponse then just drops the
        # connection with no event: contexts and no event: error, which looks
        # to the user like "no sources found" even though retrieval succeeded.
        try:
            query_bundle = QueryBundle(query_str=effective_query)
            nodes_before_rerank = nodes.copy() if VERBOSE else []
            nodes = _reranker.postprocess_nodes(nodes, query_bundle=query_bundle)

            if VERBOSE:
                logger.info(f"RERANKING: {len(nodes_before_rerank)} -> {len(nodes)} nodes")
                pre_parent_count = sum(
                    1 for n in nodes_before_rerank
                    if NodeRelationship.PARENT not in (n.node.relationships if hasattr(n, 'node') else n.relationships)
                )
                logger.info(f"PRE-RERANK CHUNK TYPES: {pre_parent_count} parent, {len(nodes_before_rerank) - pre_parent_count} child")
                logger.info(f"RERANKED RESULTS:")
                for i, node in enumerate(nodes):
                    meta = node.metadata or {}
                    rels = node.node.relationships if hasattr(node, 'node') else node.relationships
                    ctype = "child" if NodeRelationship.PARENT in rels else "parent"
                    logger.info(f"  [{i+1}] [{ctype}] ID: {node.node_id[:12]}... | Score: {node.score:.4f} | "
                              f"File: {meta.get('file_path', 'unknown')} | "
                              f"Content: {node.get_content()}")

            # 5. Build contexts payload for the frontend
            contexts = []
            for i, node in enumerate(nodes):
                meta = node.metadata or {}
                relationships = node.node.relationships if hasattr(node, 'node') else node.relationships
                chunk_type = "child" if NodeRelationship.PARENT in relationships else "parent"
                contexts.append({
                    "content": node.get_content(),
                    "file_path": meta.get("file_path", meta.get("file_name", "")),
                    "source_url": meta.get("source_url", ""),
                    "page_number": meta.get("page_number", meta.get("page_label", 1)),
                    "start_line": meta.get("start_line", 1),
                    "end_line": meta.get("end_line", 1),
                    "section_context": meta.get("section_context", ""),
                    "similarity": round(float(node.score or 0.0), 4),
                    "source_num": i + 1,
                    "chunk_type": chunk_type,
                })
        except Exception as exc:
            logger.error("Reranking or context-building failed: %s", exc, exc_info=True)
            yield (
                f"event: error\ndata: {json.dumps({'message': 'Verwerken van zoekresultaten is mislukt. Probeer het opnieuw.'})}\n\n"
            )
            return

        yield f"event: contexts\ndata: {json.dumps(contexts)}\n\n"
        
        if VERBOSE:
            logger.info(f"FINAL CONTEXTS: {len(contexts)} chunks for LLM")
            for i, ctx in enumerate(contexts):
                logger.info(f"  [{i+1}] [{ctx['chunk_type']}] {ctx['file_path']} (page {ctx['page_number']}) | "
                          f"Similarity: {ctx['similarity']:.4f} | "
                          f"Content: {ctx['content']}")

        # No context → refuse rather than hallucinate
        if not contexts:
            if VERBOSE:
                logger.warning("NO CONTEXTS FOUND - returning default response")
            yield f"event: token\ndata: {json.dumps(NO_ANSWER_RESPONSE)}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # 6. Build context string via PromptTemplate
        context_str = "\n\n".join(
            f"[{i + 1}] {c['file_path']} (page {c['page_number']})\n{c['content']}"
            for i, c in enumerate(contexts)
        )
        qa_text = _QA_TEMPLATE.format(
            context_str=context_str,
            query_str=effective_query,
        )
        
        if VERBOSE:
            logger.info(f"FORMATTED QA PROMPT:")
            logger.info(f"--- CONTEXT STRING ({len(context_str)} chars) ---")
            logger.info(context_str[:500] + ("..." if len(context_str) > 500 else ""))
            logger.info(f"--- FULL QA TEXT ({len(qa_text)} chars) ---")
            logger.info(qa_text)

        # 7. Build chat messages (system prompt + history + user question)
        system_content = LLM_SYSTEM_PROMPT.replace(
            "{today}", datetime.now().strftime("%Y-%m-%d")
        )
        messages = [ChatMessage(role=MessageRole.SYSTEM, content=system_content)]
        
        # Add chat history (limited to recent turns)
        recent_history = session_data["chat_history"][-(CHAT_HISTORY_MAX_TURNS * 2):]
        for turn in recent_history:
            role = MessageRole.USER if turn["role"] == "user" else MessageRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=turn["content"]))
        messages.append(ChatMessage(role=MessageRole.USER, content=qa_text))
        
        if VERBOSE:
            logger.info(f"COMPLETE LLM CONVERSATION:")
            logger.info(f"  Total messages: {len(messages)} (1 system + {len(recent_history)} history + 1 current)")
            for i, msg in enumerate(messages):
                role_label = "SYSTEM" if msg.role == MessageRole.SYSTEM else ("USER" if msg.role == MessageRole.USER else "ASSISTANT")
                content_preview = msg.content
                logger.info(f"  [{i+1}] {role_label}: {content_preview}")
            
            total_chars = sum(len(msg.content) for msg in messages)
            logger.info(f"TOTAL CONTEXT LENGTH: {total_chars} characters")

        # 8. Stream LLM response token-by-token
        full_response = ""
        gen_start = time.perf_counter()
        token_count = 0

        if VERBOSE:
            logger.info(f"STARTING LLM GENERATION (embedding model should be unloaded)...")
            # Verify no embedding model is loaded before starting LLM
            current_models = list_loaded_ollama_models()
            model_names = [m.get('name', '') for m in current_models]
            if EMBED_MODEL in model_names:
                logger.warning(f"WARNING: Embedding model {EMBED_MODEL} still loaded during LLM generation!")
            else:
                logger.info(f"Confirmed: Embedding model {EMBED_MODEL} not loaded, proceeding with LLM")

        try:
            if VERBOSE:
                logger.info(f"INITIALIZING LLM...")
            
            # Get the LLM instance - this will load the LLM model on-demand
            llm = get_llm()
            
            if VERBOSE:
                logger.info(f"LLM INITIALIZED, starting generation...")
            
            # Use proper streaming from LlamaIndex Ollama
            try:
                # Try using the stream_chat method for proper streaming
                streaming_response = llm.stream_chat(messages)
                
                for token in streaming_response:
                    token_str = str(token.delta)
                    if token_str:
                        full_response += token_str
                        token_count += 1
                        
                        yield f"event: token\ndata: {json.dumps(token_str)}\n\n"
                        
                        # Small delay to prevent overwhelming the frontend
                        import asyncio
                        await asyncio.sleep(0.01)
                        
            except Exception as stream_error:
                # Fallback to non-streaming if streaming fails
                if VERBOSE:
                    logger.warning(f"Streaming failed, falling back to complete response: {stream_error}")
                
                response = llm.chat(messages)
                full_response = response.message.content or ""
                
                if VERBOSE:
                    logger.info(f"LLM RESPONSE RECEIVED: {len(full_response)} characters")
                    logger.info(f"Response preview: {full_response[:200]}...")
                
                # Send the complete response as a single token
                if full_response:
                    token_count = len(full_response.split())
                    if VERBOSE:
                        logger.info(f"SENDING COMPLETE RESPONSE: {len(full_response)} chars")
                    yield f"event: token\ndata: {json.dumps(full_response)}\n\n"
        except Exception as e:
            if VERBOSE:
                logger.error(f"LLM STREAMING ERROR: {e}")
            yield f"event: error\ndata: {json.dumps({'message': f'LLM streaming failed: {str(e)}'})}\n\n"
            return

        gen_elapsed = time.perf_counter() - gen_start
        
        if VERBOSE:
            logger.info(f"LLM GENERATION COMPLETE:")
            logger.info(f"  Generation time: {gen_elapsed:.2f}s")
            logger.info(f"  Tokens generated: {token_count}")
            logger.info(f"  Response length: {len(full_response)} characters")
            logger.info(f"  Response preview: {full_response}")
            if token_count > 0:
                logger.info(f"  Tokens/second: {token_count / gen_elapsed:.1f}")
                
        metrics = {
            "wall_time_s": round(gen_elapsed, 2),
            "model": llm.model,
        }
        yield f"event: metrics\ndata: {json.dumps(metrics)}\n\n"

        # 9. Update chat history
        session_data["chat_history"].append({"role": "user", "content": effective_query})
        session_data["chat_history"].append({"role": "assistant", "content": full_response})

        if VERBOSE:
            logger.info(f"SESSION UPDATED: {len(session_data['chat_history'])} total messages")

        yield "event: done\ndata: {}\n\n"

        # Always unload LLM model after generation to free VRAM for next embed model call
        try:
            if unload_ollama_model(LLM_MODEL_NAME):
                if VERBOSE:
                    logger.info(f"LLM model {LLM_MODEL_NAME} unloaded after generation")
            else:
                if VERBOSE:
                    logger.warning(f"Failed to unload LLM model {LLM_MODEL_NAME}")
        except Exception as e:
            if VERBOSE:
                logger.error(f"Error unloading LLM model: {e}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset_session(request: ResetRequest):
    _sessions.pop(request.session_id, None)
    _session_timestamps.pop(request.session_id, None)
    return {"status": "ok"}


@app.get("/api/open-file")
async def open_file(path: str = Query(...)):
    """
    Return file information for the frontend to handle opening.
    The container doesn't need to access the file - just validate and return the path.
    """
    try:
        # Basic path validation - don't use _safe_path since we're not accessing the file
        if not path or ".." in path:
            raise HTTPException(status_code=400, detail="Invalid path")
        
        # Return file information for the frontend to handle
        # The frontend (running on host) can open the file
        from pathlib import Path
        file_path = Path(path)
        
        return {
            "status": "success", 
            "message": "File path ready for frontend to open",
            "path": path,
            "filename": file_path.name,
            "absolute_path": path,
            "file_extension": file_path.suffix.lower(),
            "note": "File opening will be handled by frontend on host system"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {str(e)}")


@app.get("/api/file")
async def get_file_content(path: str = Query(...)):
    safe = _safe_path(path)
    try:
        return {"content": safe.read_text(encoding="utf-8")}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
