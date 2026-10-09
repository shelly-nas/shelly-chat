"""shelly-chat API.

Runs on the NAS next to Postgres. It stores the document index and the
conversations, and answers vector searches - but never talks to a language
model. The browser does that with Ollama on the user's own machine.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__, db
from app.migrations import run_migrations
from app.routes import chat, conversations, index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Migrations before the first request is served.
    run_migrations()
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="shelly-chat", version=__version__, lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(index.router)
