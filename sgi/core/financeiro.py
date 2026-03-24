from datetime import date
from sgi.core.db import conectar

def calcular_financeiro_mensal(empresa_id, mes, ano):

    conn = conectar()
    cur = conn.cursor()

    # ============================
    # RECEITA DO MÊS
    # ============================
    cur.execute("""
        SELECT COALESCE(SUM(valor_aluguel),0) AS total
        FROM impressoras
        WHERE empresa_id=%s
          AND locada=TRUE
    """, (empresa_id,))
    
    row = cur.fetchone()
    receita_total = float(row["total"] or 0) if row else 0

    # ============================
    # CUSTOS OPERACIONAIS DO MÊS
    # ============================

    # custos lançados manualmente
    cur.execute("""
        SELECT COALESCE(SUM(valor),0) AS total
        FROM lancamentos
        WHERE empresa_id=%s
        AND tipo='CUSTO'
        AND EXTRACT(MONTH FROM data)= %s
        AND EXTRACT(YEAR FROM data)= %s
    """, (empresa_id, mes, ano))

    row = cur.fetchone()
    custo_lancamentos = float(row["total"] or 0) if row else 0


    # custos vindos das locações
    cur.execute("""
        SELECT COALESCE(SUM(ci.quantidade * ci.valor_unitario),0) AS total
        FROM custos_impressora ci
        JOIN clientes c ON c.id = ci.cliente_id
        WHERE c.empresa_id = %s
        AND EXTRACT(MONTH FROM ci.data_custo)= %s
        AND EXTRACT(YEAR FROM ci.data_custo)= %s
    """, (empresa_id, mes, ano))

    row = cur.fetchone()
    custo_locacoes = float(row["total"] or 0) if row else 0


    # custo operacional total
    custo_operacional = custo_lancamentos + custo_locacoes

    # ============================
    # DEPRECIAÇÃO AUTOMÁTICA
    # ============================
    depreciacao_total = 0

    cur.execute("""
        SELECT id, valor_compra, data_compra, vida_util_meses
        FROM impressoras
        WHERE empresa_id=%s
          AND valor_compra IS NOT NULL
          AND data_compra IS NOT NULL
          AND vida_util_meses IS NOT NULL
          AND ativo = TRUE
    """, (empresa_id,))

    impressoras = cur.fetchall()
    hoje = date.today()

    for imp in impressoras:
        valor_compra = imp["valor_compra"]
        data_compra = imp["data_compra"]
        vida_util = imp["vida_util_meses"]

        if not valor_compra or not vida_util:
            continue

        meses_uso = (hoje.year - data_compra.year) * 12 + (hoje.month - data_compra.month)

        if meses_uso < vida_util:
            depreciacao_mensal = valor_compra / vida_util
            depreciacao_total += depreciacao_mensal

    # ============================
    # CUSTO TOTAL
    # ============================
    custo_total = custo_operacional + depreciacao_total

    # ============================
    # LUCRO
    # ============================
    lucro = receita_total - custo_total

    # ============================
    # MARGEM
    # ============================
    if receita_total > 0:
        margem = (lucro / receita_total) * 100
    else:
        margem = 0

    cur.close()
    conn.close()

    return {
        "receita_total": receita_total,
        "custo_operacional": custo_operacional,
        "depreciacao_total": depreciacao_total,
        "custo_total": custo_total,
        "lucro": lucro,
        "margem": margem
    }