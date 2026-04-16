from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from flask_mail import Message
from datetime import datetime
from ..models import Lead, db
from .. import mail


def _perfil_busca(form):
    """Extrai campos do perfil de busca do form."""
    def _int(k):
        v = form.get(k, '').strip()
        return int(v) if v.isdigit() else None
    def _dec(k):
        import decimal
        v = form.get(k, '').strip().replace('.', '').replace(',', '.')
        try: return decimal.Decimal(v) if v else None
        except: return None
    return dict(
        interesse_finalidade  = form.get('interesse_finalidade', '').strip() or None,
        interesse_preco_min   = _dec('interesse_preco_min'),
        interesse_preco_max   = _dec('interesse_preco_max'),
        interesse_quartos_min = _int('interesse_quartos_min'),
        interesse_cidade      = form.get('interesse_cidade', '').strip() or None,
        interesse_bairros     = form.get('interesse_bairros', '').strip() or None,
    )

leads_bp = Blueprint('leads', __name__)


# ── Listagem ──────────────────────────────────────────────────────────────────

@leads_bp.route('/')
@login_required
def listar_leads():
    # Filtros via query string
    status_filtro = request.args.get('status', '')
    origem_filtro = request.args.get('origem', '')
    busca         = request.args.get('busca', '').strip()

    query = Lead.query.filter_by(imobiliaria_id=current_user.imobiliaria_id)

    if status_filtro:
        query = query.filter(Lead.status == status_filtro)
    if origem_filtro:
        query = query.filter(Lead.origem == origem_filtro)
    if busca:
        like = f"%{busca}%"
        query = query.filter(
            db.or_(
                Lead.nome.ilike(like),
                Lead.telefone.ilike(like),
                Lead.email.ilike(like)
            )
        )

    page       = request.args.get('page', 1, type=int)
    pagination = query.order_by(Lead.data_contato.desc()).paginate(page=page, per_page=15, error_out=False)
    leads      = pagination.items

    totais = {
        'total':       Lead.query.filter_by(imobiliaria_id=current_user.imobiliaria_id).count(),
        'novo':        Lead.query.filter_by(imobiliaria_id=current_user.imobiliaria_id, status='Novo').count(),
        'qualificado': Lead.query.filter_by(imobiliaria_id=current_user.imobiliaria_id, status='Qualificado').count(),
        'arquivado':   Lead.query.filter_by(imobiliaria_id=current_user.imobiliaria_id, status='Arquivado').count(),
    }

    return render_template(
        'admin/leads/listar_leads.html',
        leads=leads,
        pagination=pagination,
        totais=totais,
        status_filtro=status_filtro,
        origem_filtro=origem_filtro,
        busca=busca
    )


# ── Novo Lead (manual) ────────────────────────────────────────────────────────

