import uuid, re, os
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, current_user
from ..models import SuperAdmin, Imobiliaria, Usuario, TipoImovel, db

superadmin_bp = Blueprint('superadmin', __name__)

# Chave interna → dados de exibição e limites
PLANOS_CONFIG = {
    'basic': {
        'label':       'Basic',
        'preco':       49.90,
        'imoveis_max': 30,
        'fotos_max':   35,
        'usuarios_max':1,
        'ia_creditos': 5,
        'chatbot':     False,
        'ssl':         False,
        'esteira':     False,
    },
    'standard': {
        'label':       'Standard',
        'preco':       69.90,
        'imoveis_max': 350,
        'fotos_max':   50,
        'usuarios_max':3,
        'ia_creditos': 10,
        'chatbot':     False,
        'ssl':         True,
        'esteira':     True,
    },
    'profissional': {
        'label':       'Profissional',
        'preco':       109.90,
        'imoveis_max': 1000,
        'fotos_max':   65,
        'usuarios_max':5,
        'ia_creditos': 15,
        'chatbot':     True,
        'ssl':         True,
        'esteira':     True,
    },
    'plus': {
        'label':       'Plus',
        'preco':       239.90,
        'imoveis_max': 3000,
        'fotos_max':   65,
        'usuarios_max':15,
        'ia_creditos': 50,
        'chatbot':     True,
        'ssl':         True,
        'esteira':     True,
    },
}

PLANOS = list(PLANOS_CONFIG.keys())


def _gerar_slug(nome, excluir_id=None):
    """Gera slug único a partir do nome da imobiliária (sem acentos)."""
    import unicodedata
    normalizado = unicodedata.normalize('NFD', nome)
    sem_acentos = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    base = re.sub(r'[^a-z0-9]+', '-', sem_acentos.lower()).strip('-') or 'imob'
    slug = base
    contador = 1
    while True:
        q = Imobiliaria.query.filter_by(slug=slug)
        if excluir_id:
            q = q.filter(Imobiliaria.id != excluir_id)
        if not q.first():
            break
        slug = f"{base}-{contador}"
        contador += 1
    return slug


def _url_subdominio(slug):
    base = current_app.config.get('BASE_DOMAIN', '').strip()
    if base and slug:
        return f"http://{slug}.{base}"
    return None


def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
            return redirect(url_for('superadmin.login'))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN / LOGOUT ────────────────────────────────────────────────────────────

@superadmin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and getattr(current_user, 'is_superadmin', False):
        return redirect(url_for('superadmin.dashboard'))

    if request.method == 'POST':
        sa = SuperAdmin.query.filter_by(email=request.form.get('email')).first()
        if sa and sa.check_senha(request.form.get('senha')):
            login_user(sa)
            return redirect(url_for('superadmin.dashboard'))
        flash('E-mail ou senha incorretos.', 'danger')

    return render_template('superadmin/login.html')


@superadmin_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('superadmin.login'))


@superadmin_bp.route('/alterar-senha', methods=['POST'])
@superadmin_required
def alterar_propria_senha():
    senha_atual = request.form.get('senha_atual',    '').strip()
    nova_senha  = request.form.get('nova_senha',     '').strip()
    confirmar   = request.form.get('confirmar_senha','').strip()

    if not current_user.check_senha(senha_atual):
        flash('Senha atual incorreta.', 'danger')
        return redirect(request.referrer or url_for('superadmin.dashboard'))
    if len(nova_senha) < 6:
        flash('A nova senha deve ter ao menos 6 caracteres.', 'danger')
        return redirect(request.referrer or url_for('superadmin.dashboard'))
    if nova_senha != confirmar:
        flash('A confirmação da senha não confere.', 'danger')
        return redirect(request.referrer or url_for('superadmin.dashboard'))

    current_user.set_senha(nova_senha)
    db.session.commit()
    flash('Senha alterada com sucesso.', 'success')
    return redirect(request.referrer or url_for('superadmin.dashboard'))


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@superadmin_bp.route('/painel')
def painel():
    """Alias amigável para o dashboard master (localhost:5000/superadmin/painel)."""
    return redirect(url_for('superadmin.dashboard'))


