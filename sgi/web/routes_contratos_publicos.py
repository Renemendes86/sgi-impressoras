# ==========================================================
# ROUTES – CONTRATOS PÚBLICOS (PAINEL EXECUTIVO)
# ==========================================================

from flask import render_template, session
from psycopg2.extras import RealDictCursor
from sgi.core.db import conectar
from sgi.core.permissions import login_required, require_empresa, tem_permissao


def configurar_rotas_contratos_publicos(app):

    @app.route("/contratos-publicos")
    @login_required
    @require_empresa
    def contratos_publicos():

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ======================================================
        # PERMISSÕES
        # ======================================================
        usuario_id = session.get("usuario_id")

        pode_ver_financeiro = tem_permissao(cur, usuario_id, "ver_financeiro")

        # SUPER ADMIN sempre pode
        if session.get("perfil") == "SUPER_ADMIN":
            pode_ver_financeiro = True

        # ======================================================
        # QUERY PROFISSIONAL (ALINHADA COM LOCAÇÕES)
        # ======================================================

        cur.execute("""
        WITH locacoes AS (
            SELECT
                c.id AS cliente_id,
                c.nome AS secretaria,
                m.id AS municipio_id,
                m.nome AS municipio,

                COUNT(i.id) AS impressoras,
                SUM(i.valor_aluguel) AS total_aluguel

            FROM clientes c
            JOIN municipios m ON m.id = c.municipio_id

            LEFT JOIN impressoras i 
                ON i.cliente_id = c.id
                AND i.locada = TRUE
                AND i.empresa_id = %s

            WHERE c.empresa_id = %s

            GROUP BY c.id, c.nome, m.id, m.nome
        ),

        custos_impressao AS (
            SELECT
                cliente_id,
                SUM(quantidade * valor_unitario) AS custo_total
            FROM custos_impressora
            GROUP BY cliente_id
        ),

        custos_viagem AS (
            SELECT
                municipio_id,
                SUM(custo_total) AS custo_viagem
            FROM viagens
            WHERE empresa_id = %s
            GROUP BY municipio_id
        )

        SELECT
            l.municipio,
            l.municipio_id,
            l.cliente_id,
            l.secretaria,

            COALESCE(l.impressoras,0) AS impressoras,
            COALESCE(l.total_aluguel,0) AS total_aluguel,

            -- 🔹 custo da secretaria (SOMENTE impressora)
            COALESCE(ci.custo_total,0) AS custo_mes,

            -- 🔹 custo da viagem (SOMENTE município)
            COALESCE(cv.custo_viagem,0) AS custo_viagem

        FROM locacoes l

        LEFT JOIN custos_impressao ci 
            ON ci.cliente_id = l.cliente_id

        LEFT JOIN custos_viagem cv
            ON cv.municipio_id = l.municipio_id

        WHERE l.impressoras > 0

        ORDER BY l.municipio, l.secretaria
        """, (empresa_id, empresa_id, empresa_id))
       
        dados = cur.fetchall()

        # ======================================================
        # AGRUPAMENTO PROFISSIONAL (SEM DUPLICAÇÃO)
        # ======================================================
        municipios = {}

        for r in dados:

            municipio = r["municipio"]
            cliente_id = r["cliente_id"]

            aluguel = float(r["total_aluguel"] or 0)
            custo = float(r["custo_mes"] or 0)  # custo da secretaria
            custo_viagem = float(r["custo_viagem"] or 0)  # custo do município

            # cria estrutura do município
            if municipio not in municipios:
                municipios[municipio] = {
                    "clientes_map": {},
                    "custo_viagem_total": 0  # 🔥 controle separado
                }

            m = municipios[municipio]

            # cria secretaria se não existir
            if cliente_id not in m["clientes_map"]:
                m["clientes_map"][cliente_id] = {
                    "secretaria": r["secretaria"],
                    "impressoras": 0,
                    "total_aluguel": 0,
                    "total_custo": 0  # 🔹 só custo da impressora
                }

            # ================================
            # 🔹 ACUMULA SECRETARIA
            # ================================
            m["clientes_map"][cliente_id]["impressoras"] += r["impressoras"]
            m["clientes_map"][cliente_id]["total_aluguel"] += aluguel
            m["clientes_map"][cliente_id]["total_custo"] += custo

            # ================================
            # 🔥 ACUMULA VIAGEM (SÓ NO MUNICÍPIO)
            # ================================
            m["custo_viagem_total"] += custo_viagem

        # ======================================================
        # CONSOLIDAÇÃO FINAL (POR MUNICÍPIO)
        # ======================================================
        for m in municipios.values():

            total_impressoras = 0
            total_aluguel = 0
            total_custo_secretarias = 0  # 🔹 custo só das secretarias

            m["secretarias"] = []

            for cliente_id, c in m["clientes_map"].items():

                aluguel = float(c["total_aluguel"] or 0)
                custo = float(c["total_custo"] or 0)

                lucro = aluguel - custo
                margem = (lucro / aluguel * 100) if aluguel > 0 else 0

                m["secretarias"].append({
                    "secretaria": c["secretaria"],
                    "impressoras": c["impressoras"],

                    # 🔒 CONTROLE FINANCEIRO
                    "total_aluguel": aluguel if pode_ver_financeiro else None,
                    "custo_mes": custo if pode_ver_financeiro else None,
                    "lucro": lucro if pode_ver_financeiro else None,
                    "margem": margem if pode_ver_financeiro else None
                })

                total_impressoras += c["impressoras"]
                total_aluguel += aluguel
                total_custo_secretarias += custo

            # ==================================================
            # 🔥 CUSTO DE VIAGEM (NÍVEL MUNICÍPIO)
            # ==================================================
            custo_viagem = float(m.get("custo_viagem_total", 0))

            # ==================================================
            # 🔥 TOTAL FINAL DO MUNICÍPIO (CORRETO)
            # ==================================================
            total_custo = total_custo_secretarias + custo_viagem

            m["total_secretarias"] = len(m["clientes_map"])
            m["total_impressoras"] = total_impressoras

            # 🔒 FINANCEIRO MUNICÍPIO
            m["total_aluguel"] = total_aluguel if pode_ver_financeiro else None
            m["total_custo"] = total_custo if pode_ver_financeiro else None
            m["custo_viagem"] = custo_viagem if pode_ver_financeiro else None  # 🔥 NOVO

            lucro = total_aluguel - total_custo

            m["lucro"] = lucro if pode_ver_financeiro else None
            m["margem"] = (
                (lucro / total_aluguel * 100)
                if total_aluguel > 0 else 0
            ) if pode_ver_financeiro else None

            # limpeza profissional
            del m["clientes_map"]

        # ======================================================
        # TOTAL GERAL DO SISTEMA
        # ======================================================
        total_secretarias = 0
        total_impressoras = 0
        total_aluguel = 0
        total_custo = 0

        for m in municipios.values():

            total_secretarias += m["total_secretarias"]
            total_impressoras += m["total_impressoras"]

            if pode_ver_financeiro:
                total_aluguel += (m["total_aluguel"] or 0)
                total_custo += (m["total_custo"] or 0)

        lucro_total = total_aluguel - total_custo

        margem_total = (
            (lucro_total / total_aluguel * 100)
            if total_aluguel > 0 else 0
        ) if pode_ver_financeiro else None

        cur.close()
        conn.close()

        return render_template(
            "contratos_publicos.html",
            municipios=municipios,
            total_secretarias=total_secretarias,
            total_impressoras=total_impressoras,
            total_aluguel=total_aluguel if pode_ver_financeiro else None,
            total_custo=total_custo if pode_ver_financeiro else None,
            lucro_total=lucro_total if pode_ver_financeiro else None,
            margem_total=margem_total if pode_ver_financeiro else None,
            pode_ver_financeiro=pode_ver_financeiro
        )