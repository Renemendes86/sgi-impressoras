# ==========================================================
# ROUTES PRINCIPAL DO SISTEMA SGI
# ==========================================================
# Arquivo refatorado, organizado e compatível com:
# - Multiempresa
# - Gestão de usuários
# - Permissões granulares
# - Admin com autonomia total
# ==========================================================

# ==========================================================
# IMPORTS FLASK
# ==========================================================
from flask import (
    render_template, request, redirect, session,
    flash, send_from_directory, abort, Response
)

# ==========================================================
# BANCO / AUTH
# ==========================================================
from sgi.core.db import conectar
from sgi.core.auth import autenticar

# ==========================================================
# PERMISSÕES (ÚNICA FONTE)
# ==========================================================
from sgi.core.permissions import (
    login_required,
    perfil_required,
    require_perm,
    require_empresa,
    require_multiempresa_view,
    _usuario_id,
    _empresa_id,
    _perfil,
    _get_empresas_disponiveis,
    _empresa_existe_ativa,
    _sync_empresa_nome,
    _can_switch_company
)

# ==========================================================
# UTILITÁRIOS
# ==========================================================
from datetime import datetime, date
import os, uuid, re

# ==========================================================
# CONFIG UPLOAD
# ==========================================================
UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "txt"}

# ==========================================================
# HELPERS INTERNOS
# ==========================================================
def _get(row, key, default=None):
    return row.get(key, default) if hasattr(row, "get") else default

def so_numeros(s):
    return re.sub(r"\D", "", s or "")

def _allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _file_ext(name):
    return name.rsplit(".", 1)[1].lower()

def _log(cur, acao, entidade, entidade_id=None, detalhes=""):
    try:
        cur.execute("""
            INSERT INTO logs_sistema (usuario, acao, entidade, entidade_id, detalhes)
            VALUES (%s,%s,%s,%s,%s)
        """, (
            session.get("usuario"),
            acao[:60], entidade[:60],
            entidade_id, detalhes
        ))
    except Exception:
        pass

