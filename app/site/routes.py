from datetime import datetime
from flask import Blueprint, render_template, g, abort, request, redirect, url_for
from ..models import Imovel, TipoImovel

site_bp = Blueprint('site', __name__)

# Segmentos de URL reservados pela própria plataforma.
# Impede que /<slug>/ engula rotas de outros blueprints.
_RESERVADOS = {
    'admin', 'auth', 'superadmin', 'api', 'leads', 'pessoas',
    'static', 'imovel', 'p',
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: renderiza a homepage da imobiliária (reutilizado por 2 rotas)
# Requer g.imobiliaria preenchido.
# ─────────────────────────────────────────────────────────────────────────────

def _render_site_index():
    finalidade = request.args.get('finalidade', '').strip()
    tipo_id    = request.args.get('tipo_id',    '', type=str)
    cidade     = request.args.get('cidade',     '').strip()
    preco_max  = request.args.get('preco_max',  '', type=str)
    quartos    = request.args.get('quartos',    '', type=str)

    query = Imovel.query.filter_by(imobiliaria_id=g.imobiliaria.id)

    if finalidade:
        query = query.filter(Imovel.finalidade == finalidade)
    if tipo_id:
        query = query.filter(Imovel.tipo_id == int(tipo_id))
    if cidade:
        like = f"%{cidade}%"
        from ..models import db
        query = query.filter(
            db.or_(Imovel.cidade.ilike(like), Imovel.bairro.ilike(like))
        )
    if preco_max:
        query = query.filter(Imovel.preco <= float(preco_max))
    if quartos:
        query = query.filter(Imovel.quartos >= int(quartos))

    _ord_map = {
        'recentes':   Imovel.id.desc(),
        'destaque':   (Imovel.destaque.desc(), Imovel.id.desc()),
        'preco_asc':  Imovel.preco.asc(),
        'preco_desc': Imovel.preco.desc(),
    }
    _ord_val = _ord_map.get(g.imobiliaria.ordenacao_imoveis or 'recentes', Imovel.id.desc())
    if isinstance(_ord_val, tuple):
        query = query.order_by(*_ord_val)
    else:
        query = query.order_by(_ord_val)

    page       = request.args.get('page', 1, type=int)
    per_page   = g.imobiliaria.imoveis_por_pagina or 9
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tipos      = TipoImovel.query.filter_by(imobiliaria_id=g.imobiliaria.id).all()
    filtros_ativos = any([finalidade, tipo_id, cidade, preco_max, quartos])

    return render_template(
        'site/index.html',
        imoveis=pagination.items,
        pagination=pagination,
        tipos=tipos,
        filtros=dict(finalidade=finalidade, tipo_id=tipo_id,
                     cidade=cidade, preco_max=preco_max, quartos=quartos),
        filtros_ativos=filtros_ativos,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rota raiz: landing page da plataforma OU site da imobiliária (por subdomínio)
# ─────────────────────────────────────────────────────────────────────────────

@site_bp.route('/')
def index():
    if not g.imobiliaria:
        return render_template('landing.html', now=datetime.utcnow())
    return _render_site_index()


# ─────────────────────────────────────────────────────────────────────────────
# Atalho /painel — acesso direto ao painel quando imobiliária já está no contexto
# Usado em produção: slug.imobiconectaja.com.br/painel
# ─────────────────────────────────────────────────────────────────────────────

@site_bp.route('/painel')
def painel():
    if not g.imobiliaria:
        return redirect(url_for('site.index'))
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────────────────────
# Rotas path-based para desenvolvimento local
# localhost:5000/{slug}/         → site da imobiliária
# localhost:5000/{slug}/painel   → painel admin da imobiliária
# ─────────────────────────────────────────────────────────────────────────────

@site_bp.route('/<slug>/')
@site_bp.route('/<slug>')
def slug_site(slug):
    """Acesso ao site da imobiliária via path (desenvolvimento local)."""
    if slug in _RESERVADOS:
        abort(404)
    from ..models import Imobiliaria
    from flask import session
    imob = Imobiliaria.query.filter_by(slug=slug, ativo=True).first_or_404()
    g.imobiliaria = imob
    # Grava na sessão para que rotas internas (/imovel/<id>, /p/<slug>) funcionem
    session['_site_imob_id'] = imob.id
    return _render_site_index()


@site_bp.route('/<slug>/painel')
def slug_painel(slug):
    """Acesso ao painel admin da imobiliária via path (desenvolvimento local)."""
    if slug in _RESERVADOS:
        abort(404)
    from ..models import Imobiliaria
    Imobiliaria.query.filter_by(slug=slug, ativo=True).first_or_404()
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────────────────────
# Demais rotas do site da imobiliária
# ─────────────────────────────────────────────────────────────────────────────

@site_bp.route('/imovel/<int:id>')
def detalhes(id):
    if not g.imobiliaria:
        abort(404)
    imovel = Imovel.query.filter_by(id=id, imobiliaria_id=g.imobiliaria.id).first_or_404()
    return render_template('site/detalhes.html', imovel=imovel)


@site_bp.route('/p/<slug>')
def pagina(slug):
    from ..models import PaginaSite
    if not g.imobiliaria:
        abort(404)
    p = PaginaSite.query.filter_by(
        imobiliaria_id=g.imobiliaria.id,
        slug=slug,
        ativo=True
    ).first_or_404()
    return render_template('site/pagina.html', pagina=p)
