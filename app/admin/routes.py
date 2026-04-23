import os, uuid, shutil
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import login_required, current_user
from ..models import Imovel, Foto, TipoImovel, BannerSite, db

TEMAS = [
    {'id': 'clean',   'nome': 'Clean Azul',    'descricao': 'Clássico e profissional',
     'cores': ['#0d6efd', '#0d1b2a', '#f8f9fa']},
    {'id': 'escuro',  'nome': 'Dark Luxury',   'descricao': 'Elegante e sofisticado',
     'cores': ['#e94560', '#0f3460', '#16213e']},
    {'id': 'verde',   'nome': 'Verde Natureza','descricao': 'Fresco e equilibrado',
     'cores': ['#52b788', '#1b4332', '#d8f3dc']},
    {'id': 'laranja', 'nome': 'Energia',       'descricao': 'Vibrante e dinâmico',
     'cores': ['#f4831f', '#7f3100', '#fff3e0']},
    {'id': 'roxo',    'nome': 'Luxo Premium',  'descricao': 'Exclusivo e refinado',
     'cores': ['#7b2fbe', '#2d0057', '#ede7f6']},
    {'id': 'cinza',   'nome': 'Minimalista',   'descricao': 'Limpo e neutro',
     'cores': ['#6c757d', '#212529', '#f8f9fa']},
]

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
def verificar_acesso_admin():
    """Bloqueia superadmins e usuários de imobiliárias inativas."""
    from flask_login import current_user
    from flask import redirect, url_for
    if not current_user.is_authenticated:
        return  # login_required cuida do redirect
    if getattr(current_user, 'is_superadmin', False):
        return redirect(url_for('superadmin.dashboard'))
    from ..models import Imobiliaria
    imob = Imobiliaria.query.get(current_user.imobiliaria_id)
    if not imob or not imob.ativo:
        from flask_login import logout_user
        logout_user()
        from flask import flash
        flash('Sua conta foi suspensa. Entre em contato com o suporte.', 'danger')
        return redirect(url_for('auth.login'))


# Filtro de Moeda Brasileira para os Templates
@admin_bp.app_template_filter('moeda')
def moeda_filter(valor):
    if valor is None: return "R$ 0,00"
    try:
        formato = "{:,.2f}".format(float(valor))
        return "R$ " + formato.replace(',', 'v').replace('.', ',').replace('v', '.')
    except:
        return "R$ 0,00"

