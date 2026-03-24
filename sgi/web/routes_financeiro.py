from flask import render_template, session, redirect, flash, request
from datetime import date, datetime
from calendar import monthrange
from psycopg2.extras import RealDictCursor

from sgi.core.db import conectar
from sgi.core.permissions import login_required, require_empresa, require_perm
from sgi.core.financeiro import calcular_financeiro_mensal


def configurar_rotas_financeiro(app):

    @app.route("/financeiro", methods=["GET"])
    @login_required
    @require_empresa
    @require_perm("entrar_no_financeiro")
    def financeiro():

        empresa_id = session.get("empresa_id")

        if not empresa_id:
            flash("Selecione uma empresa.", "warning")
            return redirect("/selecionar-empresa")

        hoje = date.today()

        # ==========================================================
        # 🔎 CAPTURA DOS FILTROS
        # ==========================================================
        periodo = request.args.get("periodo", "mes_atual")
        data_inicio = request.args.get("data_inicio")
        data_fim = request.args.get("data_fim")

        # ==========================================================
        # 📅 DEFINIÇÃO DO PERÍODO
        # ==========================================================
        if periodo == "mes_atual":
            inicio = hoje.replace(day=1)
            fim = hoje

        elif periodo == "mes_anterior":
            mes = hoje.month - 1 or 12
            ano = hoje.year if hoje.month > 1 else hoje.year - 1

            inicio = date(ano, mes, 1)
            fim = date(ano, mes, monthrange(ano, mes)[1])

        elif periodo == "personalizado" and data_inicio and data_fim:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            fim = datetime.strptime(data_fim, "%Y-%m-%d").date()

        else:
            inicio = date(2000, 1, 1)
            fim = hoje

        # ==========================================================
        # 📊 FINANCEIRO RESUMIDO (MANTIDO ORIGINAL)
        # ==========================================================
        financeiro = calcular_financeiro_mensal(
            empresa_id,
            hoje.month,
            hoje.year
        )

        conn = conectar()
        cur = conn.cursor(cursor_factory=RealDictCursor)

       # ==========================================================
        # 🏆 RANKING ANTIGO (MANTIDO)
        # ==========================================================
        cur.execute("""
        SELECT
            m.nome AS municipio,

            COALESCE(SUM(i.valor_aluguel),0) -
            COALESCE(SUM(ci.quantidade * ci.valor_unitario),0) AS lucro

        FROM municipios m

        LEFT JOIN clientes c
            ON c.municipio_id = m.id
            AND c.empresa_id = %s

        LEFT JOIN impressoras i
            ON i.cliente_id = c.id
            AND i.locada = TRUE

        LEFT JOIN custos_impressora ci
            ON ci.cliente_id = c.id

        GROUP BY m.nome
        ORDER BY lucro DESC
        LIMIT 10
        """, (empresa_id,))

        ranking_secretarias = cur.fetchall()


        # ==========================================================
        # 🧠 RELATÓRIO COMPLETO POR MUNICÍPIO (CORRIGIDO DEFINITIVO)
        # ==========================================================
        cur.execute("""
        SELECT
            m.nome AS municipio,

            -- Receita
            COALESCE(SUM(i.valor_aluguel), 0) AS receita_total,

            -- Custo insumos (correto por período)
            COALESCE(SUM(ci.custo_total), 0) AS custo_insumos,

            -- 🚗 Custo viagens (SEM DUPLICAÇÃO)
            COALESCE((
                SELECT SUM(v2.custo_total)
                FROM viagens v2
                WHERE v2.municipio_id = m.id
                AND v2.empresa_id = %s
                AND v2.data_viagem BETWEEN %s AND %s
            ), 0) AS custo_viagem,

            -- Custo total
            COALESCE(SUM(ci.custo_total), 0)
            +
            COALESCE((
                SELECT SUM(v2.custo_total)
                FROM viagens v2
                WHERE v2.municipio_id = m.id
                AND v2.empresa_id = %s
                AND v2.data_viagem BETWEEN %s AND %s
            ), 0) AS custo_total,

            -- Lucro
            COALESCE(SUM(i.valor_aluguel), 0)
            -
            (
                COALESCE(SUM(ci.custo_total), 0)
                +
                COALESCE((
                    SELECT SUM(v2.custo_total)
                    FROM viagens v2
                    WHERE v2.municipio_id = m.id
                    AND v2.empresa_id = %s
                    AND v2.data_viagem BETWEEN %s AND %s
                ), 0)
            ) AS lucro,

            -- Margem
            CASE
                WHEN COALESCE(SUM(i.valor_aluguel), 0) > 0 THEN
                    (
                        (
                            COALESCE(SUM(i.valor_aluguel), 0)
                            -
                            (
                                COALESCE(SUM(ci.custo_total), 0)
                                +
                                COALESCE((
                                    SELECT SUM(v2.custo_total)
                                    FROM viagens v2
                                    WHERE v2.municipio_id = m.id
                                    AND v2.empresa_id = %s
                                    AND v2.data_viagem BETWEEN %s AND %s
                                ), 0)
                            )
                        ) / COALESCE(SUM(i.valor_aluguel), 0)
                    ) * 100
                ELSE 0
            END AS margem

        FROM municipios m

        LEFT JOIN clientes c
            ON c.municipio_id = m.id
            AND c.empresa_id = %s

        LEFT JOIN impressoras i
            ON i.cliente_id = c.id
            AND i.locada = TRUE

        -- CUSTOS AGRUPADOS
        LEFT JOIN (
            SELECT
                cliente_id,
                SUM(quantidade * valor_unitario) AS custo_total
            FROM custos_impressora
            WHERE data_custo BETWEEN %s AND %s
            GROUP BY cliente_id
        ) ci ON ci.cliente_id = c.id

        GROUP BY m.id, m.nome
        ORDER BY lucro DESC
        """, (
            # viagem
            empresa_id, inicio, fim,
            empresa_id, inicio, fim,
            empresa_id, inicio, fim,
            empresa_id, inicio, fim,

            # base
            empresa_id,
            inicio, fim
        ))

        municipios_financeiro = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "financeiro.html",
            financeiro=financeiro,
            ranking_secretarias=ranking_secretarias,
            municipios_financeiro=municipios_financeiro,
            inicio=inicio,
            fim=fim,
            periodo=periodo
        )