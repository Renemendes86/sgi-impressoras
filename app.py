# ==========================================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================================

import os
from pathlib import Path

# Garante UTF-8 no Windows
os.environ["PYTHONUTF8"] = "1"
os.environ["PGCLIENTENCODING"] = "UTF8"

from flask import Flask
from dotenv import load_dotenv

# ==========================================================
# BASE DIR / .ENV
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Força leitura correta do .env, mesmo no Windows
load_dotenv(
    dotenv_path=ENV_PATH,
    override=True,
    encoding="utf-8"
)

# ==========================================================
# APLICAÇÃO FLASK
# ==========================================================

app = Flask(
    __name__,
    template_folder="sgi/web/templates",
    static_folder="sgi/web/static",
)

# ==========================================================
# CONFIGURAÇÕES GERAIS
# ==========================================================

# ⚠️ ESSENCIAL para sessões, login, permissões e segurança
app.secret_key = os.getenv(
    "SECRET_KEY",
    "sgi-secret-key-dev"  # fallback apenas para DEV
)

# 🔥 LIMITE DE UPLOAD (SEGURANÇA)
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH", 16777216)
)

# 🔒 SEGURANÇA DE SESSÃO (OBRIGATÓRIO PRODUÇÃO)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ==========================================================
# FILTROS JINJA (PADRÃO BRASILEIRO)
# ==========================================================

def moeda_brl(valor):
    """
    Formata valores para Real Brasileiro
    Ex.: 1234.5 -> R$ 1.234,50
    """
    try:
        valor = float(valor or 0)
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


# Registro do filtro no Jinja
app.jinja_env.filters["brl"] = moeda_brl

# ==========================================================
# REGISTRO CENTRAL DE ROTAS (PADRÃO OFICIAL DO PROJETO)
# ==========================================================

try:
    from sgi.web import registrar_rotas
except ImportError as e:
    raise ImportError(
        "Erro ao importar registrar_rotas. "
        "Verifique se o arquivo sgi/web/__init__.py "
        "define corretamente a função registrar_rotas."
    ) from e

registrar_rotas(app)

# ==========================================================
# CONTEXTO GLOBAL (USUÁRIO / PERMISSÕES / EMPRESA)
# ==========================================================

from flask import session

@app.context_processor
def inject_user_context():
    """
    Disponibiliza dados do usuário logado
    em TODOS os templates automaticamente.
    """

    perfil = (session.get("perfil") or "").upper()

    return dict(
        usuario_logado=session.get("usuario"),
        perfil_usuario=perfil,
        empresa_nome=session.get("empresa_nome"),
        pode_trocar_empresa=session.get("pode_multiempresa", False)
        or perfil == "SUPER_ADMIN"
    )

# ==========================================================
# EXECUÇÃO
# ==========================================================

if __name__ == "__main__":
    # Em produção, debug deve ser False
    app.run(debug=False)
