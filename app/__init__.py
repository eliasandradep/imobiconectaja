from flask import Flask, g, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
import os

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()


def _resolver_imobiliaria(host, app):
    """
    Resolve qual Imobiliária corresponde ao host recebido.

    Ordem de tentativas:
      1. Hosts da plataforma (localhost, 127.0.0.1, domínio raiz) → None (landing page)
      2. Domínio personalizado exato       →  www.imobiliaria.com.br
      3. Domínio personalizado sem www     →  imobiliaria.com.br
      4. Subdomínio da plataforma          →  slug.imobiconectaja.com.br
      5. Legado: campo 'dominio' exato     →  qualquer valor salvo

    Acesso em desenvolvimento (sem subdomínio):
      - localhost:5000/          → landing page
      - localhost:5000/{slug}/   → site da imobiliária (rota em site_bp)
      - localhost:5000/{slug}/painel → painel admin  (rota em site_bp)
    """
    from .models import Imobiliaria

    base     = app.config.get('BASE_DOMAIN', '').strip().lower()
    platform = app.config.get('PLATFORM_HOSTS', set())

    # 1 — Hosts próprios da plataforma nunca resolvem para uma imobiliária.
    #     Inclui localhost, 127.0.0.1, 0.0.0.0 e o domínio raiz da plataforma.
    if host in platform:
        return None
    if base and host in (base, f'www.{base}'):
        return None

    # 2 & 3 — Domínio personalizado (com e sem www)
    host_sem_www = host[4:] if host.startswith('www.') else host
    imob = (
        Imobiliaria.query.filter(
            Imobiliaria.dominio_personalizado.in_([host, host_sem_www]),
            Imobiliaria.ativo == True          # noqa: E712
        ).first()
    )
    if imob:
        return imob

    # 4 — Subdomínio da plataforma  (slug.base_domain)
    if base and host.endswith(f'.{base}'):
        slug = host[:-(len(base) + 1)]
        if slug and slug != 'www':
            imob = Imobiliaria.query.filter_by(slug=slug, ativo=True).first()
            if imob:
                return imob

    # 5 — Campo legado 'dominio' (compatibilidade com registros antigos)
    return Imobiliaria.query.filter_by(dominio=host, ativo=True).first()


def create_app():
    app = Flask(__name__)

    # Carrega config do objeto Config (inclui BASE_DOMAIN)
    from config import Config
    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024   # 16 MB upload máximo

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    mail.init_app(app)

    # ── Registro de Blueprints ─────────────────────────────────────
    from .auth.routes       import auth_bp
    from .admin.routes      import admin_bp
    from .site.routes       import site_bp
    from .leads.routes      import leads_bp
    from .api.routes        import api_bp
    from .superadmin.routes import superadmin_bp
    from .pessoas.routes    import pessoas_bp
    from .cliente.routes    import cliente_bp
    from .whatsapp.routes   import whatsapp_bp

    app.register_blueprint(auth_bp,       url_prefix='/auth')
    app.register_blueprint(admin_bp,      url_prefix='/admin')
    app.register_blueprint(leads_bp,      url_prefix='/admin/leads')
    app.register_blueprint(pessoas_bp,    url_prefix='/admin/pessoas')
    app.register_blueprint(api_bp,        url_prefix='/api')
    app.register_blueprint(superadmin_bp, url_prefix='/superadmin')
    app.register_blueprint(cliente_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(site_bp)

    # ── Middleware: identifica a imobiliária pelo domínio ──────────
    @app.before_request
    def carregar_imobiliaria():
        if request.endpoint == 'static':
            return
        from flask import session
        host = request.host.split(':')[0].lower()
        g.imobiliaria = _resolver_imobiliaria(host, app)

        # Fallback para navegação em desenvolvimento (host da plataforma):
        # restaura a imobiliária gravada na sessão para as rotas do site público,
        # permitindo que /imovel/<id>, /p/<slug> etc. funcionem após entrar via /<slug>/.
        if not g.imobiliaria:
            imob_id = session.get('_site_imob_id')
            if imob_id and request.endpoint and request.endpoint.startswith('site.') \
                    and request.endpoint != 'site.index':
                from .models import Imobiliaria
                g.imobiliaria = Imobiliaria.query.filter_by(
                    id=imob_id, ativo=True
                ).first()

    # ── Helper: URL pública do site de uma imobiliária ───────────
    def url_site_imobiliaria(imob):
        """Retorna a URL pública correta do site da imobiliária."""
        if not imob:
            return '/'
        if getattr(imob, 'dominio_personalizado', None):
            return f'https://{imob.dominio_personalizado}'
        base = app.config.get('BASE_DOMAIN', '').strip()
        if base and getattr(imob, 'slug', None):
            return f'https://{imob.slug}.{base}'
        # fallback desenvolvimento: roteamento por slug no path
        return f'/{imob.slug}/'

    # ── Context processor: menu dinâmico + badge de leads novos ────
    @app.context_processor
    def injetar_contexto():
        from app.superadmin.routes import PLANOS_CONFIG
        extras = {'config': app.config, 'url_site_imob': url_site_imobiliaria,
                  'planos_config': PLANOS_CONFIG}

        if not getattr(g, 'imobiliaria', None):
            return {**extras, 'menu_links': [], 'menu_paginas': [], 'leads_novos_count': 0}

        from .models import MenuLink, PaginaSite, Lead
        menu_links = MenuLink.query.filter_by(
            imobiliaria_id=g.imobiliaria.id, ativo=True
        ).order_by(MenuLink.ordem).all()
        menu_paginas = PaginaSite.query.filter_by(
            imobiliaria_id=g.imobiliaria.id, ativo=True, no_menu=True
        ).order_by(PaginaSite.ordem).all()
        leads_novos_count = Lead.query.filter_by(
            imobiliaria_id=g.imobiliaria.id, status='Novo'
        ).count()
        return {
            **extras,
            'menu_links': menu_links,
            'menu_paginas': menu_paginas,
            'leads_novos_count': leads_novos_count,
        }

    return app


@login_manager.user_loader
def load_user(user_id):
    user_id = str(user_id)
    if user_id.startswith('sa:'):
        from .models import SuperAdmin
        return SuperAdmin.query.get(int(user_id[3:]))
    from .models import Usuario
    return Usuario.query.get(int(user_id))
