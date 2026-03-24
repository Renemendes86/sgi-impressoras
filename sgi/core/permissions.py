from functools import wraps
from flask import session, redirect, flash
from sgi.core.db import conectar


# ==========================================================
# PERMISSÕES CRÍTICAS DO SISTEMA (NÃO PODEM SER EXCLUÍDAS)
# ==========================================================

PERMISSOES_PROTEGIDAS = [
    "ADMIN_USUARIOS",
    "ACESSAR_TODAS_EMPRESAS"
]


# ==========================================================
# HELPERS INTERNOS (SESSÃO)
# ==========================================================

def _usuario_id():
    """Retorna o ID do usuário logado ou None."""
    uid = session.get("usuario_id")
    return int(uid) if uid else None


def _perfil():
    """Retorna o perfil do usuário em MAIÚSCULO."""
    return (session.get("perfil") or "").upper().strip()


def _empresa_id():
    """Retorna o empresa_id atual da sessão ou None."""
    try:
        return int(session.get("empresa_id"))
    except Exception:
        return None


def _pode_multiempresa():
    """Permissão explícita para visão multiempresa (não-admin)."""
    return bool(session.get("pode_multiempresa", False))


def _is_super_admin():
    """
    Super admin é definido pelo PERFIL, não por permissão.
    """
    return _perfil() == "SUPER_ADMIN"


# ==========================================================
# FUNÇÃO CENTRAL DE PERMISSÃO
# ==========================================================

def tem_permissao(cur, usuario_id: int, codigo_perm: str, empresa_id: int = None) -> bool:

    # SUPER ADMIN sempre tem acesso
    if _is_super_admin():
        return True

    if not cur:
        return False

    try:
        usuario_id = int(usuario_id)
    except Exception:
        return False

    codigo_perm = (codigo_perm or "").upper().strip()

    # ------------------------------------------------------
    # 1️⃣ PERMISSÃO GLOBAL
    # ------------------------------------------------------
    cur.execute("""
        SELECT 1
        FROM usuarios_permissoes up
        JOIN permissoes p ON p.id = up.permissao_id
        WHERE up.usuario_id = %s
        AND UPPER(p.codigo) = %s
    """, (usuario_id, codigo_perm))

    if cur.fetchone():
        return True

    # ------------------------------------------------------
    # 2️⃣ PERMISSÃO POR EMPRESA
    # ------------------------------------------------------
    if empresa_id:

        cur.execute("""
            SELECT 1
            FROM usuarios_empresas_permissoes uep
            JOIN permissoes p ON p.id = uep.permissao_id
            WHERE uep.usuario_id = %s
            AND uep.empresa_id = %s
            AND UPPER(p.codigo) = %s
        """, (usuario_id, empresa_id, codigo_perm))

        if cur.fetchone():
            return True

    return False

# ==========================================================
# LOGIN OBRIGATÓRIO
# ==========================================================

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect("/")
        return view(*args, **kwargs)
    return wrapper


# ==========================================================
# PERFIL (ADMIN, OPERADOR, CONSULTA)
# ==========================================================

def perfil_required(*perfis):
    perfis = [p.upper() for p in perfis]

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "usuario_id" not in session:
                return redirect("/")

            if _perfil() not in perfis:
                flash("Ação não permitida para seu perfil.", "warning")
                return redirect("/dashboard")

            return view(*args, **kwargs)
        return wrapper
    return decorator

# ==========================================================
# VERIFICA ACESSO A EMPRESA
# ==========================================================

def pode_acessar_empresa(cur, usuario_id: int, empresa_id: int) -> bool:

    # SUPER ADMIN sempre pode
    if _is_super_admin():
        return True

    # Verifica permissão global
    cur.execute("""
        SELECT 1
        FROM usuarios_permissoes up
        JOIN permissoes p ON p.id = up.permissao_id
        WHERE up.usuario_id = %s
        AND UPPER(p.codigo) = 'ACESSAR_TODAS_EMPRESAS'
    """, (usuario_id,))

    if cur.fetchone():
        return True

    # Verifica vínculo com empresa
    cur.execute("""
        SELECT 1
        FROM usuarios_empresas
        WHERE usuario_id = %s
        AND empresa_id = %s
    """, (usuario_id, empresa_id))

    return cur.fetchone() is not None

# ==========================================================
# EMPRESA SELECIONADA (MULTIEMPRESA)
# ==========================================================

