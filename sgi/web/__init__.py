# ==========================================================
# REGISTRO CENTRAL DE ROTAS DO SISTEMA
# ==========================================================

from sgi.web.routes_auth import configurar_rotas_auth
from sgi.web.routes_dashboard import configurar_rotas_dashboard
from sgi.web.routes_clientes import configurar_rotas_clientes
from sgi.web.routes_impressoras import configurar_rotas_impressoras
from sgi.web.routes_produtos import configurar_rotas_produtos
from sgi.web.routes_servicos import configurar_rotas_servicos
from sgi.web.routes_locacoes import configurar_rotas_locacoes
from sgi.web.routes_contratos_publicos import configurar_rotas_contratos_publicos
from sgi.web.routes_municipios import configurar_rotas_municipios
from sgi.web.routes_usuarios import configurar_rotas_usuarios
from sgi.web.routes_empresas import configurar_rotas_empresas
from sgi.web.routes_viagens import configurar_rotas_viagens


def registrar_rotas(app):
    """
    Registra todas as rotas do sistema.
    Arquitetura modular por responsabilidade.
    """
    from .routes_financeiro import configurar_rotas_financeiro
    # Autenticação / Login
    configurar_rotas_auth(app)

    # Núcleo do sistema
    configurar_rotas_dashboard(app)
    configurar_rotas_clientes(app)
    configurar_rotas_impressoras(app)
    configurar_rotas_produtos(app)
    configurar_rotas_servicos(app)
    configurar_rotas_locacoes(app)
    configurar_rotas_contratos_publicos(app)
    configurar_rotas_municipios(app)
    configurar_rotas_viagens(app)

    # Administração
    configurar_rotas_usuarios(app)
    configurar_rotas_empresas(app)
    configurar_rotas_financeiro(app)