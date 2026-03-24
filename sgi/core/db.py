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

# Carrega .env com caminho absoluto: <raiz do projeto>/.env
BASE_DIR = Path(__file__).resolve().parents[2]  # sai de sgi/core -> raiz
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True, encoding="utf-8")


def _get_database_url() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()

    if not dsn:
        raise RuntimeError(
            "DATABASE_URL não encontrada.\n"
            f"Arquivo .env esperado em: {ENV_PATH}\n\n"
            "Exemplo:\n"
            "DATABASE_URL=postgresql://postgres:SENHA@localhost:5432/sgi_impressoras\n"
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

    # remove caracteres invisíveis comuns
    dsn = dsn.replace("\ufeff", "").strip()

    return dsn


def conectar(*, dict_cursor: bool = True, connect_timeout: int = 10) -> PGConnection:
    dsn = _get_database_url()

    try:
        conn = psycopg2.connect(
            dsn,
            cursor_factory=RealDictCursor if dict_cursor else None,
            connect_timeout=connect_timeout,
        )
    except UnicodeDecodeError as e:
        # Mostra a URL real usada (repr) para descobrir a fonte do erro
        raise RuntimeError(
            "Falha ao conectar: a DATABASE_URL que chegou no psycopg2 contém bytes inválidos.\n\n"
            f"✅ ENV_PATH usado: {ENV_PATH}\n"
            f"✅ DATABASE_URL (repr): {repr(dsn)}\n\n"
            "Isso quase sempre acontece quando existe uma DATABASE_URL definida no Windows "
            "com caracteres especiais/encoding ruim, e ela está sobrescrevendo.\n"
            "Solução:\n"
            "1) Remova DATABASE_URL do Ambiente do Windows (Usuário/Sistema) OU\n"
            "2) Mantenha e deixe o código com override=True (já está).\n\n"
            f"Erro original: {e}"
        )

    # Ajustes de sessão
    with conn.cursor() as cur:
        cur.execute("SET client_encoding TO 'UTF8';")
        cur.execute("SET TIME ZONE 'UTC';")

    return conn


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
