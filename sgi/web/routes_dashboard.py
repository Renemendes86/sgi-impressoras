# ==========================================================
# ROUTES - DASHBOARD
# ==========================================================

from flask import render_template, session, redirect, flash, request
from datetime import date
from sgi.core.financeiro import calcular_financeiro_mensal
from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    require_multiempresa_view,
    require_perm,
    tem_permissao,
    _get_empresas_disponiveis,
    _sync_empresa_nome,
    _can_switch_company,
    _is_super_admin   # <-- ADICIONE AQUI
)

# ==========================================================
# CONFIGURAÇÃO DAS ROTAS DO DASHBOARD
# ==========================================================

def configurar_rotas_dashboard(app):

    # ======================================================
    # DASHBOARD PRINCIPAL
    # ======================================================
    @app.route("/dashboard", methods=["GET"])
    @login_required
    @require_empresa
    def dashboard():


        empresa_id = session.get("empresa_id")
        usuario_id = session.get("usuario_id")
        perfil = (session.get("perfil") or "").upper()

        # --------------------------------------------------
        # CONTROLE DE PERFIL ADMIN
        # --------------------------------------------------
        is_super_admin = perfil == "SUPER_ADMIN"
        is_admin = perfil == "ADMIN"

        pode_gerenciar_usuarios = is_super_admin or is_admin

        # SUPER ADMIN e ADMIN podem gerenciar usuários
        pode_gerenciar_usuarios = is_super_admin or is_admin

        if not empresa_id or not usuario_id:
            flash("Sessão inválida. Selecione a empresa novamente.", "warning")
            return redirect("/selecionar-empresa")
        
        # ==========================================
        # MODO VISUALIZAR TODAS EMPRESAS
        # ==========================================
        visualizar_todas = request.args.get("todas") == "1"

        conn = conectar()
        cur = conn.cursor()

        # Permissão para ver multiempresa
        pode_ver_multiempresa = tem_permissao(cur, usuario_id, "ver_multiempresa")

        # Se tentou forçar via URL sem permissão
        if visualizar_todas and not pode_ver_multiempresa:
            visualizar_todas = False


        # --------------------------------------------------
        # SINCRONIZA NOME DA EMPRESA NA SESSÃO
        # --------------------------------------------------
        if not session.get("empresa_nome"):
            _sync_empresa_nome(cur, empresa_id)

        # --------------------------------------------------
        # PERMISSÃO PARA GERENCIAR USUÁRIOS
        # --------------------------------------------------
        perfil = (session.get("perfil") or "").upper()

        pode_gerenciar_usuarios = (
            perfil == "SUPER_ADMIN" or
            perfil == "ADMIN"
        )

        # --------------------------------------------------
        # EMPRESAS DISPONÍVEIS (TROCAR EMPRESA)
        # --------------------------------------------------
        empresas_disponiveis = _get_empresas_disponiveis(cur, usuario_id)
        pode_trocar_empresa = _can_switch_company(empresas_disponiveis)

        # --------------------------------------------------
        # CARDS OPERACIONAIS
        # --------------------------------------------------
        if visualizar_todas:
            cur.execute("""
                SELECT COUNT(*)
                FROM clientes
                WHERE empresa_id IN (
                    SELECT empresa_id
                    FROM usuarios_empresas
                    WHERE usuario_id = %s
                )
            """, (usuario_id,))
        else:
            cur.execute(
                "SELECT COUNT(*) FROM clientes WHERE empresa_id=%s",
                (empresa_id,)
            )

        total_clientes = int(cur.fetchone().get("total", 0))

        if visualizar_todas:
            cur.execute("""
                SELECT COUNT(*)
                FROM impressoras
                WHERE empresa_id IN (
                    SELECT empresa_id
                    FROM usuarios_empresas
                    WHERE usuario_id = %s
                )
            """, (usuario_id,))
        else:
            cur.execute(
                "SELECT COUNT(*) FROM clientes WHERE empresa_id=%s",
                (empresa_id,)
            )
        total_impressoras = int(cur.fetchone().get("total", 0))

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM impressoras
            WHERE empresa_id=%s AND locada=TRUE
        """, (empresa_id,))
        locadas = int(cur.fetchone().get("total", 0))

        disponiveis = max(0, total_impressoras - locadas)

        cur.execute(
            "SELECT COUNT(*) AS total FROM produtos WHERE empresa_id=%s",
            (empresa_id,)
        )
        total_produtos = int(cur.fetchone().get("total", 0))

        # --------------------------------------------------
        # OBJETO FINANCEIRO PADRÃO
        # --------------------------------------------------
        financeiro = {
            "receita_total": 0,
            "custo_total": 0,
            "lucro": 0,
            "margem": 0,
            "depreciacao_total": 0,
            "custo_operacional": 0
        }

       # --------------------------------------------------
        # CONTROLE DE PERMISSÕES FINANCEIRAS (PADRÃO OFICIAL)
        # --------------------------------------------------
        pode_ver_financeiro = tem_permissao(cur, usuario_id, "ver_financeiro")
        pode_ver_valor_aluguel = tem_permissao(cur, usuario_id, "ver_valor_aluguel")
        pode_ver_valor_custo = tem_permissao(cur, usuario_id, "ver_valor_custo")

        # --------------------------------------------------
        # CARDS FINANCEIROS
        # --------------------------------------------------
        # --------------------------------------------------
        # CARDS FINANCEIROS (PADRÃO OFICIAL ERP)
        # --------------------------------------------------

        hoje = date.today()

        financeiro = calcular_financeiro_mensal(
            empresa_id,
            hoje.month,
            hoje.year
        )

        total_aluguel = financeiro.get("receita_total", 0)
        total_compra = financeiro.get("investimento_total", 0)

        cur.close()
        conn.close()

        # 🔒 BLOQUEIO REAL NO BACKEND
        if not pode_ver_financeiro:
            financeiro = {
                "receita_total": None,
                "custo_total": None,
                "lucro": None,
                "margem": None,
                "depreciacao_total": None,
                "custo_operacional": None
            }

        if not pode_ver_valor_aluguel:
            total_aluguel = None
            total_compra = None

        return render_template(
            "dashboard.html",
            empresa_nome=session.get("empresa_nome"),
            total_clientes=total_clientes,
            total_impressoras=total_impressoras,
            visualizar_todas=visualizar_todas,
            pode_ver_multiempresa=pode_ver_multiempresa,
            locadas=locadas,
            disponiveis=disponiveis,
            total_produtos=total_produtos,
            pode_trocar_empresa=pode_trocar_empresa,
            

            # 🔐 Permissões
            pode_ver_financeiro=pode_ver_financeiro,
            pode_ver_valor_aluguel=pode_ver_valor_aluguel,
            pode_ver_valor_custo=pode_ver_valor_custo,
            pode_gerenciar_usuarios=pode_gerenciar_usuarios,

            # 🔐 Valores protegidos
            total_aluguel=total_aluguel,
            total_compra=total_compra,

            receita_total=financeiro["receita_total"],
            custo_total=financeiro["custo_total"],
            lucro=financeiro["lucro"],
            margem=financeiro["margem"],
            depreciacao_total=financeiro["depreciacao_total"],
            custo_operacional=financeiro["custo_operacional"],
        )

    # ======================================================
    # PAINEL MULTIEMPRESA
    # ======================================================
    @app.route("/multiempresa", methods=["GET"])
    @login_required
    def painel_multiempresa():

        filtro_empresa = request.args.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        # Empresas ativas
        usuario_id = session.get("usuario_id")

        # verifica permissão total
        cur.execute("""
            SELECT 1
            FROM usuarios_permissoes up
            JOIN permissoes p ON p.id = up.permissao_id
            WHERE up.usuario_id = %s
            AND UPPER(p.codigo) = 'ACESSAR_TODAS_EMPRESAS'
        """, (usuario_id,))
        acesso_total = cur.fetchone()

        perfil = (session.get("perfil") or "").upper()

        if acesso_total or perfil == "SUPER_ADMIN":
                    cur.execute("""
                SELECT id, nome
                FROM empresas
                WHERE ativo = TRUE
                ORDER BY nome
            """)
        else:
            cur.execute("""
                SELECT e.id, e.nome
                FROM empresas e
                JOIN usuarios_empresas ue ON ue.empresa_id = e.id
                WHERE ue.usuario_id = %s
                AND e.ativo = TRUE
                ORDER BY e.nome
            """, (usuario_id,))

        empresas = cur.fetchall()

        # ------------------------------------------
        # Resumo geral ou filtrado (FORMA SEGURA)
        # ------------------------------------------
        # ------------------------------------------
        # Verifica permissão financeira
        # ------------------------------------------
        usuario_id = session.get("usuario_id")

        pode_ver_financeiro = tem_permissao(
            cur,
            usuario_id,
            "VER_FINANCEIRO",
            session.get("empresa_id")
        )

        # ------------------------------------------
        # Resumo geral ou filtrado
        # ------------------------------------------
        if filtro_empresa and filtro_empresa.isdigit():
            cur.execute("""
                SELECT *
                FROM vw_empresas_resumo
                WHERE id = %s
                ORDER BY nome
            """, (int(filtro_empresa),))
        else:
            cur.execute("""
                SELECT *
                FROM vw_empresas_resumo
                ORDER BY nome
            """)

        resumo = cur.fetchall()

        # ------------------------------------------------
        # PROTEÇÃO FINANCEIRA (OPERADOR NÃO VÊ VALORES)
        # ------------------------------------------------
        if session.get("perfil") != "SUPER_ADMIN" and not pode_ver_financeiro:
            for r in resumo:
                if isinstance(r, dict):
                    r["total_aluguel"] = None

        cur.close()
        conn.close()

        return render_template(
            "multiempresa.html",
            empresas=empresas,
            resumo=resumo,
            filtro_empresa=filtro_empresa or "",
            pode_ver_financeiro=pode_ver_financeiro
        )
    # ======================================================
    # TROCAR EMPRESA ATIVA
    # ======================================================
    @app.route("/trocar-empresa/<int:empresa_id>")
    @login_required
    def trocar_empresa(empresa_id):

        usuario_id = session.get("usuario_id")
        perfil = (session.get("perfil") or "").upper()

        conn = conectar()
        cur = conn.cursor()

        # Verifica se admin OU tem permissão total
        cur.execute("""
            SELECT 1
            FROM usuarios_permissoes up
            JOIN permissoes p ON p.id = up.permissao_id
            WHERE up.usuario_id = %s
            AND UPPER(p.codigo) = 'ACESSAR_TODAS_EMPRESAS'
        """, (usuario_id,))
        acesso_total = cur.fetchone()

        permitido = False

        if _is_super_admin() or bool(acesso_total):
            permitido = True
        else:
            cur.execute("""
                SELECT 1
                FROM usuarios_empresas
                WHERE usuario_id=%s AND empresa_id=%s
            """, (usuario_id, empresa_id))
            permitido = cur.fetchone() is not None

        if not permitido:
            flash("Você não tem permissão para acessar esta empresa.", "danger")
            return redirect("/multiempresa")
        
        # Verifica se empresa está ativa
        cur.execute("""
            SELECT ativo
            FROM empresas
            WHERE id = %s
        """, (empresa_id,))

        empresa = cur.fetchone()

        if not empresa or not empresa.get("ativo"):
            flash("Empresa inativa.", "danger")
            return redirect("/dashboard")

        # Atualiza empresa ativa na sessão
        session["empresa_id"] = empresa_id

        # Atualiza nome da empresa
        _sync_empresa_nome(cur, empresa_id)

        cur.close()
        conn.close()

        return redirect("/dashboard")