def require_empresa(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        empresa_id = session.get("empresa_id")
        usuario_id = session.get("usuario_id")

        if not empresa_id:
            flash("Selecione uma empresa para continuar.", "warning")
            return redirect("/selecionar-empresa")

        conn = conectar()
        cur = conn.cursor()

        # 🔒 verifica se empresa está ativa
        cur.execute("""
            SELECT 1
            FROM empresas
            WHERE id = %s AND ativo = TRUE
        """, (empresa_id,))
        ativa = cur.fetchone()

        if not ativa:
            cur.close()
            conn.close()
            session.pop("empresa_id", None)
            session.pop("empresa_nome", None)
            flash("Empresa inválida ou inativa.", "danger")
            return redirect("/selecionar-empresa")

        
        # 🔒 ADMIN sempre pode acessar qualquer empresa
        if _is_super_admin():
            cur.close()
            conn.close()
            return view(*args, **kwargs)

        # 🔒 verifica se usuário tem permissão explícita
        cur.execute("""
            SELECT 1
            FROM usuarios_permissoes up
            JOIN permissoes p ON p.id = up.permissao_id
            WHERE up.usuario_id = %s
            AND UPPER(p.codigo) = 'ACESSAR_TODAS_EMPRESAS'
        """, (usuario_id,))
        acesso_total = cur.fetchone()

        if not acesso_total:
            # verifica se empresa está vinculada ao usuário
            cur.execute("""
                SELECT 1
                FROM usuarios_empresas
                WHERE usuario_id = %s
                AND empresa_id = %s
            """, (usuario_id, empresa_id))

            vinculo = cur.fetchone()

            if not vinculo:
                cur.close()
                conn.close()
                session.pop("empresa_id", None)
                flash("Você não tem acesso a esta empresa.", "danger")
                return redirect("/selecionar-empresa")

        cur.close()
        conn.close()

        return view(*args, **kwargs)

    return wrapper


# ==========================================================
# VISÃO MULTIEMPRESA (ADMIN ou PERMISSÃO EXPLÍCITA)
# ==========================================================

def require_multiempresa_view(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if _is_super_admin():
            return view(*args, **kwargs)

        uid = _usuario_id()
        if not uid:
            return redirect("/")

        conn = conectar()
        cur = conn.cursor()

        permitido = tem_permissao(cur, uid, "ACESSAR_TODAS_EMPRESAS")

        cur.close()
        conn.close()

        if permitido:
            return view(*args, **kwargs)

        flash("Você não possui permissão para acessar a visão multiempresa.", "warning")
        return redirect("/dashboard")

    return wrapper


# ==========================================================
# PERMISSÃO GRANULAR (BANCO DE DADOS)
# ==========================================================

def require_perm(codigo_perm):
    """
    Permissão baseada nas tabelas:
      - permissoes
      - usuarios_permissoes

    SUPER_ADMIN sempre tem acesso total.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):

            # SUPER_ADMIN nunca é bloqueado
            if _is_super_admin():
                return view(*args, **kwargs)

            uid = _usuario_id()
            if not uid:
                flash("Sessão inválida.", "danger")
                return redirect("/")

            conn = conectar()
            cur = conn.cursor()

            permitido = tem_permissao(cur, uid, codigo_perm)

            cur.close()
            conn.close()

            if not permitido:
                flash("Você não possui permissão para executar esta ação.", "warning")
                return redirect("/dashboard")

            return view(*args, **kwargs)
        return wrapper
    return decorator


# ==========================================================
# HELPERS MULTIEMPRESA (OBRIGATÓRIOS)
# ==========================================================

def _get_empresas_disponiveis(cur, usuario_id: int):
    cur.execute("""
        SELECT perfil
        FROM usuarios
        WHERE id = %s
    """, (usuario_id,))
    u = cur.fetchone()
    if not u:
        return []

    if isinstance(u, dict):
        perfil = (u.get("perfil") or "").upper()
    else:
        perfil = (u[0] or "").upper()

    # Verifica permissão explícita multiempresa
    cur.execute("""
        SELECT 1
        FROM usuarios_permissoes up
        JOIN permissoes p ON p.id = up.permissao_id
        WHERE up.usuario_id = %s
          AND UPPER(p.codigo) = 'ACESSAR_TODAS_EMPRESAS'
    """, (usuario_id,))
    tem_multi = cur.fetchone()

    # SUPER_ADMIN ou permissão explícita → TODAS EMPRESAS
    if perfil == "SUPER_ADMIN" or tem_multi:
        cur.execute("""
            SELECT id, nome
            FROM empresas
            WHERE ativo = TRUE
            ORDER BY nome
        """)
        return cur.fetchall()

    # Usuário comum → apenas vinculadas
    cur.execute("""
        SELECT e.id, e.nome
        FROM usuarios_empresas ue
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE ue.usuario_id = %s
          AND e.ativo = TRUE
        ORDER BY e.nome
    """, (usuario_id,))

    return cur.fetchall()


def _empresa_existe_ativa(cur, empresa_id: int) -> bool:
    cur.execute("""
        SELECT 1
        FROM empresas
        WHERE id = %s AND ativo = TRUE
    """, (empresa_id,))
    return bool(cur.fetchone())


def _sync_empresa_nome(cur, empresa_id: int):
    cur.execute("""
        SELECT nome
        FROM empresas
        WHERE id = %s
    """, (empresa_id,))
    e = cur.fetchone()
    if e:
        session["empresa_nome"] = e["nome"] if isinstance(e, dict) else e[0]


def _can_switch_company(empresas_lista) -> bool:
    """Mostra botão 'Trocar Empresa' se houver mais de uma empresa disponível."""
    try:
        return len(empresas_lista or []) > 1
    except Exception:
        return False


# ==========================================================
# PERMISSÕES FINANCEIRAS
# ==========================================================

def pode_ver_financeiro(cur, usuario_id: int) -> bool:
    return tem_permissao(cur, usuario_id, "VER_FINANCEIRO")


def pode_excluir(cur, usuario_id: int) -> bool:
    return tem_permissao(cur, usuario_id, "EXCLUIR_REGISTROS")