# --- DASHBOARD E LISTAGEM ---

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    from ..models import Lead
    from datetime import datetime, timedelta
    import json

    imob_id = current_user.imobiliaria_id
    hoje    = datetime.utcnow().date()

    # ── Imóveis ──────────────────────────────────────────────────
    imoveis_total   = Imovel.query.filter_by(imobiliaria_id=imob_id).count()
    imoveis_venda   = Imovel.query.filter_by(imobiliaria_id=imob_id, finalidade='Venda').count()
    imoveis_locacao = Imovel.query.filter_by(imobiliaria_id=imob_id, finalidade='Locação').count()

    # ── Leads por status ─────────────────────────────────────────
    leads_total       = Lead.query.filter_by(imobiliaria_id=imob_id).count()
    leads_novos       = Lead.query.filter_by(imobiliaria_id=imob_id, status='Novo').count()
    leads_qualificados= Lead.query.filter_by(imobiliaria_id=imob_id, status='Qualificado').count()
    leads_arquivados  = Lead.query.filter_by(imobiliaria_id=imob_id, status='Arquivado').count()
    leads_perdidos    = Lead.query.filter_by(imobiliaria_id=imob_id, status='Perdido').count()
    taxa_qualificacao = round(leads_qualificados / leads_total * 100) if leads_total else 0

    # ── Leads por período ─────────────────────────────────────────
    leads_hoje   = Lead.query.filter(Lead.imobiliaria_id == imob_id,
                       db.func.date(Lead.data_contato) == str(hoje)).count()
    leads_semana = Lead.query.filter(Lead.imobiliaria_id == imob_id,
                       Lead.data_contato >= datetime.utcnow() - timedelta(days=7)).count()
    leads_mes    = Lead.query.filter(Lead.imobiliaria_id == imob_id,
                       Lead.data_contato >= datetime.utcnow() - timedelta(days=30)).count()

    # ── Leads por origem ─────────────────────────────────────────
    origens_raw    = (db.session.query(Lead.origem, db.func.count(Lead.id))
                       .filter_by(imobiliaria_id=imob_id)
                       .group_by(Lead.origem).all())
    leads_por_origem = {o: c for o, c in origens_raw}

    # ── Série temporal: últimos 30 dias ──────────────────────────
    serie_raw = (db.session.query(
                     db.func.date(Lead.data_contato).label('dia'),
                     db.func.count(Lead.id).label('total'))
                 .filter(Lead.imobiliaria_id == imob_id,
                         Lead.data_contato >= datetime.utcnow() - timedelta(days=29))
                 .group_by(db.func.date(Lead.data_contato)).all())
    serie_dict = {str(r.dia): r.total for r in serie_raw}
    labels_dias, dados_dias = [], []
    for i in range(29, -1, -1):
        d = hoje - timedelta(days=i)
        labels_dias.append(d.strftime('%d/%m'))
        dados_dias.append(serie_dict.get(str(d), 0))

    # ── Últimos leads ─────────────────────────────────────────────
    leads_recentes = (Lead.query.filter_by(imobiliaria_id=imob_id)
                      .order_by(Lead.data_contato.desc()).limit(8).all())

    return render_template('admin/dashboard.html',
        imoveis_total=imoveis_total,
        imoveis_venda=imoveis_venda,
        imoveis_locacao=imoveis_locacao,
        leads_total=leads_total,
        leads_novos=leads_novos,
        leads_qualificados=leads_qualificados,
        leads_arquivados=leads_arquivados,
        leads_perdidos=leads_perdidos,
        taxa_qualificacao=taxa_qualificacao,
        leads_hoje=leads_hoje,
        leads_semana=leads_semana,
        leads_mes=leads_mes,
        leads_por_origem=leads_por_origem,
        labels_dias=json.dumps(labels_dias),
        dados_dias=json.dumps(dados_dias),
        leads_recentes=leads_recentes,
    )

@admin_bp.route('/imoveis')
@login_required
def listar_imoveis():
    page       = request.args.get('page', 1, type=int)
    pagination = (Imovel.query
                  .filter_by(imobiliaria_id=current_user.imobiliaria_id)
                  .order_by(Imovel.id.desc())
                  .paginate(page=page, per_page=20, error_out=False))
    return render_template('admin/imoveis.html', imoveis=pagination.items, pagination=pagination)

# --- GESTÃO DE IMÓVEIS (VERSÃO CONGELADA) ---

@admin_bp.route('/imoveis/<int:id>/detalhe')
@login_required
def detalhe_imovel(id):
    imovel = Imovel.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    foto_principal = next((f for f in imovel.fotos if f.principal), None)
    if not foto_principal and imovel.fotos:
        foto_principal = imovel.fotos[0]
    return render_template('admin/detalhe_imovel.html',
                           imovel=imovel,
                           foto_principal=foto_principal)


