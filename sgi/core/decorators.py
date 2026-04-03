from functools import wraps
from flask import session, redirect, flash

# ======================================================
# GARANTE QUE UMA EMPRESA ESTEJA SELECIONADA
# ======================================================

def empresa_ativa_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        empresa_id = session.get("empresa_id")

        if not empresa_id:
            flash("Nenhuma empresa selecionada.", "warning")
            return redirect("/selecionar-empresa")

        return func(*args, **kwargs)

    return wrapper