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
    load_dotenv(dotenv_path=ENV_PATH, override=True)


# ==========================================================
# 🔗 DATABASE URL (CORRIGIDO)
# ==========================================================
def _get_database_url() -> str:
    # 🔍 DEBUG (TEMPORÁRIO)
    print("DEBUG DATABASE_URL_EXTERNAL:", os.environ.get("DATABASE_URL_EXTERNAL"))
    print("DEBUG DATABASE_URL:", os.environ.get("DATABASE_URL"))

    # 🔥 USAR SOMENTE A EXTERNA
    dsn = os.environ.get("DATABASE_URL_EXTERNAL")

    if not dsn:
        raise RuntimeError(
            "DATABASE_URL_EXTERNAL não encontrada no ambiente.\n"
            "Configure no Railway com a URL externa do banco."
        )

    # validação básica
    parsed = urlparse(dsn)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("DATABASE_URL inválida: use postgresql:// (ou postgres://).")

    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise RuntimeError(
            "DATABASE_URL inválida: faltando host ou database.\n"
            "Exemplo: postgresql://postgres:SENHA@localhost:5432/sgi_impressoras"
        )

    # remove caracteres invisíveis
    dsn = dsn.replace("\ufeff", "").strip()

    return dsn



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