@superadmin_bp.route('/')
@superadmin_required
def dashboard():
    from ..models import Lead, Imovel
    total_imobs   = Imobiliaria.query.count()
    imobs_ativas  = Imobiliaria.query.filter_by(ativo=True).count()
    imobs_inativas= Imobiliaria.query.filter_by(ativo=False).count()
    total_imoveis = Imovel.query.count()
    total_leads   = Lead.query.count()

    imobiliarias = Imobiliaria.query.order_by(Imobiliaria.criado_em.desc()).all()

    # Stats por imobiliária
    stats = {}
    for imob in imobiliarias:
        stats[imob.id] = {
            'imoveis': Imovel.query.filter_by(imobiliaria_id=imob.id).count(),
            'leads':   Lead.query.filter_by(imobiliaria_id=imob.id).count(),
            'usuarios':Usuario.query.filter_by(imobiliaria_id=imob.id).count(),
        }

    base_domain = current_app.config.get('BASE_DOMAIN', '')

    return render_template('superadmin/dashboard.html',
                           total_imobs=total_imobs,
                           imobs_ativas=imobs_ativas,
                           imobs_inativas=imobs_inativas,
                           total_imoveis=total_imoveis,
                           total_leads=total_leads,
                           imobiliarias=imobiliarias,
                           stats=stats,
                           base_domain=base_domain)


# ── CRIAR NOVA IMOBILIÁRIA ────────────────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/nova', methods=['GET', 'POST'])
@superadmin_required
def nova_imobiliaria():
    if request.method == 'POST':
        nome      = request.form.get('nome', '').strip()
        dominio   = request.form.get('dominio', '').strip().lower()
        plano     = request.form.get('plano', 'basico')
        adm_nome  = request.form.get('adm_nome', '').strip()
        adm_email = request.form.get('adm_email', '').strip().lower()
        adm_senha = request.form.get('adm_senha', '').strip()

        erros = []
        if not nome:           erros.append('Informe o nome da imobiliária.')
        if not adm_nome:       erros.append('Informe o nome do administrador.')
        if not adm_email:      erros.append('Informe o e-mail do administrador.')
        if len(adm_senha) < 6: erros.append('A senha deve ter ao menos 6 caracteres.')
        if Usuario.query.filter_by(email=adm_email).first():
            erros.append(f'O e-mail "{adm_email}" já está cadastrado.')

        # Gera slug a partir do campo ou do nome
        slug_val = request.form.get('slug', '').strip().lower() or _gerar_slug(nome)
        slug_val = re.sub(r'[^a-z0-9-]+', '-', slug_val).strip('-') or _gerar_slug(nome)
        if Imobiliaria.query.filter_by(slug=slug_val).first():
            erros.append(f'O slug "{slug_val}" já está em uso.')

        dominio_personalizado = request.form.get('dominio_personalizado', '').strip().lower() or None

        if erros:
            for e in erros:
                flash(e, 'danger')
            return render_template('superadmin/form_imobiliaria.html',
                                   planos=PLANOS, form=request.form, editando=False,
                                   base_domain=current_app.config.get('BASE_DOMAIN', ''))

        # Campo legado 'dominio': usa dominio_personalizado ou slug (garante unicidade)
        dominio_legado = dominio_personalizado or slug_val

        imob = Imobiliaria(
            nome=nome,
            dominio=dominio_legado,
            slug=slug_val,
            dominio_personalizado=dominio_personalizado,
            api_token=str(uuid.uuid4()).replace('-', ''),
            plano=plano,
            ativo=True,
        )
        db.session.add(imob)
        db.session.flush()  # obtém imob.id

        # Tipos de imóvel padrão para toda imobiliária nova
        _TIPOS_PADRAO = [
            ('Apartamento',    'AP'),
            ('Casa',           'CA'),
            ('Casa em Condomínio', 'CC'),
            ('Terreno',        'TE'),
            ('Sala Comercial', 'SC'),
            ('Loja',           'LJ'),
            ('Galpão',         'GA'),
            ('Flat',           'FL'),
            ('Cobertura',      'CB'),
            ('Kitnet',         'KI'),
        ]
        for nome_tipo, prefixo in _TIPOS_PADRAO:
            db.session.add(TipoImovel(
                imobiliaria_id=imob.id,
                nome=nome_tipo,
                prefixo=prefixo,
            ))

        usuario = Usuario(
            imobiliaria_id=imob.id,
            nome=adm_nome,
            email=adm_email,
        )
        usuario.set_senha(adm_senha)
        db.session.add(usuario)
        db.session.commit()

        flash(f'Imobiliária "{nome}" criada com sucesso!', 'success')
        return redirect(url_for('superadmin.dashboard'))

    return render_template('superadmin/form_imobiliaria.html',
                           planos=PLANOS, form={}, editando=False,
                           base_domain=current_app.config.get('BASE_DOMAIN',''))


