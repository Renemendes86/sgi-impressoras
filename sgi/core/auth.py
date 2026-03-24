from __future__ import annotations

from typing import Any, Dict, Optional

import bcrypt

from sgi.core.db import conectar


# ------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------

def _as_dict(row) -> Dict[str, Any]:
    """
    Garante acesso consistente aos campos, mesmo se vier dict (RealDictCursor)
    ou tupla (cursor normal).
    """
    if row is None:
        return {}
    if hasattr(row, "get"):
        return dict(row)
    # fallback: tupla -> impossível mapear sem cursor.description,
    # então retornamos dict vazio e tratamos pelo acesso posicional.
    return {}


def _get_col(row, idx: int, key: str, default=None):
    """
    Lê coluna por chave (dict) ou por índice (tupla).
    """
    if row is None:
        return default
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[idx]
    except Exception:
        return default


def _column_exists(cur, table: str, column: str, schema: str = "public") -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s AND column_name=%s
        """,
        (schema, table, column),
    )
    return cur.fetchone() is not None


def _is_bcrypt_hash(value: str) -> bool:
    """
    Detecta hashes bcrypt típicos.
    """
    if not value:
        return False
    v = value.strip()
    return v.startswith("$2a$") or v.startswith("$2b$") or v.startswith("$2y$")


def _check_password_bcrypt(password: str, hash_db: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_db.encode("utf-8"))
    except Exception:
        return False


def _check_password_pgcrypto(cur, password: str, hash_db: str) -> bool:
    """
    Valida senha quando o hash foi gerado no PostgreSQL (pgcrypto):
        crypt('senha', gen_salt('bf', 12))

    Validação correta:
        crypt(%s, hash_db) = hash_db
    """
    try:
        cur.execute("SELECT crypt(%s, %s) = %s AS ok", (password, hash_db, hash_db))
        r = cur.fetchone()
        if not r:
            return False
        return bool(_get_col(r, 0, "ok", False))
    except Exception:
        return False


def _upgrade_hash_to_bcrypt(cur, user_id: int, password: str) -> None:
    """
    Atualiza o hash do usuário para bcrypt do Python.
    Não dá commit aqui: quem chama decide (melhor prática).
    """
    new_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    cur.execute("UPDATE public.usuarios SET senha_hash=%s WHERE id=%s", (new_hash, user_id))


# ------------------------------------------------------------
# Função principal
# ------------------------------------------------------------

def autenticar(usuario: str, senha: str) -> Optional[Dict[str, Any]]:
    """
    Autentica usuário no SGI.

    Compatível com:
      - bcrypt do Python ($2a$/$2b$/$2y$)
      - pgcrypto do PostgreSQL (crypt)

    Também tolera banco antigo sem colunas:
      - ativo
      - empresa_id
    """
    usuario = (usuario or "").strip()
    senha = (senha or "").strip()

    if not usuario or not senha:
        return None

    conn = conectar(dict_cursor=True)
    cur = conn.cursor()

    try:
        # Descobre quais colunas existem (para não quebrar em banco antigo)
        has_ativo = _column_exists(cur, "usuarios", "ativo")
        has_empresa_id = _column_exists(cur, "usuarios", "empresa_id")
        has_forcar_troca = _column_exists(cur, "usuarios", "forcar_troca_senha")

        # Monta SELECT seguro
        select_cols = ["id", "usuario", "senha_hash", "perfil"]
        if has_ativo:
            select_cols.append("ativo")
        else:
            select_cols.append("TRUE AS ativo")  # default seguro
        if has_empresa_id:
            select_cols.append("empresa_id")
        else:
            select_cols.append("NULL::int AS empresa_id")

        if has_forcar_troca:
            select_cols.append("forcar_troca_senha")
        else:
            select_cols.append("FALSE AS forcar_troca_senha")

        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM public.usuarios
            WHERE usuario = %s
            LIMIT 1
        """

        cur.execute(sql, (usuario,))
        u = cur.fetchone()
        if not u:
            return None

        user_id = int(_get_col(u, 0, "id"))
        user_usuario = str(_get_col(u, 1, "usuario") or "")
        senha_hash = str(_get_col(u, 2, "senha_hash") or "")
        perfil = str(_get_col(u, 3, "perfil") or "")
        ativo = bool(_get_col(u, 4, "ativo", True))
        empresa_id = _get_col(u, 5, "empresa_id", None)
        forcar_troca_senha = bool(_get_col(u, 6, "forcar_troca_senha", False))

        if not ativo:
            return None

        # 1) Se for bcrypt python
        if _is_bcrypt_hash(senha_hash):
            if not _check_password_bcrypt(senha, senha_hash):
                return None

        # 2) Caso contrário, tenta pgcrypto
        else:
            ok = _check_password_pgcrypto(cur, senha, senha_hash)
            if not ok:
                return None

            # Se autenticou via pgcrypto, upgrade para bcrypt python (melhor prática)
            try:
                _upgrade_hash_to_bcrypt(cur, user_id, senha)
                conn.commit()
            except Exception:
                conn.rollback()
                # Não impede login se falhar o upgrade

        # Retorna dados padronizados
        return {
            "id": user_id,
            "usuario": user_usuario,
            "perfil": perfil,
            "ativo": ativo,
            "empresa_id": int(empresa_id) if empresa_id is not None else None,
            "forcar_troca_senha": forcar_troca_senha,
        }

    finally:
        try:
            cur.close()
        finally:
            conn.close()