@admin_bp.route('/imoveis/novo', methods=['GET', 'POST'])
@login_required
def novo_imovel():
    tipos = TipoImovel.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).all()
    if request.method == 'GET':
        session['upload_session_id'] = str(uuid.uuid4())
    
    if request.method == 'POST':
        try:
            tipo_id = request.form.get('tipo_id')
            tipo_obj = TipoImovel.query.get(tipo_id)
            contagem = Imovel.query.filter_by(imobiliaria_id=current_user.imobiliaria_id, tipo_id=tipo_id).count()
            ref_gerada = f"{tipo_obj.prefixo}{(contagem + 1):03d}"

            novo = Imovel(
                imobiliaria_id=current_user.imobiliaria_id,
                tipo_id=tipo_id,
                codigo_ref=ref_gerada,
                titulo=request.form.get('titulo'),
                finalidade=request.form.get('finalidade'),
                preco=float(request.form.get('preco_real') or 0),
                valor_condominio=float(request.form.get('condo_real') or 0),
                valor_iptu=float(request.form.get('iptu_real') or 0),
                area_util=float(request.form.get('area_util') or 0),
                area_total=float(request.form.get('area_total') or 0),
                quartos=int(request.form.get('quartos') or 0),
                suites=int(request.form.get('suites') or 0),
                banheiros=int(request.form.get('banheiros') or 0),
                vagas=int(request.form.get('vagas') or 0),
                cep=request.form.get('cep'),
                logradouro=request.form.get('logradouro'),
                numero=request.form.get('numero'),
                bairro=request.form.get('bairro'),
                cidade=request.form.get('cidade'),
                estado=request.form.get('estado'),
                descricao=request.form.get('descricao'),
                destaque=True if request.form.get('destaque') else False
            )
            db.session.add(novo)
            db.session.flush()

            session_id = session.get('upload_session_id')
            temp_dir = os.path.join('app', 'static', 'uploads', 'temp', session_id)
            final_dir = os.path.join('app', 'static', 'uploads', str(current_user.imobiliaria_id), str(novo.id))
            if os.path.exists(temp_dir):
                os.makedirs(final_dir, exist_ok=True)
                for i, arq in enumerate(os.listdir(temp_dir)):
                    shutil.move(os.path.join(temp_dir, arq), os.path.join(final_dir, arq))
                    db.session.add(Foto(imovel_id=novo.id, url=f"uploads/{current_user.imobiliaria_id}/{novo.id}/{arq}", principal=(i==0)))
                shutil.rmtree(temp_dir)

            db.session.commit()
            flash(f"Imóvel {ref_gerada} cadastrado!", "success")
            return redirect(url_for('admin.listar_imoveis'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro: {e}", "danger")
    return render_template('admin/form_imovel.html', tipos=tipos, imovel=None)

@admin_bp.route('/imoveis/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_imovel(id):
    imovel = Imovel.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    tipos = TipoImovel.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).all()
    if request.method == 'GET': session['upload_session_id'] = str(uuid.uuid4())
    if request.method == 'POST':
        try:
            imovel.tipo_id          = request.form.get('tipo_id')
            imovel.titulo           = request.form.get('titulo')
            imovel.finalidade       = request.form.get('finalidade')
            imovel.preco            = float(request.form.get('preco_real') or 0)
            imovel.valor_condominio = float(request.form.get('condo_real') or 0)
            imovel.valor_iptu       = float(request.form.get('iptu_real') or 0)
            imovel.area_util        = float(request.form.get('area_util') or 0)
            imovel.area_total       = float(request.form.get('area_total') or 0)
            imovel.quartos          = int(request.form.get('quartos') or 0)
            imovel.suites           = int(request.form.get('suites') or 0)
            imovel.banheiros        = int(request.form.get('banheiros') or 0)
            imovel.vagas            = int(request.form.get('vagas') or 0)
            imovel.cep              = request.form.get('cep')
            imovel.logradouro       = request.form.get('logradouro')
            imovel.numero           = request.form.get('numero')
            imovel.bairro           = request.form.get('bairro')
            imovel.cidade           = request.form.get('cidade')
            imovel.estado           = request.form.get('estado')
            imovel.descricao        = request.form.get('descricao')
            imovel.destaque         = True if request.form.get('destaque') else False

            # Processa novas fotos enviadas nesta edição
            session_id = session.get('upload_session_id')
            temp_dir = os.path.join('app', 'static', 'uploads', 'temp', session_id)
            final_dir = os.path.join('app', 'static', 'uploads', str(current_user.imobiliaria_id), str(imovel.id))
            if os.path.exists(temp_dir):
                os.makedirs(final_dir, exist_ok=True)
                for i, arq in enumerate(os.listdir(temp_dir)):
                    shutil.move(os.path.join(temp_dir, arq), os.path.join(final_dir, arq))
                    db.session.add(Foto(imovel_id=imovel.id, url=f"uploads/{current_user.imobiliaria_id}/{imovel.id}/{arq}", principal=False))
                shutil.rmtree(temp_dir)

            db.session.commit()
            flash("Imóvel atualizado!", "success")
            return redirect(url_for('admin.listar_imoveis'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro: {e}", "danger")
    return render_template('admin/form_imovel.html', tipos=tipos, imovel=imovel)

@admin_bp.route('/imoveis/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_imovel(id):
    imovel = Imovel.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    try:
        diretorio = os.path.join('app', 'static', 'uploads', str(current_user.imobiliaria_id), str(imovel.id))
        if os.path.exists(diretorio): shutil.rmtree(diretorio)
        db.session.delete(imovel)
        db.session.commit()
        flash("Imóvel removido!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro: {e}", "danger")
    return redirect(url_for('admin.listar_imoveis'))

# --- GESTÃO DE TIPOS (CORREÇÃO DE DUPLICIDADE E BUILDERROR) ---

@admin_bp.route('/configuracoes/tipos')
@login_required
def listar_tipos():
    tipos = TipoImovel.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).all()
    return render_template('admin/tipos_imovel.html', tipos=tipos)

@admin_bp.route('/configuracoes/tipos/novo', methods=['GET', 'POST'])
@login_required
def novo_tipo():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            prefixo = request.form.get('prefixo').upper()
            novo = TipoImovel(imobiliaria_id=current_user.imobiliaria_id, nome=nome, prefixo=prefixo)
            db.session.add(novo)
            db.session.commit()
            flash(f"Tipo '{nome}' cadastrado!", "success")
            return redirect(url_for('admin.listar_tipos'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro: {e}", "danger")
    return render_template('admin/form_tipo_imovel.html')

@admin_bp.route('/configuracoes/tipos/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_tipo(id):
    tipo = TipoImovel.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    if Imovel.query.filter_by(tipo_id=id).count() > 0:
        flash("Não é possível excluir tipos vinculados a imóveis.", "warning")
    else:
        db.session.delete(tipo)
        db.session.commit()
        flash("Tipo excluído!", "success")
    return redirect(url_for('admin.listar_tipos'))

@admin_bp.route('/fotos/principal/<int:foto_id>', methods=['POST'])
@login_required
def definir_foto_principal(foto_id):
    foto   = Foto.query.get_or_404(foto_id)
    imovel = Imovel.query.get(foto.imovel_id)
    if imovel.imobiliaria_id != current_user.imobiliaria_id:
        return {"ok": False, "erro": "Não autorizado"}, 403

    Foto.query.filter_by(imovel_id=imovel.id).update({"principal": False})
    foto.principal = True
    db.session.commit()
    return {"ok": True}, 200

@admin_bp.route('/fotos/excluir/<int:foto_id>', methods=['POST'])
@login_required
def excluir_foto(foto_id):
    foto   = Foto.query.get_or_404(foto_id)
    imovel = Imovel.query.get(foto.imovel_id)
    if imovel.imobiliaria_id != current_user.imobiliaria_id:
        return {"ok": False, "erro": "Não autorizado"}, 403

    filepath = os.path.join('app', 'static', foto.url)
    if os.path.exists(filepath):
        os.remove(filepath)

    era_principal = foto.principal
    db.session.delete(foto)
    db.session.flush()

    if era_principal:
        proxima = Foto.query.filter_by(imovel_id=imovel.id).first()
        if proxima:
            proxima.principal = True

    db.session.commit()
    return {"ok": True}, 200

# ── CONFIGURAÇÕES GERAIS ──────────────────────────────────────────────────────

@admin_bp.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    from ..models import Imobiliaria
    imob = Imobiliaria.query.get(current_user.imobiliaria_id)
    if request.method == 'POST':
        imob.email_contato      = request.form.get('email_contato', '').strip() or None
        imob.email_exibicao     = request.form.get('email_exibicao', '').strip() or None
        imob.telefone           = request.form.get('telefone', '').strip() or None
        imob.slogan             = request.form.get('slogan', '').strip() or None
        imob.ordenacao_imoveis  = request.form.get('ordenacao_imoveis', 'recentes')
        imob.imoveis_por_pagina = int(request.form.get('imoveis_por_pagina') or 9)
        db.session.commit()
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('admin.configuracoes'))
    return render_template('admin/configuracoes.html', imob=imob)

# ── MEU SITE ──────────────────────────────────────────────────────────────────

@admin_bp.route('/meusite')
@login_required
def meusite():
    from ..models import Imobiliaria
    imobiliaria = Imobiliaria.query.get(current_user.imobiliaria_id)
    banners     = BannerSite.query.filter_by(imobiliaria_id=current_user.imobiliaria_id)\
                                  .order_by(BannerSite.ordem).all()
    return render_template('admin/meusite.html', imobiliaria=imobiliaria,
                           banners=banners, temas=TEMAS,
                           tab=request.args.get('tab', 'tema'))

@admin_bp.route('/meusite/layout', methods=['POST'])
@login_required
def salvar_layout():
    from ..models import Imobiliaria
    imob = Imobiliaria.query.get(current_user.imobiliaria_id)
    imob.layout_banner = request.form.get('layout_banner', 'fullscreen')
    imob.layout_busca  = request.form.get('layout_busca',  'abaixo')
    imob.layout_grid   = request.form.get('layout_grid',   '3')
    imob.layout_logo   = request.form.get('layout_logo',   'esquerda')
    db.session.commit()
    flash('Layout atualizado com sucesso!', 'success')
    return redirect(url_for('admin.meusite', tab='layout'))

@admin_bp.route('/meusite/tema', methods=['POST'])
@login_required
def salvar_tema():
    from ..models import Imobiliaria
    imob = Imobiliaria.query.get(current_user.imobiliaria_id)
    imob.tema_ativo = request.form.get('tema_id', 'clean')
    db.session.commit()
    flash('Tema atualizado com sucesso!', 'success')
    return redirect(url_for('admin.meusite', tab='tema'))

@admin_bp.route('/meusite/identidade', methods=['POST'])
@login_required
def salvar_identidade():
    from ..models import Imobiliaria
    imob    = Imobiliaria.query.get(current_user.imobiliaria_id)
    arquivo = request.files.get('logo')
    imob.whatsapp = request.form.get('whatsapp', '').strip() or None

    if arquivo and arquivo.filename:
        ext  = os.path.splitext(arquivo.filename)[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.svg'):
            flash('Formato de logo inválido. Use JPG, PNG, WEBP ou SVG.', 'danger')
            return redirect(url_for('admin.meusite', tab='identidade'))
        logo_dir = os.path.join('app', 'static', 'uploads', str(imob.id), 'logo')
        os.makedirs(logo_dir, exist_ok=True)
        filename = f"logo{ext}"
        arquivo.save(os.path.join(logo_dir, filename))
        imob.logo_url = f"uploads/{imob.id}/logo/{filename}"

    db.session.commit()
    flash('Identidade salva com sucesso!', 'success')
    return redirect(url_for('admin.meusite', tab='identidade'))

@admin_bp.route('/meusite/banners/novo', methods=['POST'])
@login_required
def novo_banner():
    arquivo = request.files.get('imagem')
    if not arquivo or not arquivo.filename:
        flash('Selecione uma imagem para o banner.', 'warning')
        return redirect(url_for('admin.meusite', tab='banners'))

    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        flash('Formato inválido. Use JPG, PNG ou WEBP.', 'danger')
        return redirect(url_for('admin.meusite', tab='banners'))

    banner_dir = os.path.join('app', 'static', 'uploads',
                              str(current_user.imobiliaria_id), 'banners')
    os.makedirs(banner_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    arquivo.save(os.path.join(banner_dir, filename))

    maior_ordem = db.session.query(db.func.max(BannerSite.ordem))\
                             .filter_by(imobiliaria_id=current_user.imobiliaria_id).scalar() or 0
    banner = BannerSite(
        imobiliaria_id=current_user.imobiliaria_id,
        url_imagem=f"uploads/{current_user.imobiliaria_id}/banners/{filename}",
        titulo=request.form.get('titulo', '').strip() or None,
        subtitulo=request.form.get('subtitulo', '').strip() or None,
        ordem=maior_ordem + 1
    )
    db.session.add(banner)
    db.session.commit()
    flash('Banner adicionado!', 'success')
    return redirect(url_for('admin.meusite', tab='banners'))

@admin_bp.route('/meusite/banners/excluir/<int:banner_id>', methods=['POST'])
@login_required
def excluir_banner(banner_id):
    banner = BannerSite.query.filter_by(id=banner_id,
                                         imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    filepath = os.path.join('app', 'static', banner.url_imagem)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(banner)
    db.session.commit()
    flash('Banner removido.', 'success')
    return redirect(url_for('admin.meusite', tab='banners'))

# ── UPLOAD TEMP ───────────────────────────────────────────────────────────────

@admin_bp.route('/imoveis/upload-temp', methods=['POST'])
@login_required
def upload_temp_fotos():
    file = request.files['fotos']
    session_id = session.get('upload_session_id')
    temp_path = os.path.join('app', 'static', 'uploads', 'temp', session_id)
    os.makedirs(temp_path, exist_ok=True)
    filename = f"{uuid.uuid4()}_{file.filename}"
    file.save(os.path.join(temp_path, filename))
    return {"status": "success"}, 200

# ── CONFIGURAR PÁGINAS ────────────────────────────────────────────────────────

# Páginas institucionais pré-definidas (criadas automaticamente se não existirem)
PAGINAS_INSTITUCIONAIS = [
    {'slug': 'sobre',       'titulo': 'Sobre a Imobiliária',    'ordem': 1},
    {'slug': 'privacidade', 'titulo': 'Política de Privacidade','ordem': 2},
    {'slug': 'contato',     'titulo': 'Fale Conosco',           'ordem': 3},
]

def _garantir_paginas_institucionais(imob_id):
    """Cria as páginas institucionais da imobiliária se ainda não existirem."""
    from ..models import PaginaSite
    for p in PAGINAS_INSTITUCIONAIS:
        existe = PaginaSite.query.filter_by(imobiliaria_id=imob_id,
                                            tipo='institucional',
                                            slug=p['slug']).first()
        if not existe:
            db.session.add(PaginaSite(
                imobiliaria_id=imob_id,
                tipo='institucional',
                slug=p['slug'],
                titulo=p['titulo'],
                conteudo='',
                ativo=False,
                no_menu=False,
                ordem=p['ordem'],
            ))
    db.session.commit()


@admin_bp.route('/paginas')
@login_required
def paginas():
    from ..models import PaginaSite, MenuLink
    imob_id = current_user.imobiliaria_id
    _garantir_paginas_institucionais(imob_id)
    institucionais = PaginaSite.query.filter_by(imobiliaria_id=imob_id, tipo='institucional')\
                                     .order_by(PaginaSite.ordem).all()
    extras         = PaginaSite.query.filter_by(imobiliaria_id=imob_id, tipo='custom')\
                                     .order_by(PaginaSite.ordem).all()
    links_menu     = MenuLink.query.filter_by(imobiliaria_id=imob_id)\
                                   .order_by(MenuLink.ordem).all()
    return render_template('admin/paginas.html',
                           institucionais=institucionais,
                           extras=extras,
                           links_menu=links_menu,
                           tab=request.args.get('tab', 'institucionais'))


@admin_bp.route('/paginas/institucional/<slug>', methods=['GET', 'POST'])
@login_required
def editar_pagina_institucional(slug):
    from ..models import PaginaSite
    imob_id = current_user.imobiliaria_id
    _garantir_paginas_institucionais(imob_id)
    pagina = PaginaSite.query.filter_by(imobiliaria_id=imob_id,
                                        tipo='institucional', slug=slug).first_or_404()
    if request.method == 'POST':
        pagina.titulo   = request.form.get('titulo', pagina.titulo).strip()
        pagina.conteudo = request.form.get('conteudo', '').strip()
        pagina.ativo    = 'ativo' in request.form
        pagina.no_menu  = 'no_menu' in request.form
        db.session.commit()
        flash('Página salva com sucesso!', 'success')
        return redirect(url_for('admin.paginas', tab='institucionais'))
    return render_template('admin/editar_pagina.html', pagina=pagina,
                           back_tab='institucionais')


@admin_bp.route('/paginas/extra/nova', methods=['POST'])
@login_required
def nova_pagina_extra():
    from ..models import PaginaSite
    import re
    titulo = request.form.get('titulo', '').strip()
    if not titulo:
        flash('Informe um título para a página.', 'warning')
        return redirect(url_for('admin.paginas', tab='extras'))
    # Gera slug a partir do título
    slug = re.sub(r'[^a-z0-9]+', '-', titulo.lower()).strip('-')
    # Garante unicidade do slug
    base_slug = slug
    counter   = 1
    while PaginaSite.query.filter_by(imobiliaria_id=current_user.imobiliaria_id,
                                     slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    maior_ordem = db.session.query(db.func.max(PaginaSite.ordem))\
                             .filter_by(imobiliaria_id=current_user.imobiliaria_id,
                                        tipo='custom').scalar() or 0
    pagina = PaginaSite(
        imobiliaria_id=current_user.imobiliaria_id,
        tipo='custom',
        slug=slug,
        titulo=titulo,
        conteudo='',
        ativo=True,
        no_menu=False,
        ordem=maior_ordem + 1,
    )
    db.session.add(pagina)
    db.session.commit()
    flash('Página criada! Edite o conteúdo abaixo.', 'success')
    return redirect(url_for('admin.editar_pagina_extra', id=pagina.id))


@admin_bp.route('/paginas/extra/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_pagina_extra(id):
    from ..models import PaginaSite
    pagina = PaginaSite.query.filter_by(id=id,
                                        imobiliaria_id=current_user.imobiliaria_id,
                                        tipo='custom').first_or_404()
    if request.method == 'POST':
        pagina.titulo   = request.form.get('titulo', pagina.titulo).strip()
        pagina.conteudo = request.form.get('conteudo', '').strip()
        pagina.ativo    = 'ativo' in request.form
        pagina.no_menu  = 'no_menu' in request.form
        db.session.commit()
        flash('Página salva com sucesso!', 'success')
        return redirect(url_for('admin.paginas', tab='extras'))
    return render_template('admin/editar_pagina.html', pagina=pagina,
                           back_tab='extras')


@admin_bp.route('/paginas/extra/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_pagina_extra(id):
    from ..models import PaginaSite
    pagina = PaginaSite.query.filter_by(id=id,
                                        imobiliaria_id=current_user.imobiliaria_id,
                                        tipo='custom').first_or_404()
    db.session.delete(pagina)
    db.session.commit()
    flash('Página excluída.', 'success')
    return redirect(url_for('admin.paginas', tab='extras'))


@admin_bp.route('/paginas/menu/novo', methods=['POST'])
@login_required
def novo_menu_link():
    from ..models import MenuLink
    label = request.form.get('label', '').strip()
    url   = request.form.get('url',   '').strip()
    if not label or not url:
        flash('Preencha o nome e o URL do link.', 'warning')
        return redirect(url_for('admin.paginas', tab='menu'))
    maior_ordem = db.session.query(db.func.max(MenuLink.ordem))\
                             .filter_by(imobiliaria_id=current_user.imobiliaria_id).scalar() or 0
    link = MenuLink(
        imobiliaria_id=current_user.imobiliaria_id,
        label=label,
        url=url,
        abre_nova_aba='abre_nova_aba' in request.form,
        ordem=maior_ordem + 1,
        ativo=True,
    )
    db.session.add(link)
    db.session.commit()
    flash('Link adicionado ao menu!', 'success')
    return redirect(url_for('admin.paginas', tab='menu'))


@admin_bp.route('/paginas/menu/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_menu_link(id):
    from ..models import MenuLink
    link = MenuLink.query.filter_by(id=id,
                                    imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash('Link removido do menu.', 'success')
    return redirect(url_for('admin.paginas', tab='menu'))


@admin_bp.route('/paginas/menu/toggle/<int:id>', methods=['POST'])
@login_required
def toggle_menu_link(id):
    from ..models import MenuLink
    link = MenuLink.query.filter_by(id=id,
                                    imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    link.ativo = not link.ativo
    db.session.commit()
    return redirect(url_for('admin.paginas', tab='menu'))


# ── SENHA PRÓPRIA ────────────────────────────────────────────────────────────

@admin_bp.route('/alterar-senha', methods=['POST'])
@login_required
def alterar_propria_senha():
    senha_atual   = request.form.get('senha_atual',    '').strip()
    nova_senha    = request.form.get('nova_senha',     '').strip()
    confirmar     = request.form.get('confirmar_senha','').strip()

    if not current_user.check_senha(senha_atual):
        flash('Senha atual incorreta.', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))
    if len(nova_senha) < 6:
        flash('A nova senha deve ter ao menos 6 caracteres.', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))
    if nova_senha != confirmar:
        flash('A confirmação da senha não confere.', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))

    current_user.set_senha(nova_senha)
    db.session.commit()
    flash('Senha alterada com sucesso.', 'success')
    return redirect(request.referrer or url_for('admin.dashboard'))


# ── GESTÃO DE USUÁRIOS ────────────────────────────────────────────────────────

@admin_bp.route('/usuarios')
@login_required
def usuarios():
    from ..models import Usuario
    equipe = Usuario.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).all()
    return render_template('admin/usuarios.html', equipe=equipe)


@admin_bp.route('/usuarios/novo', methods=['POST'])
@login_required
def novo_usuario():
    from ..models import Usuario
    nome  = request.form.get('nome',  '').strip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '').strip()

    if not nome or not email or not senha:
        flash('Preencha nome, e-mail e senha.', 'danger')
        return redirect(url_for('admin.usuarios'))
    if len(senha) < 6:
        flash('A senha deve ter ao menos 6 caracteres.', 'danger')
        return redirect(url_for('admin.usuarios'))
    if Usuario.query.filter_by(email=email).first():
        flash(f'O e-mail "{email}" já está cadastrado.', 'danger')
        return redirect(url_for('admin.usuarios'))

    u = Usuario(nome=nome, email=email, imobiliaria_id=current_user.imobiliaria_id)
    u.set_senha(senha)
    db.session.add(u)
    db.session.commit()
    flash(f'Usuário "{nome}" criado com sucesso.', 'success')
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:id>/editar', methods=['POST'])
@login_required
def editar_usuario(id):
    from ..models import Usuario
    u = Usuario.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    nome  = request.form.get('nome',  '').strip()
    email = request.form.get('email', '').strip().lower()

    if not nome or not email:
        flash('Nome e e-mail são obrigatórios.', 'danger')
        return redirect(url_for('admin.usuarios'))

    conflito = Usuario.query.filter(Usuario.email == email, Usuario.id != id).first()
    if conflito:
        flash(f'O e-mail "{email}" já está em uso por outro usuário.', 'danger')
        return redirect(url_for('admin.usuarios'))

    u.nome  = nome
    u.email = email
    db.session.commit()
    flash('Usuário atualizado.', 'success')
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:id>/reset-senha', methods=['POST'])
@login_required
def reset_senha_usuario(id):
    from ..models import Usuario
    u = Usuario.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    senha = request.form.get('nova_senha', '').strip()
    if len(senha) < 6:
        flash('A nova senha deve ter ao menos 6 caracteres.', 'danger')
        return redirect(url_for('admin.usuarios'))
    u.set_senha(senha)
    db.session.commit()
    flash(f'Senha de "{u.nome}" redefinida.', 'success')
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_usuario(id):
    from ..models import Usuario
    u = Usuario.query.filter_by(id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()

    if u.id == current_user.id:
        flash('Você não pode excluir seu próprio usuário.', 'danger')
        return redirect(url_for('admin.usuarios'))

    total = Usuario.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).count()
    if total <= 1:
        flash('Não é possível excluir o único usuário da imobiliária.', 'danger')
        return redirect(url_for('admin.usuarios'))

    nome = u.nome
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuário "{nome}" excluído.', 'success')
    return redirect(url_for('admin.usuarios'))