# ── EDITAR IMOBILIÁRIA ────────────────────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/<int:id>/editar', methods=['GET', 'POST'])
@superadmin_required
def editar_imobiliaria(id):
    imob = Imobiliaria.query.get_or_404(id)

    if request.method == 'POST':
        novo_dominio = request.form.get('dominio', '').strip().lower()
        conflito = Imobiliaria.query.filter(
            Imobiliaria.dominio == novo_dominio,
            Imobiliaria.id != id
        ).first()
        if conflito:
            flash(f'O domínio "{novo_dominio}" já está em uso por outra imobiliária.', 'danger')
            return render_template('superadmin/form_imobiliaria.html',
                                   planos=PLANOS, form=request.form,
                                   imob=imob, editando=True)

        novo_slug = request.form.get('slug', '').strip().lower()
        novo_slug = re.sub(r'[^a-z0-9-]+', '-', novo_slug).strip('-') or _gerar_slug(imob.nome, excluir_id=id)
        conflito_slug = Imobiliaria.query.filter(
            Imobiliaria.slug == novo_slug, Imobiliaria.id != id
        ).first()
        if conflito_slug:
            flash(f'O slug "{novo_slug}" já está em uso.', 'danger')
            return render_template('superadmin/form_imobiliaria.html',
                                   planos=PLANOS, form=request.form, imob=imob, editando=True,
                                   base_domain=current_app.config.get('BASE_DOMAIN',''))

        imob.nome                 = request.form.get('nome', '').strip()
        imob.dominio              = novo_dominio
        imob.slug                 = novo_slug
        imob.dominio_personalizado= request.form.get('dominio_personalizado','').strip().lower() or None
        imob.plano                = request.form.get('plano', 'basico')
        db.session.commit()
        flash('Imobiliária atualizada!', 'success')
        return redirect(url_for('superadmin.dashboard'))

    return render_template('superadmin/form_imobiliaria.html',
                           planos=PLANOS, form=imob, imob=imob, editando=True,
                           base_domain=current_app.config.get('BASE_DOMAIN',''))


# ── TOGGLE ATIVO/INATIVO ──────────────────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/<int:id>/toggle', methods=['POST'])
@superadmin_required
def toggle_imobiliaria(id):
    imob = Imobiliaria.query.get_or_404(id)
    imob.ativo = not imob.ativo
    db.session.commit()
    estado = 'ativada' if imob.ativo else 'desativada'
    flash(f'Imobiliária "{imob.nome}" {estado}.', 'success')
    return redirect(url_for('superadmin.dashboard'))


# ── GERENCIAR DOMÍNIOS DA IMOBILIÁRIA ────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/<int:id>/dominios', methods=['GET', 'POST'])
@superadmin_required
def dominios_imobiliaria(id):
    imob = Imobiliaria.query.get_or_404(id)
    base_domain = current_app.config.get('BASE_DOMAIN', '')

    if request.method == 'POST':
        novo_slug = request.form.get('slug', '').strip().lower()
        novo_slug = re.sub(r'[^a-z0-9-]+', '-', novo_slug).strip('-')
        dominio_personalizado = request.form.get('dominio_personalizado', '').strip().lower() or None

        if novo_slug:
            conflito = Imobiliaria.query.filter(
                Imobiliaria.slug == novo_slug, Imobiliaria.id != id
            ).first()
            if conflito:
                flash(f'O slug "{novo_slug}" já está em uso por outra imobiliária.', 'danger')
                return render_template('superadmin/dominios.html', imob=imob, base_domain=base_domain)

        imob.slug                  = novo_slug or None
        imob.dominio_personalizado = dominio_personalizado
        db.session.commit()
        flash('Domínios atualizados com sucesso!', 'success')
        return redirect(url_for('superadmin.dominios_imobiliaria', id=id))

    return render_template('superadmin/dominios.html', imob=imob, base_domain=base_domain)


# ── GERENCIAR USUÁRIOS DA IMOBILIÁRIA ─────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/<int:id>/usuarios')
@superadmin_required
def usuarios_imobiliaria(id):
    imob     = Imobiliaria.query.get_or_404(id)
    usuarios = Usuario.query.filter_by(imobiliaria_id=id).all()
    return render_template('superadmin/usuarios.html', imob=imob, usuarios=usuarios)


