from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import psycopg2
from psycopg2.extensions import connection as PGConnection
from psycopg2.extensions import cursor as PGCursor
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv

# ==========================================================
# 🔧 CARREGAMENTO DE AMBIENTE (LOCAL + PRODUÇÃO)
# ==========================================================

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

# Só carrega .env se existir (LOCAL)
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)


# ==========================================================
# 🔗 DATABASE URL (PROFISSIONAL - HÍBRIDO)
# ==========================================================
def _get_database_url() -> str:

    # 🔥 1. PRODUÇÃO (Railway / Variáveis de ambiente)
    dsn = os.environ.get("DATABASE_URL")

    if dsn:
        dsn = dsn.replace("\ufeff", "").strip()

        parsed = urlparse(dsn)
        if parsed.scheme not in ("postgresql", "postgres"):
            raise RuntimeError("DATABASE_URL inválida. Use postgresql://")

        if not parsed.hostname or not parsed.path or parsed.path == "/":
            raise RuntimeError("DATABASE_URL inválida: faltando host ou database.")

        return dsn

    # 🔥 2. LOCAL (.env)
    dbname = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")

    if dbname and user:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    # 🔥 3. ERRO CONTROLADO
    raise RuntimeError(
        "Nenhuma configuração de banco encontrada.\n"
        "Defina DATABASE_URL (produção) ou DB_* no .env (local)."
    )


# ==========================================================
# 🔌 CONEXÃO
# ==========================================================

def conectar(*, dict_cursor: bool = True, connect_timeout: int = 10) -> PGConnection:
    dsn = _get_database_url()

    try:
        conn = psycopg2.connect(
            dsn,
            cursor_factory=RealDictCursor if dict_cursor else None,
            connect_timeout=connect_timeout,
        )
    except UnicodeDecodeError as e:
        raise RuntimeError(
            "Falha ao conectar: DATABASE_URL contém caracteres inválidos.\n\n"
            f"ENV_PATH usado: {ENV_PATH}\n"
            f"DATABASE_URL (repr): {repr(dsn)}\n\n"
            f"Erro original: {e}"
        )

    # Ajustes de sessão
    with conn.cursor() as cur:
        cur.execute("SET client_encoding TO 'UTF8';")
        cur.execute("SET TIME ZONE 'UTC';")

    return conn


# ==========================================================
# 🔄 CONTEXTOS
# ==========================================================

@contextmanager
def get_conn(*, dict_cursor: bool = True) -> Iterable[PGConnection]:
    conn = conectar(dict_cursor=dict_cursor)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(*, dict_cursor: bool = True) -> Iterable[Tuple[PGConnection, PGCursor]]:
    conn = conectar(dict_cursor=dict_cursor)
    cur = conn.cursor()
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        finally:
            conn.close()


# ==========================================================
# 🧠 QUERY HELPER
# ==========================================================

def query(
    sql: str,
    params: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    *,
    fetchone: bool = False,
    fetchall: bool = False,
    dict_cursor: bool = True,
) -> Union[None, Dict[str, Any], List[Dict[str, Any]]]:
    with transaction(dict_cursor=dict_cursor) as (_conn, cur):
        cur.execute(sql, params)
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        return None