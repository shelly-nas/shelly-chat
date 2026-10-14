"""Postgres connection pool (psycopg 3)."""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

_pool: ConnectionPool | None = None


def conninfo() -> str:
    return psycopg.conninfo.make_conninfo(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        dbname=config.DB_NAME,
    )


def open_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A pooled connection; commits on success, rolls back on an exception."""
    if _pool is None:
        open_pool()
    assert _pool is not None
    with _pool.connection() as conn:
        yield conn


def vector_literal(values: list[float]) -> str:
    """Text form of a pgvector value, to be cast with ::vector."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"