@superadmin_bp.route('/imobiliarias/<int:id>/usuarios/novo', methods=['POST'])
@superadmin_required
def novo_usuario_imobiliaria(id):
    imob  = Imobiliaria.query.get_or_404(id)
    nome  = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '').strip()

    if not nome or not email or len(senha) < 6:
        flash('Preencha nome, e-mail e senha (mínimo 6 caracteres).', 'danger')
        return redirect(url_for('superadmin.usuarios_imobiliaria', id=id))

    if Usuario.query.filter_by(email=email).first():
        flash(f'E-mail "{email}" já cadastrado.', 'danger')
        return redirect(url_for('superadmin.usuarios_imobiliaria', id=id))

    u = Usuario(imobiliaria_id=id, nome=nome, email=email)
    u.set_senha(senha)
    db.session.add(u)
    db.session.commit()
    flash(f'Usuário "{nome}" criado com sucesso!', 'success')
    return redirect(url_for('superadmin.usuarios_imobiliaria', id=id))


@superadmin_bp.route('/imobiliarias/<int:imob_id>/usuarios/<int:user_id>/excluir', methods=['POST'])
@superadmin_required
def excluir_usuario_imobiliaria(imob_id, user_id):
    usuario = Usuario.query.filter_by(id=user_id, imobiliaria_id=imob_id).first_or_404()
    # Não permite excluir o último usuário
    total = Usuario.query.filter_by(imobiliaria_id=imob_id).count()
    if total <= 1:
        flash('Não é possível excluir o único usuário desta imobiliária.', 'danger')
        return redirect(url_for('superadmin.usuarios_imobiliaria', id=imob_id))
    nome = usuario.nome
    db.session.delete(usuario)
    db.session.commit()
    flash(f'Usuário "{nome}" excluído.', 'success')
    return redirect(url_for('superadmin.usuarios_imobiliaria', id=imob_id))


# ── CONFIGURAÇÕES DA PLATAFORMA (.env) ───────────────────────────────────────

def _env_path():
    return os.path.join(current_app.root_path, '..', '.env')


def _ler_env():
    """Lê o .env e retorna dict {chave: valor} e lista de linhas originais."""
    path = _env_path()
    linhas = []
    valores = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
        for linha in linhas:
            linha_strip = linha.strip()
            if linha_strip and not linha_strip.startswith('#'):
                if '=' in linha_strip:
                    k, _, v = linha_strip.partition('=')
                    valores[k.strip()] = v.strip()
    return valores, linhas