# ==========================================================
# ROTAS
# ==========================================================
def configurar_rotas(app):

    # ======================================================
    # LOGIN / LOGOUT
    # ======================================================
    @app.route("/", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            usuario = request.form.get("usuario", "").strip()
            senha = request.form.get("senha", "").strip()

            user = autenticar(usuario, senha)
            if not user:
                flash("Usuário ou senha inválidos.", "danger")
                return render_template("login.html")

            if not user.get("ativo", True):
                flash("Usuário desativado.", "danger")
                return render_template("login.html")

            session.clear()
            session["usuario"] = user["usuario"]
            session["usuario_id"] = user["id"]
            session["perfil"] = user["perfil"]

        # --------------------------------------------------
        # Carrega TODAS as permissões do usuário
        # --------------------------------------------------

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT UPPER(p.codigo) AS codigo
            FROM usuarios_permissoes up
            JOIN permissoes p ON p.id = up.permissao_id
            WHERE up.usuario_id = %s
        """, (user["id"],))

        permissoes = [row["codigo"] for row in cur.fetchall()]

        cur.close()
        conn.close()

        # Salva lista principal
        session["permissoes"] = permissoes

        # Flags rápidas

        # SUPER_ADMIN tem acesso total
        is_super = "SUPER_ADMIN" in permissoes
        session["super_admin"] = is_super

        session["pode_multiempresa"] = is_super or "ACESSAR_TODAS_EMPRESAS" in permissoes
        session["is_admin"] = is_super or "ADMIN_USUARIOS" in permissoes
        session["pode_entrar_financeiro"] = is_super or "ENTRAR_FINANCEIRO" in permissoes
        session["pode_ver_financeiro"] = is_super or "VER_FINANCEIRO" in permissoes
        session["pode_ver_custo"] = is_super or "VER_VALOR_CUSTO" in permissoes
        session["pode_editar_custo"] = is_super or "EDITAR_VALOR_CUSTO" in permissoes
        session["pode_excluir"] = is_super or "EXCLUIR_REGISTROS" in permissoes

        return redirect("/selecionar-empresa")


    @app.route("/logout")
    def logout():
        session.clear()
        return redirect("/")


    # ======================================================
    # SELEÇÃO DE EMPRESA
    # ======================================================
    @app.route("/selecionar-empresa", methods=["GET", "POST"])
    @login_required
    def selecionar_empresa():
        conn = conectar()
        cur = conn.cursor()

        uid = _usuario_id()
        empresas = _get_empresas_disponiveis(cur, uid)

        if request.method == "POST":
            emp_id = request.form.get("empresa_id")
            if not emp_id:
                flash("Selecione uma empresa.", "warning")
                return redirect("/selecionar-empresa")

            emp_ids = [str(_get(e, "id")) for e in empresas]
            if emp_id not in emp_ids:
                flash("Acesso não permitido.", "danger")
                return redirect("/selecionar-empresa")

            cur.execute("SELECT id, nome, ativo FROM empresas WHERE id=%s", (emp_id,))
            emp = cur.fetchone()
            if not emp or not emp["ativo"]:
                flash("Empresa inválida.", "danger")
                return redirect("/selecionar-empresa")

            session["empresa_id"] = emp["id"]
            session["empresa_nome"] = emp["nome"]

            _log(cur, "TROCAR_EMPRESA", "empresas", emp["id"], emp["nome"])
            conn.commit()
            cur.close()
            conn.close()

            return redirect("/dashboard")

        cur.close()
        conn.close()
        return render_template("selecionar_empresa.html", empresas=empresas)


    # ======================================================
    # DASHBOARD
    # ======================================================
    @app.route("/dashboard")
    @login_required
    @require_empresa
    def dashboard():
        empresa_id = _empresa_id()

        conn = conectar()
        cur = conn.cursor()

        _sync_empresa_nome(cur, empresa_id)

        uid = _usuario_id()
        empresas = _get_empresas_disponiveis(cur, uid)
        can_switch = _can_switch_company(empresas)

        # =============================
        # CONTADORES
        # =============================
        cur.execute("SELECT COUNT(*) AS n FROM clientes WHERE empresa_id=%s", (empresa_id,))
        clientes = _get(cur.fetchone(), "n", 0)

        cur.execute("SELECT COUNT(*) AS n FROM impressoras WHERE empresa_id=%s", (empresa_id,))
        impressoras = _get(cur.fetchone(), "n", 0)

        cur.execute("SELECT COUNT(*) AS n FROM impressoras WHERE empresa_id=%s AND locada=TRUE", (empresa_id,))
        locadas = _get(cur.fetchone(), "n", 0)

        # =============================
        # PERMISSÕES
        # =============================
        perfil = (session.get("perfil") or "").upper()
        is_super_admin = perfil == "SUPER_ADMIN"
        is_admin = perfil == "ADMIN"

        # ADMIN e SUPER_ADMIN podem gerenciar usuários
        pode_gerenciar_usuarios = is_super_admin or is_admin

        # Permissão multiempresa já existente
        pode_ver_multiempresa = session.get("pode_multiempresa", False)

        # Permissão multiempresa já existente
        pode_ver_multiempresa = session.get("pode_multiempresa", False)

        cur.close()
        conn.close()

        return render_template(
            "dashboard.html",
            total_clientes=clientes,
            total_impressoras=impressoras,
            locadas=locadas,
            disponiveis=impressoras - locadas,
            empresa_nome=session.get("empresa_nome"),
            can_switch_company=can_switch,
            pode_ver_multiempresa=pode_ver_multiempresa,
            is_super_admin=is_super_admin,
            is_admin=is_admin,
            pode_gerenciar_usuarios=pode_gerenciar_usuarios
        )

    # ======================================================
    # MULTIEMPRESA (ADMIN / PERMISSÃO)
    # ======================================================
    @app.route("/multiempresa")
    @login_required
    @require_multiempresa_view
    def painel_multiempresa():
        conn = conectar()
        cur = conn.cursor()

        cur.execute("SELECT * FROM vw_empresas_resumo ORDER BY nome")
        resumo = cur.fetchall()

        cur.close()
        conn.close()

        return render_template("multiempresa.html", resumo=resumo)

    # ======================================================
    # IMPORTA ROTAS DE USUÁRIOS (SEPARADO)
    # ======================================================
    from sgi.web.routes_usuarios import configurar_rotas_usuarios
    configurar_rotas_usuarios(app)
