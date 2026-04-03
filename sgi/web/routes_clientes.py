# ==========================================================
# ROUTES – CLIENTES
# ==========================================================

from flask import (
    render_template,
    request,
    redirect,
    flash,
    session
)

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required
)

import re

# ==========================================================
# HELPERS LOCAIS
# ==========================================================

def so_numeros(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf: str) -> bool:
    cpf = so_numeros(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def calc(digs):
        s = sum(int(digs[i]) * (len(digs) + 1 - i) for i in range(len(digs)))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    d1 = calc(cpf[:9])
    d2 = calc(cpf[:9] + str(d1))
    return cpf[-2:] == f"{d1}{d2}"


def cnpj_valido(cnpj: str) -> bool:
    cnpj = so_numeros(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pesos2 = [6] + pesos1

    def calc(base, pesos):
        s = sum(int(base[i]) * pesos[i] for i in range(len(pesos)))
        r = s % 11
        return 0 if r < 2 else 11 - r

    d1 = calc(cnpj[:12], pesos1)
    d2 = calc(cnpj[:12] + str(d1), pesos2)
    return cnpj[-2:] == f"{d1}{d2}"


def documento_valido(tipo: str, doc: str) -> bool:
    if tipo == "FISICA":
        return cpf_valido(doc)
    if tipo == "JURIDICA":
        return cnpj_valido(doc)
    return False

def detectar_municipio(nome_cliente, cur):

    nome_cliente = nome_cliente.upper()

    cur.execute("""
        SELECT id, nome
        FROM municipios
    """)

    municipios = cur.fetchall()

    for m in municipios:
        if m["nome"].upper() in nome_cliente:
            return m["id"]

    return None


# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_clientes(app):

    # ======================================================
    # LISTAGEM DE CLIENTES
    # ======================================================
    @app.route("/clientes", methods=["GET"])
    @login_required
    @require_empresa
    def clientes_listar():

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                c.id,
                c.tipo_pessoa,
                c.nome,
                c.cnpj_cpf,
                c.telefone,
                c.email,
                c.municipio_id,
                m.nome AS municipio_nome
            FROM clientes c
            LEFT JOIN municipios m ON m.id = c.municipio_id
            WHERE c.empresa_id = %s
            ORDER BY c.nome
        """, (empresa_id,))

        clientes = cur.fetchall()

        # BUSCAR MUNICÍPIOS
        cur.execute("""
            SELECT id, nome
            FROM municipios
            ORDER BY nome
        """)

        municipios = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "clientes.html",
            clientes=clientes,
            municipios=municipios
        )

    # ======================================================
    # NOVO CLIENTE
    # ======================================================
    @app.route("/clientes/novo", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR" , "SUPER_ADMIN")
    def clientes_novo():

        empresa_id = session.get("empresa_id")

        tipo_pessoa = (request.form.get("tipo_pessoa") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        cnpj_cpf = so_numeros(request.form.get("cnpj_cpf"))
        telefone = (request.form.get("telefone") or "").strip()
        email = (request.form.get("email") or "").strip()
        municipio_id = request.form.get("municipio_id")
        # detectar automaticamente se não foi escolhido
        if not municipio_id:
            municipio_id = detectar_municipio(nome, cur)

        if not nome:
            flash("Cadastro não realizado: informe o nome do cliente.", "warning")
            return redirect("/clientes")

        if not documento_valido(tipo_pessoa, cnpj_cpf):
            flash("Cadastro não realizado: CPF ou CNPJ inválido.", "danger")
            return redirect("/clientes")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT 1
                FROM clientes
                WHERE empresa_id = %s AND cnpj_cpf = %s
            """, (empresa_id, cnpj_cpf))

            if cur.fetchone():
                flash("Já existe um cliente com este CPF/CNPJ nesta empresa.", "warning")
                return redirect("/clientes")

            cur.execute("""
                INSERT INTO clientes
                    (empresa_id, tipo_pessoa, nome, cnpj_cpf, telefone, email, municipio_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                empresa_id,
                tipo_pessoa,
                nome,
                cnpj_cpf,
                telefone,
                email,
                municipio_id
            ))

            conn.commit()
            flash("Cliente cadastrado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar cliente: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/clientes")

   # ======================================================
    # EDITAR CLIENTE
    # ======================================================
    @app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def clientes_editar(cliente_id):

        empresa_id = session.get("empresa_id")

        # ======================================================
        # GET → carregar dados do cliente
        # ======================================================
        if request.method == "GET":

            conn = conectar()
            cur = conn.cursor()

            cur.execute("""
                SELECT 
                    c.id,
                    c.tipo_pessoa,
                    c.nome,
                    c.cnpj_cpf,
                    c.telefone,
                    c.email,
                    c.municipio_id,
                    m.nome AS municipio_nome
                FROM clientes c
                LEFT JOIN municipios m ON m.id = c.municipio_id
                WHERE c.id = %s AND c.empresa_id = %s
            """, (cliente_id, empresa_id))

            cliente = cur.fetchone()

            if not cliente:
                flash("Cliente não encontrado.", "danger")
                return redirect("/clientes")

            cur.execute("""
                SELECT id, nome
                FROM municipios
                ORDER BY nome
            """)
            municipios = cur.fetchall()

            cur.close()
            conn.close()

            return render_template(
                "clientes.html",
                cliente_editar=cliente,
                municipios=municipios
            )

        # ======================================================
        # POST → salvar edição
        # ======================================================

        tipo_pessoa = (request.form.get("tipo_pessoa") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        cnpj_cpf = so_numeros(request.form.get("cnpj_cpf"))
        telefone = (request.form.get("telefone") or "").strip()
        email = (request.form.get("email") or "").strip()
        municipio_id = request.form.get("municipio_id")

        # 🔥 TRATAMENTO CORRETO DO MUNICÍPIO
        if not municipio_id:
            municipio_id = None
        else:
            municipio_id = int(municipio_id)

        if not nome:
            flash("Atualização não realizada: informe o nome do cliente.", "warning")
            return redirect("/clientes")

        if not documento_valido(tipo_pessoa, cnpj_cpf):
            flash("Atualização não realizada: CPF ou CNPJ inválido.", "danger")
            return redirect("/clientes")

        conn = conectar()
        cur = conn.cursor()

        try:

            cur.execute("""
                UPDATE clientes
                SET tipo_pessoa=%s,
                    nome=%s,
                    cnpj_cpf=%s,
                    telefone=%s,
                    email=%s,
                    municipio_id=%s
                WHERE id=%s AND empresa_id=%s
            """, (
                tipo_pessoa,
                nome,
                cnpj_cpf,
                telefone,
                email,
                municipio_id,
                cliente_id,
                empresa_id
            ))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Cliente não encontrado.", "danger")
            else:
                conn.commit()
                flash("Cliente atualizado com sucesso.", "modal_success")
                flash("Erro ao atualizar cliente.", "modal_error")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar cliente: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/clientes")

    # ======================================================
    # EXCLUIR CLIENTE
    # ======================================================
    @app.route("/clientes/<int:cliente_id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN" , "SUPER_ADMIN")
    def clientes_excluir(cliente_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        try:
            # Bloqueio por vínculo ativo
            cur.execute("""
                SELECT 1
                FROM impressoras
                WHERE empresa_id=%s
                  AND cliente_id=%s
                  AND locada=TRUE
                LIMIT 1
            """, (empresa_id, cliente_id))

            if cur.fetchone():
                flash(
                    "Exclusão bloqueada: cliente possui impressoras locadas.",
                    "warning"
                )
                return redirect("/clientes")

            cur.execute("""
                DELETE FROM clientes
                WHERE id=%s AND empresa_id=%s
            """, (cliente_id, empresa_id))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Cliente não encontrado.", "danger")
            else:
                conn.commit()
                flash("Cliente excluído com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir cliente: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/clientes")