def _salvar_env(novos_valores: dict):
    """
    Atualiza ou acrescenta chaves no .env, preservando comentários e ordem.
    Chaves com valor None ou '' são escritas como KEY= (preservam a chave).
    """
    path = _env_path()
    _, linhas = _ler_env()

    pendentes = set(novos_valores.keys())

    novas_linhas = []
    for linha in linhas:
        stripped = linha.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            k = stripped.split('=', 1)[0].strip()
            if k in novos_valores:
                v = novos_valores[k] or ''
                novas_linhas.append(f'{k}={v}\n')
                pendentes.discard(k)
                continue
        novas_linhas.append(linha)

    # Acrescenta chaves novas que não existiam no arquivo
    if pendentes:
        novas_linhas.append('\n')
        for k in sorted(pendentes):
            v = novos_valores[k] or ''
            novas_linhas.append(f'{k}={v}\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(novas_linhas)


@superadmin_bp.route('/configuracoes', methods=['GET', 'POST'])
@superadmin_required
def configuracoes_plataforma():
    env_path = _env_path()
    env_existe = os.path.exists(env_path)
    valores, _ = _ler_env()

    if request.method == 'POST':
        acao = request.form.get('_acao', 'salvar')

        if acao == 'testar_smtp':
            _testar_smtp(valores)
            return redirect(url_for('superadmin.configuracoes_plataforma'))

        # Monta dict com todos os campos do formulário
        campos = {
            # Geral
            'SECRET_KEY':    request.form.get('SECRET_KEY', '').strip(),
            'DATABASE_URL':  request.form.get('DATABASE_URL', '').strip(),
            'FLASK_DEBUG':   request.form.get('FLASK_DEBUG', 'false'),
            # Plataforma / Domínios
            'BASE_DOMAIN':   request.form.get('BASE_DOMAIN', '').strip().lower().lstrip('.'),
            'FLASK_HOST':    request.form.get('FLASK_HOST', '').strip(),
            'FLASK_PORT':    request.form.get('FLASK_PORT', '').strip(),
            # SMTP
            'MAIL_SERVER':         request.form.get('MAIL_SERVER', '').strip(),
            'MAIL_PORT':           request.form.get('MAIL_PORT', '587').strip(),
            'MAIL_USE_TLS':        request.form.get('MAIL_USE_TLS', 'false'),
            'MAIL_USE_SSL':        request.form.get('MAIL_USE_SSL', 'false'),
            'MAIL_USERNAME':       request.form.get('MAIL_USERNAME', '').strip(),
            'MAIL_DEFAULT_SENDER': request.form.get('MAIL_DEFAULT_SENDER', '').strip(),
        }

        # Senha SMTP: só sobrescreve se o usuário digitou algo
        nova_senha = request.form.get('MAIL_PASSWORD', '').strip()
        if nova_senha:
            campos['MAIL_PASSWORD'] = nova_senha
        elif 'MAIL_PASSWORD' in valores:
            campos['MAIL_PASSWORD'] = valores['MAIL_PASSWORD']  # mantém a atual

        # SECRET_KEY: não pode ficar vazio
        if not campos['SECRET_KEY']:
            flash('SECRET_KEY não pode ser vazia.', 'danger')
            return redirect(url_for('superadmin.configuracoes_plataforma'))

        _salvar_env(campos)

        # Atualiza a config em memória para refletir imediatamente sem restart
        current_app.config['BASE_DOMAIN'] = campos['BASE_DOMAIN'].strip().lower().lstrip('.')
        current_app.config['MAIL_SERVER']  = campos['MAIL_SERVER']
        current_app.config['MAIL_PORT']    = int(campos['MAIL_PORT'] or 587)
        current_app.config['MAIL_USE_TLS'] = campos['MAIL_USE_TLS'].lower() == 'true'
        current_app.config['MAIL_USE_SSL'] = campos['MAIL_USE_SSL'].lower() == 'true'
        current_app.config['MAIL_USERNAME'] = campos['MAIL_USERNAME']
        current_app.config['MAIL_DEFAULT_SENDER'] = campos['MAIL_DEFAULT_SENDER'] or campos['MAIL_USERNAME']
        if nova_senha:
            current_app.config['MAIL_PASSWORD'] = nova_senha

        flash('Configurações salvas com sucesso! Reinicie o servidor para que todas as alterações sejam aplicadas.', 'success')
        return redirect(url_for('superadmin.configuracoes_plataforma'))

    # Recarrega valores após POST
    valores, _ = _ler_env()
    return render_template('superadmin/configuracoes.html',
                           env=valores,
                           env_existe=env_existe,
                           env_path=os.path.abspath(env_path))


@superadmin_bp.route('/configuracoes/testar-smtp', methods=['POST'])
@superadmin_required
def testar_smtp():
    valores, _ = _ler_env()
    _testar_smtp(valores)
    return redirect(url_for('superadmin.configuracoes_plataforma'))


def _testar_smtp(env_valores):
    """Tenta enviar um e-mail de teste com as configurações atuais."""
    from flask_mail import Message
    from .. import mail

    username = env_valores.get('MAIL_USERNAME', '').strip()
    if not username:
        flash('Configure o MAIL_USERNAME antes de testar.', 'warning')
        return

    destinatario = current_user.email if hasattr(current_user, 'email') else username
    try:
        msg = Message(
            subject='ImobiConectaJa — Teste de SMTP',
            sender=(current_app.config.get('MAIL_DEFAULT_SENDER') or username),
            recipients=[destinatario],
            html=(
                '<h2>Teste de e-mail — ImobiConectaJa</h2>'
                '<p>Se você recebeu esta mensagem, as configurações SMTP estão corretas.</p>'
                '<p style="color:#888;font-size:.85rem;">Enviado pelo Painel Master</p>'
            ),
        )
        mail.send(msg)
        flash(f'E-mail de teste enviado para <strong>{destinatario}</strong> com sucesso!', 'success')
    except Exception as e:
        flash(f'Falha ao enviar e-mail de teste: {e}', 'danger')


# ── RESET DE SENHA DE USUÁRIO ─────────────────────────────────────────────────

@superadmin_bp.route('/imobiliarias/<int:imob_id>/usuarios/<int:user_id>/reset-senha', methods=['POST'])
@superadmin_required
def reset_senha_usuario(imob_id, user_id):
    usuario = Usuario.query.filter_by(id=user_id, imobiliaria_id=imob_id).first_or_404()
    nova    = request.form.get('nova_senha', '').strip()
    if len(nova) < 6:
        flash('A nova senha deve ter ao menos 6 caracteres.', 'danger')
        return redirect(url_for('superadmin.usuarios_imobiliaria', id=imob_id))
    usuario.set_senha(nova)
    db.session.commit()
    flash(f'Senha de "{usuario.nome}" redefinida.', 'success')
    return redirect(url_for('superadmin.usuarios_imobiliaria', id=imob_id))