@leads_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo_lead():
    if request.method == 'POST':
        try:
            pessoa_id = request.form.get('pessoa_id', type=int) or None
            lead = Lead(
                imobiliaria_id=current_user.imobiliaria_id,
                pessoa_id=pessoa_id,
                nome=request.form.get('nome', '').strip(),
                telefone=request.form.get('telefone', '').strip(),
                email=request.form.get('email', '').strip() or None,
                origem=request.form.get('origem', 'Manual'),
                status='Novo',
                mensagem=request.form.get('mensagem', '').strip() or None,
                data_contato=datetime.utcnow(),
                **_perfil_busca(request.form),
            )
            db.session.add(lead)
            db.session.commit()
            flash(f"Lead '{lead.nome}' cadastrado com sucesso!", "success")
            return redirect(url_for('leads.listar_leads'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao cadastrar lead: {e}", "danger")

    return render_template('admin/leads/form_leads.html', lead=None)


# ── Editar Lead ───────────────────────────────────────────────────────────────

@leads_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_lead(id):
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()

    if request.method == 'POST':
        try:
            lead.nome      = request.form.get('nome', '').strip()
            lead.telefone  = request.form.get('telefone', '').strip()
            lead.email     = request.form.get('email', '').strip() or None
            lead.origem    = request.form.get('origem', lead.origem)
            lead.status    = request.form.get('status', lead.status)
            lead.mensagem  = request.form.get('mensagem', '').strip() or None
            lead.pessoa_id = request.form.get('pessoa_id', type=int) or None
            for k, v in _perfil_busca(request.form).items():
                setattr(lead, k, v)
            db.session.commit()
            flash(f"Lead '{lead.nome}' atualizado com sucesso!", "success")
            return redirect(url_for('leads.listar_leads'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao atualizar: {e}", "danger")

    return render_template('admin/leads/form_leads.html', lead=lead)


# ── Ações Rápidas (AJAX ou redirect) ─────────────────────────────────────────

@leads_bp.route('/qualificar/<int:id>', methods=['POST'])
@login_required
def qualificar_lead(id):
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    lead.status = 'Qualificado'
    db.session.commit()
    if request.is_json:
        return jsonify({"ok": True, "status": lead.status})
    flash(f"Lead '{lead.nome}' qualificado!", "success")
    return redirect(url_for('leads.listar_leads'))


@leads_bp.route('/arquivar/<int:id>', methods=['POST'])
@login_required
def arquivar_lead(id):
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    lead.status = 'Arquivado'
    db.session.commit()
    if request.is_json:
        return jsonify({"ok": True, "status": lead.status})
    flash(f"Lead '{lead.nome}' arquivado.", "info")
    return redirect(url_for('leads.listar_leads'))


@leads_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_lead(id):
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()
    try:
        nome = lead.nome
        db.session.delete(lead)
        db.session.commit()
        flash(f"Lead '{nome}' excluído.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir: {e}", "danger")
    return redirect(url_for('leads.listar_leads'))


# ── CONVERTER LEAD → PESSOA ───────────────────────────────────────────────────

@leads_bp.route('/converter-para-pessoa/<int:id>', methods=['POST'])
@login_required
def converter_para_pessoa(id):
    from ..models import Pessoa, TelefonePessoa
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()

    if lead.pessoa_id:
        flash('Este lead já está vinculado a uma pessoa.', 'info')
        return redirect(url_for('leads.editar_lead', id=id))

    pessoa = Pessoa(
        imobiliaria_id=current_user.imobiliaria_id,
        tipo='Cliente',
        nome=lead.nome,
        email=lead.email or None,
    )
    db.session.add(pessoa)
    db.session.flush()

    if lead.telefone:
        db.session.add(TelefonePessoa(
            pessoa_id=pessoa.id, tipo='WhatsApp', numero=lead.telefone
        ))

    lead.pessoa_id = pessoa.id
    db.session.commit()
    flash(f'Lead convertido! Pessoa "{pessoa.nome}" criada e vinculada.', 'success')
    return redirect(url_for('pessoas.ver_pessoa', id=pessoa.id))


# ── IMÓVEIS COMPATÍVEIS COM PERFIL DE BUSCA (AJAX) ───────────────────────────

@leads_bp.route('/imoveis-compativeis/<int:id>')
@login_required
def imoveis_compativeis(id):
    from ..models import Imovel, Foto
    lead = Lead.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id).first_or_404()

    query = Imovel.query.filter_by(imobiliaria_id=current_user.imobiliaria_id)

    if lead.interesse_finalidade and lead.interesse_finalidade != 'Ambos':
        finalidade_map = {'Compra': 'Venda', 'Locação': 'Locação'}
        fin = finalidade_map.get(lead.interesse_finalidade)
        if fin:
            query = query.filter(
                db.or_(Imovel.finalidade == fin,
                        Imovel.finalidade == 'Venda e Locação')
            )

    if lead.interesse_preco_min:
        query = query.filter(Imovel.preco >= lead.interesse_preco_min)
    if lead.interesse_preco_max:
        query = query.filter(Imovel.preco <= lead.interesse_preco_max)
    if lead.interesse_quartos_min:
        query = query.filter(Imovel.quartos >= lead.interesse_quartos_min)
    if lead.interesse_cidade:
        query = query.filter(Imovel.cidade.ilike(f'%{lead.interesse_cidade}%'))

    imoveis = query.order_by(Imovel.destaque.desc(), Imovel.id.desc()).limit(6).all()

    resultado = []
    for im in imoveis:
        foto = next((f for f in im.fotos if f.principal), None) or (im.fotos[0] if im.fotos else None)
        resultado.append({
            'id': im.id,
            'titulo': im.titulo,
            'cidade': im.cidade or '',
            'bairro': im.bairro or '',
            'quartos': im.quartos,
            'preco': float(im.preco) if im.preco else 0,
            'finalidade': im.finalidade or '',
            'foto': foto.url if foto else None,
        })

    return jsonify(resultado)


# ── BUSCA DE LEADS PARA VÍNCULO COM PESSOA (AJAX) ────────────────────────────

@leads_bp.route('/buscar-para-vincular')
@login_required
def buscar_para_vincular():
    q        = request.args.get('q', '').strip()
    pessoa_id= request.args.get('pessoa_id', type=int)
    like     = f'%{q}%'
    # Retorna leads sem pessoa vinculada (ou já vinculados a esta pessoa)
    query = Lead.query.filter(
        Lead.imobiliaria_id == current_user.imobiliaria_id,
        db.or_(Lead.nome.ilike(like), Lead.telefone.ilike(like)),
        db.or_(Lead.pessoa_id == None, Lead.pessoa_id == pessoa_id)  # noqa: E711
    ).order_by(Lead.data_contato.desc()).limit(10)
    return jsonify([
        {'id': l.id, 'nome': l.nome, 'telefone': l.telefone,
         'status': l.status, 'origem': l.origem}
        for l in query
    ])


# ── PÁGINA DEDICADA: IMÓVEIS COMPATÍVEIS ─────────────────────────────────────

def _enviar_email_compativeis(imobiliaria, lead, imoveis, marcar_enviado=True):
    """
    Envia um e-mail ao lead listando os imóveis compatíveis.
    Retorna True se o envio foi bem-sucedido, False caso contrário.
    """
    if not lead.email:
        return False
    if not current_app.config.get('MAIL_USERNAME'):
        return False  # SMTP não configurado

    try:
        html = render_template(
            'email/compativeis.html',
            lead=lead,
            imobiliaria=imobiliaria,
            imoveis=imoveis,
        )
        remetente_nome = imobiliaria.nome
        reply_to = imobiliaria.email_contato or imobiliaria.email_exibicao
        msg = Message(
            subject=f'{imobiliaria.nome} — Imóveis compatíveis com seu perfil',
            sender=(remetente_nome, current_app.config['MAIL_DEFAULT_SENDER']),
            recipients=[lead.email],
            html=html,
            reply_to=reply_to,
        )
        mail.send(msg)

        if marcar_enviado:
            from ..models import ImoveCompativel
            ImoveCompativel.query.filter(
                ImoveCompativel.lead_id == lead.id,
                ImoveCompativel.imovel_id.in_([im.id for im in imoveis]),
            ).update({'email_enviado': True}, synchronize_session=False)
            db.session.commit()

        return True
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar e-mail para {lead.email}: {e}')
        return False


def _calcular_compativeis(imob_id, enviar_email=False):
    """
    Cruza todos os leads com perfil de busca contra o catálogo e persiste novos vínculos.
    Se enviar_email=True, dispara e-mail automático para leads com novos compatíveis.
    Retorna o número de novos pares encontrados.
    """
    from ..models import Imovel, ImoveCompativel, Imobiliaria
    imobiliaria = Imobiliaria.query.get(imob_id)

    leads_com_perfil = Lead.query.filter(
        Lead.imobiliaria_id == imob_id,
        db.or_(
            Lead.interesse_finalidade != None,  # noqa: E711
            Lead.interesse_preco_max  != None,
            Lead.interesse_cidade     != None,
            Lead.interesse_quartos_min!= None,
        )
    ).all()

    novos_por_lead = {}   # lead_id → [Imovel, ...]
    novos = 0
    for lead in leads_com_perfil:
        query = Imovel.query.filter_by(imobiliaria_id=imob_id)

        if lead.interesse_finalidade and lead.interesse_finalidade != 'Ambos':
            fin = {'Compra': 'Venda', 'Locação': 'Locação'}.get(lead.interesse_finalidade)
            if fin:
                query = query.filter(db.or_(
                    Imovel.finalidade == fin,
                    Imovel.finalidade == 'Venda e Locação'
                ))
        if lead.interesse_preco_min:
            query = query.filter(Imovel.preco >= lead.interesse_preco_min)
        if lead.interesse_preco_max:
            query = query.filter(Imovel.preco <= lead.interesse_preco_max)
        if lead.interesse_quartos_min:
            query = query.filter(Imovel.quartos >= lead.interesse_quartos_min)
        if lead.interesse_cidade:
            query = query.filter(Imovel.cidade.ilike(f'%{lead.interesse_cidade}%'))

        for imovel in query.all():
            existe = ImoveCompativel.query.filter_by(
                lead_id=lead.id, imovel_id=imovel.id
            ).first()
            if not existe:
                db.session.add(ImoveCompativel(
                    imobiliaria_id=imob_id,
                    lead_id=lead.id,
                    imovel_id=imovel.id,
                    status='compativel',
                ))
                novos_por_lead.setdefault(lead.id, {'lead': lead, 'imoveis': []})['imoveis'].append(imovel)
                novos += 1

    if novos:
        db.session.commit()

    # Envio automático de e-mail para leads com novos compatíveis
    if enviar_email and imobiliaria:
        for entry in novos_por_lead.values():
            _enviar_email_compativeis(imobiliaria, entry['lead'], entry['imoveis'])

    return novos


@leads_bp.route('/compativeis')
@login_required
def pagina_compativeis():
    from ..models import ImoveCompativel
    imob_id = current_user.imobiliaria_id
    aba     = request.args.get('aba', 'compativel')
    page    = request.args.get('page', 1, type=int)

    # Calcula e persiste novos vínculos ao abrir a página
    _calcular_compativeis(imob_id)

    query = ImoveCompativel.query.filter_by(
        imobiliaria_id=imob_id, status=aba
    ).order_by(ImoveCompativel.criado_em.desc())

    pagination = query.paginate(page=page, per_page=15, error_out=False)

    contagem = {
        'compativel': ImoveCompativel.query.filter_by(imobiliaria_id=imob_id, status='compativel').count(),
        'favorito':   ImoveCompativel.query.filter_by(imobiliaria_id=imob_id, status='favorito').count(),
        'descartado': ImoveCompativel.query.filter_by(imobiliaria_id=imob_id, status='descartado').count(),
    }

    return render_template('admin/leads/compativeis.html',
                           itens=pagination.items,
                           pagination=pagination,
                           aba=aba,
                           contagem=contagem)


@leads_bp.route('/compativeis/recalcular')
@login_required
def recalcular_compativeis():
    novos = _calcular_compativeis(current_user.imobiliaria_id, enviar_email=False)
    flash(f'{novos} novo(s) par(es) compatível(is) encontrado(s).' if novos else 'Nenhum novo compatível encontrado.', 'info')
    return redirect(url_for('leads.pagina_compativeis'))


@leads_bp.route('/compativeis/enviar-emails', methods=['POST'])
@login_required
def enviar_emails_compativeis():
    """Envia e-mails para todos os leads que possuem compatíveis ainda não enviados."""
    from ..models import ImoveCompativel, Imobiliaria, Imovel
    imob_id = current_user.imobiliaria_id
    imobiliaria = Imobiliaria.query.get(imob_id)

    if not current_app.config.get('MAIL_USERNAME'):
        flash('SMTP não configurado. Preencha as variáveis de e-mail no arquivo .env.', 'danger')
        return redirect(url_for('leads.pagina_compativeis'))

    # Busca todos os pares compatíveis (status compativel ou favorito) ainda não enviados
    pares = ImoveCompativel.query.filter(
        ImoveCompativel.imobiliaria_id == imob_id,
        ImoveCompativel.email_enviado  == False,  # noqa: E712
        ImoveCompativel.status.in_(['compativel', 'favorito']),
    ).all()

    # Agrupa por lead
    por_lead = {}
    for par in pares:
        por_lead.setdefault(par.lead_id, {'lead': par.lead, 'imoveis': []})['imoveis'].append(par.imovel)

    enviados = 0
    sem_email = 0
    for entry in por_lead.values():
        lead = entry['lead']
        if not lead.email:
            sem_email += 1
            continue
        ok = _enviar_email_compativeis(imobiliaria, lead, entry['imoveis'])
        if ok:
            enviados += 1

    if enviados:
        flash(f'E-mail enviado para {enviados} lead(s) com sucesso.', 'success')
    else:
        flash('Nenhum e-mail enviado. Verifique se os leads possuem e-mail cadastrado e se o SMTP está configurado.', 'warning')
    if sem_email:
        flash(f'{sem_email} lead(s) ignorado(s) por não terem e-mail cadastrado.', 'info')

    return redirect(url_for('leads.pagina_compativeis'))


@leads_bp.route('/compativeis/lead/<int:lead_id>/enviar-email', methods=['POST'])
@login_required
def enviar_email_lead_compativel(lead_id):
    """Envia e-mail com TODOS os imóveis compatíveis (não descartados) para um lead específico."""
    from ..models import ImoveCompativel, Imobiliaria
    imob_id = current_user.imobiliaria_id
    imobiliaria = Imobiliaria.query.get(imob_id)

    if not current_app.config.get('MAIL_USERNAME'):
        flash('SMTP não configurado. Preencha as variáveis de e-mail no arquivo .env.', 'danger')
        return redirect(url_for('leads.pagina_compativeis'))

    lead = Lead.query.filter_by(id=lead_id, imobiliaria_id=imob_id).first_or_404()

    if not lead.email:
        flash(f'{lead.nome} não possui e-mail cadastrado.', 'warning')
        return redirect(url_for('leads.pagina_compativeis'))

    pares = ImoveCompativel.query.filter(
        ImoveCompativel.lead_id == lead_id,
        ImoveCompativel.imobiliaria_id == imob_id,
        ImoveCompativel.status.in_(['compativel', 'favorito']),
    ).all()
    imoveis = [p.imovel for p in pares]

    if not imoveis:
        flash(f'Nenhum imóvel compatível para enviar a {lead.nome}.', 'info')
        return redirect(url_for('leads.pagina_compativeis'))

    ok = _enviar_email_compativeis(imobiliaria, lead, imoveis)
    if ok:
        flash(f'E-mail enviado para {lead.nome} ({lead.email}) com {len(imoveis)} imóvel(is).', 'success')
    else:
        flash('Falha ao enviar o e-mail. Verifique as configurações SMTP.', 'danger')

    aba = request.args.get('aba', 'compativel')
    return redirect(url_for('leads.pagina_compativeis', aba=aba))


@leads_bp.route('/compativeis/<int:id>/status', methods=['POST'])
@login_required
def atualizar_compativel(id):
    from ..models import ImoveCompativel
    item = ImoveCompativel.query.filter_by(
        id=id, imobiliaria_id=current_user.imobiliaria_id
    ).first_or_404()
    novo_status = request.form.get('status')
    if novo_status in ('compativel', 'favorito', 'descartado'):
        item.status = novo_status
        db.session.commit()
    aba = request.args.get('aba', 'compativel')
    return redirect(url_for('leads.pagina_compativeis', aba=aba))


# ── API pública: receber leads de fontes externas ─────────────────────────────
# Será consumida futuramente pelo site, WhatsApp, Facebook, Instagram.
# Autenticação via header  X-ImobiConectaJa-Token  (api_token da imobiliária).

@leads_bp.route('/api/receber', methods=['POST'])
def api_receber_lead():
    """
    Endpoint público para receber leads de integrações externas.
    Body JSON esperado:
    {
        "nome":     "João Silva",
        "telefone": "11999999999",
        "email":    "joao@email.com",       (opcional)
        "origem":   "Site" | "WhatsApp" | "Facebook" | "Instagram",
        "mensagem": "Tenho interesse no AP001"  (opcional)
    }
    Header obrigatório:
        X-ImobiConectaJa-Token: <api_token da imobiliária>
    """
    from ..models import Imobiliaria

    token = request.headers.get('X-ImobiConectaJa-Token')
    if not token:
        return jsonify({"erro": "Token ausente"}), 401

    imobiliaria = Imobiliaria.query.filter_by(api_token=token).first()
    if not imobiliaria:
        return jsonify({"erro": "Token inválido"}), 401

    dados = request.get_json(silent=True) or {}
    nome     = dados.get('nome', '').strip()
    telefone = dados.get('telefone', '').strip()

    if not nome or not telefone:
        return jsonify({"erro": "Campos 'nome' e 'telefone' são obrigatórios"}), 400

    origens_validas = {'Site', 'WhatsApp', 'Facebook', 'Instagram', 'Manual'}
    origem = dados.get('origem', 'Site')
    if origem not in origens_validas:
        origem = 'Site'

    try:
        lead = Lead(
            imobiliaria_id=imobiliaria.id,
            nome=nome,
            telefone=telefone,
            email=dados.get('email', '').strip() or None,
            origem=origem,
            status='Novo',
            mensagem=dados.get('mensagem', '').strip() or None,
            data_contato=datetime.utcnow()
        )
        db.session.add(lead)
        db.session.commit()
        return jsonify({"ok": True, "lead_id": lead.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": str(e)}), 500