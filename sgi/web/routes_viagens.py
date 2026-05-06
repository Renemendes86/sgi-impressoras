# ==========================================================
# ROUTES – VIAGENS
# ==========================================================

from flask import (
    render_template,
    request,
    redirect,
    flash,
    session
)

from datetime import date, timedelta

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required
)


# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_viagens(app):

    # ======================================================
    # LISTAR VIAGENS (COM FILTRO PROFISSIONAL)
    # ======================================================
    @app.route("/viagens", methods=["GET"])
    @login_required
    @require_empresa
    def viagens():

        empresa_id = session.get("empresa_id")

        # 🔎 FILTROS (RANGE + RÁPIDO)
        periodo = request.args.get("periodo")
        filtro = request.args.get("filtro")

        data_inicio = None
        data_fim = None

        hoje = date.today()

        # ===============================
        # 📅 FILTRO POR PERÍODO (CALENDÁRIO)
        # ===============================
        from datetime import datetime

        if periodo:
            try:
                datas = periodo.split(" to ")

                data_inicio = datetime.strptime(datas[0], "%Y-%m-%d").date()

                if len(datas) > 1:
                    data_fim = datetime.strptime(datas[1], "%Y-%m-%d").date()
                else:
                    data_fim = data_inicio

            except Exception:
                data_inicio = None
                data_fim = None

        # ===============================
        # ⚡ FILTROS RÁPIDOS
        # ===============================
        elif filtro == "mes_atual":
            data_inicio = date(hoje.year, hoje.month, 1)
            data_fim = hoje

        elif filtro == "mes_anterior":
            from datetime import timedelta

            primeiro_dia_mes = date(hoje.year, hoje.month, 1)
            ultimo_mes = primeiro_dia_mes - timedelta(days=1)

            data_inicio = date(ultimo_mes.year, ultimo_mes.month, 1)
            data_fim = ultimo_mes

        elif filtro == "ano":
            data_inicio = date(hoje.year, 1, 1)
            data_fim = hoje

        conn = conectar()
        cur = conn.cursor()

        # ======================================================
        # QUERY DINÂMICA (PROFISSIONAL)
        # ======================================================
        query = """
            SELECT 
                v.*,
                m.nome AS municipio_nome
            FROM viagens v
            JOIN municipios m ON m.id = v.municipio_id
            WHERE v.empresa_id = %s
        """

        params = [empresa_id]

        if data_inicio:
            query += " AND v.data_viagem >= %s"
            params.append(data_inicio)

        if data_fim:
            query += " AND v.data_viagem <= %s"
            params.append(data_fim)

        query += " ORDER BY v.data_viagem DESC"

        cur.execute(query, params)

        viagens = cur.fetchall()

        # ======================================================
        # MUNICÍPIOS PARA SELECT
        # ======================================================
        cur.execute("""
            SELECT id, nome
            FROM municipios
            ORDER BY nome
        """)

        municipios = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "viagens.html",
            viagens=viagens,
            municipios=municipios,
            filtro=filtro,
            data_inicio=data_inicio,
            data_fim=data_fim
        )


    # ======================================================
    # NOVA VIAGEM
    # ======================================================
    @app.route("/viagens/nova", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def viagens_nova():

        empresa_id = session.get("empresa_id")

        municipio_id = request.form.get("municipio_id")
        veiculo = request.form.get("veiculo")

        # 🔹 KM
        km_saida = float(request.form.get("km_saida") or 0)
        km_chegada = float(request.form.get("km_chegada") or 0)
        km_rodado = km_chegada - km_saida

        # 🔹 GASTOS (COMPATÍVEL COM MÁSCARA BR)
        def parse_decimal(valor, default=0.0):
            try:
                if not valor:
                    return float(default)

                v = str(valor).replace("R$", "").strip()

                if "," in v:
                    v = v.replace(".", "").replace(",", ".")

                return float(v)
            except:
                return float(default)


        combustivel = parse_decimal(request.form.get("combustivel"))
        refeicao = parse_decimal(request.form.get("refeicao"))
        hotel = parse_decimal(request.form.get("hotel"))

        custo_total = combustivel + refeicao + hotel

        observacao = request.form.get("observacao")

        # 🔒 VALIDAÇÃO PROFISSIONAL
        if km_chegada < km_saida:
            flash("KM de chegada não pode ser menor que o KM de saída.", "warning")
            return redirect("/viagens")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO viagens (
                empresa_id,
                municipio_id,
                veiculo,
                km_saida,
                km_chegada,
                km_rodado,
                gasto_combustivel,
                gasto_refeicao,
                gasto_hotel,
                custo_total,
                data_viagem,
                observacao
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            empresa_id,
            municipio_id,
            veiculo,
            km_saida,
            km_chegada,
            km_rodado,
            combustivel,
            refeicao,
            hotel,
            custo_total,
            date.today(),
            observacao
        ))

        conn.commit()
        cur.close()
        conn.close()

        flash("Viagem cadastrada com sucesso.", "success")

        return redirect("/viagens")
    
    # ======================================================
    # EDITAR VIAGEM
    # ======================================================
    @app.route("/viagens/<int:id>/editar", methods=["GET", "POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "SUPER_ADMIN")
    def viagens_editar(id):

        conn = conectar()
        cur = conn.cursor()

        if request.method == "POST":

            veiculo = request.form.get("veiculo")

            km_saida = float(request.form.get("km_saida") or 0)
            km_chegada = float(request.form.get("km_chegada") or 0)
            km_rodado = km_chegada - km_saida

            def parse_decimal(valor, default=0.0):
                try:
                    if not valor:
                        return float(default)

                    v = str(valor).replace("R$", "").strip()

                    if "," in v:
                        v = v.replace(".", "").replace(",", ".")

                    return float(v)
                except:
                    return float(default)

            combustivel = parse_decimal(request.form.get("combustivel"))
            refeicao = parse_decimal(request.form.get("refeicao"))
            hotel = parse_decimal(request.form.get("hotel"))

            custo_total = combustivel + refeicao + hotel

            cur.execute("""
                UPDATE viagens
                SET veiculo=%s,
                    km_saida=%s,
                    km_chegada=%s,
                    km_rodado=%s,
                    gasto_combustivel=%s,
                    gasto_refeicao=%s,
                    gasto_hotel=%s,
                    custo_total=%s
                WHERE id=%s
            """, (
                veiculo,
                km_saida,
                km_chegada,
                km_rodado,
                combustivel,
                refeicao,
                hotel,
                custo_total,
                id
            ))

            conn.commit()
            flash("Viagem atualizada com sucesso.", "success")
            return redirect("/viagens")

        cur.execute("SELECT * FROM viagens WHERE id=%s", (id,))
        viagem = cur.fetchone()

        conn.close()

        return render_template("viagens_editar.html", viagem=viagem)


    # ======================================================
    # EXCLUIR VIAGEM
    # ======================================================
    @app.route("/viagens/<int:id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "SUPER_ADMIN")
    def viagens_excluir(id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                DELETE FROM viagens
                WHERE id = %s
                AND empresa_id = %s
            """, (id, empresa_id))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Viagem não encontrada.", "danger")
            else:
                conn.commit()
                flash("Viagem excluída com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir viagem: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/viagens")
    
   
