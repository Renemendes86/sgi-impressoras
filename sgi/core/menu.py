from flask import session
from sgi.core.db import conectar
from sgi.core.permissions import tem_permissao


def gerar_menu():

    menu = []

    usuario_id = session.get("usuario_id")
    perfil = (session.get("perfil") or "").upper()

    conn = conectar()
    cur = conn.cursor()

    # DASHBOARD
    menu.append({
        "nome": "Dashboard",
        "url": "/dashboard"
    })

    # CLIENTES
    menu.append({
        "nome": "Clientes",
        "url": "/clientes"
    })

    # IMPRESSORAS
    menu.append({
        "nome": "Impressoras",
        "url": "/impressoras"
    })

    # PRODUTOS
    menu.append({
        "nome": "Produtos",
        "url": "/produtos"
    })

    # SERVIÇOS
    menu.append({
        "nome": "Serviços",
        "url": "/servicos"
    })

    # LOCAÇÕES
    menu.append({
        "nome": "Locações",
        "url": "/locacoes"
    })

    # FINANCEIRO
    if tem_permissao(cur, usuario_id, "VER_FINANCEIRO"):
        menu.append({
            "nome": "Financeiro",
            "url": "/financeiro"
        })

    # EMPRESAS (somente admin)
    if perfil in ["SUPER_ADMIN", "ADMIN"]:
        menu.append({
            "nome": "Empresas",
            "url": "/empresas"
        })

    # USUÁRIOS
    if perfil in ["SUPER_ADMIN", "ADMIN"] or tem_permissao(cur, usuario_id, "ADMIN_USUARIOS"):
        menu.append({
            "nome": "Usuários",
            "url": "/usuarios"
        })

    cur.close()
    conn.close()

    return menu