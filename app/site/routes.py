from datetime import datetime
from flask import Blueprint, render_template, g, abort, request, redirect, url_for, jsonify
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


# ── CHATBOT ─────────────────────────────────────────────────────────────────

def _executar_tool(nome_tool: str, entrada: dict, imob_id: int) -> dict:
    """Executa a ferramenta solicitada pelo Claude e retorna o resultado."""
    if nome_tool == "validar_cpf":
        from validate_docbr import CPF as _CPF
        cpf_raw = entrada.get("cpf", "")
        limpo = ''.join(filter(str.isdigit, cpf_raw))
        c = _CPF()
        valido = c.validate(limpo)
        return {
            "valido": valido,
            "cpf_limpo": limpo,
            "mensagem": "CPF válido." if valido else "CPF inválido. Por favor, verifique os números e tente novamente.",
        }

    if nome_tool == "buscar_pessoa":
        from ..models import Pessoa
        cpf = ''.join(filter(str.isdigit, entrada.get("cpf", "")))
        pessoa = Pessoa.query.filter_by(documento=cpf, imobiliaria_id=imob_id).first()
        if pessoa:
            return {"encontrado": True, "nome": pessoa.nome, "email": pessoa.email}
        return {"encontrado": False, "nome": None, "email": None}

    if nome_tool == "registrar_lead":
        from ..models import db, Pessoa, TelefonePessoa, Lead
        dados = entrada
        nome     = dados.get("nome", "").strip()
        cpf      = ''.join(filter(str.isdigit, dados.get("cpf", "")))
        telefone = dados.get("telefone", "").strip()
        email    = dados.get("email", "").strip()
        interesse = dados.get("interesse", "").strip()
        mensagem  = dados.get("mensagem", "").strip()

        try:
            pessoa = None
            if cpf:
                pessoa = Pessoa.query.filter_by(documento=cpf, imobiliaria_id=imob_id).first()

            if not pessoa and nome:
                pessoa = Pessoa(
                    imobiliaria_id=imob_id,
                    nome=nome,
                    documento=cpf or None,
                    email=email or None,
                )
                db.session.add(pessoa)
                db.session.flush()  # gera pessoa.id sem fechar a transação

                if telefone:
                    tel = TelefonePessoa(pessoa_id=pessoa.id, numero=telefone, tipo='WhatsApp')
                    db.session.add(tel)

            lead = Lead(
                imobiliaria_id=imob_id,
                pessoa_id=pessoa.id if pessoa else None,
                nome=nome or "Visitante",
                telefone=telefone or "Não informado",
                email=email or None,
                origem="Chat IA",
                status="Novo",
                mensagem=mensagem or None,
                interesse_finalidade=interesse or None,
            )
            db.session.add(lead)
            db.session.commit()
            return {"sucesso": True, "mensagem": "Lead registrado com sucesso."}
        except Exception as exc:
            db.session.rollback()
            return {"sucesso": False, "mensagem": f"Erro ao registrar: {exc}"}

    if nome_tool == "buscar_imoveis":
        from ..models import Imovel
        finalidade  = entrada.get("finalidade")
        cidade      = entrada.get("cidade")
        quartos_min = entrada.get("quartos_min")
        preco_max   = entrada.get("preco_max")

        q = Imovel.query.filter_by(imobiliaria_id=imob_id)
        if finalidade:
            q = q.filter(Imovel.finalidade.ilike(f"%{finalidade}%"))
        if cidade:
            q = q.filter(Imovel.cidade.ilike(f"%{cidade}%"))
        if quartos_min:
            q = q.filter(Imovel.quartos >= quartos_min)
        if preco_max:
            q = q.filter(Imovel.preco <= preco_max)

        imoveis = q.order_by(Imovel.destaque.desc(), Imovel.id.desc()).limit(5).all()
        resultado = []
        for im in imoveis:
            resultado.append({
                "titulo":     im.titulo,
                "finalidade": im.finalidade,
                "cidade":     im.cidade,
                "quartos":    im.quartos,
                "preco":      float(im.preco) if im.preco else None,
                "url":        url_for('site.detalhes', id=im.id, _external=False),
            })
        return {"imoveis": resultado, "total": len(resultado)}

    return {"erro": f"Ferramenta desconhecida: {nome_tool}"}


@site_bp.route('/chat', methods=['POST'])
def chat():
    import json
    import os

    if not g.imobiliaria:
        return jsonify({'resposta': 'Serviço indisponível.'}), 404

    dados = request.get_json(silent=True) or {}
    mensagem_usuario = (dados.get('mensagem') or '').strip()
    if not mensagem_usuario:
        return jsonify({'resposta': 'Mensagem vazia.'}), 400

    from flask import session, current_app

    # ── Chave de API — imobiliária tem prioridade sobre a chave global ──────
    api_key = (
        getattr(g.imobiliaria, 'anthropic_api_key', None)
        or current_app.config.get('ANTHROPIC_API_KEY')
        or os.environ.get('ANTHROPIC_API_KEY')
    )
    if not api_key:
        return jsonify({
            'resposta': (
                'Nosso assistente virtual está temporariamente indisponível. '
                'Por favor, entre em contato conosco por telefone.'
            ),
            'acao': None,
        })

    try:
        import anthropic
    except ImportError:
        return jsonify({
            'resposta': (
                'Nosso assistente virtual está temporariamente indisponível. '
                'Por favor, entre em contato conosco por telefone.'
            ),
            'acao': None,
        })

    imob_id   = g.imobiliaria.id
    nome_imob = g.imobiliaria.nome

    # ── Histórico de conversa ────────────────────────────────────────────────
    historico = session.get('chat_hist', [])
    historico.append({"role": "user", "content": mensagem_usuario})

    # ── System prompt dinâmico ───────────────────────────────────────────────
    system_prompt = (
        f"Você é {nome_imob}, assistente virtual de atendimento da imobiliária {nome_imob}.\n"
        "Seu objetivo é:\n"
        "1. Cumprimentar o visitante de forma amigável e profissional\n"
        "2. Entender o que ele precisa: comprar, alugar, vender, tirar dúvidas sobre imóveis\n"
        "3. Coletar o nome completo da pessoa\n"
        "4. Solicitar o CPF para identificação (obrigatório para cadastro)\n"
        "5. Usar a ferramenta validar_cpf para validar o CPF informado\n"
        "6. Se o CPF for inválido: informar e pedir novamente\n"
        "7. Se o CPF for válido: usar buscar_pessoa para verificar se já é cliente\n"
        "8. Se já cliente: cumprimentar pelo nome, perguntar como pode ajudar\n"
        "9. Se novo: coletar telefone/WhatsApp e e-mail, depois usar registrar_lead\n"
        "10. Após registrar: informar que a equipe entrará em contato e perguntar se quer ver imóveis disponíveis\n"
        "11. Para busca de imóveis: usar ferramenta buscar_imoveis com os filtros informados pelo visitante\n\n"
        "Regras:\n"
        "- Seja sempre cordial e objetivo\n"
        "- Peça uma informação por vez\n"
        "- Se o visitante não quiser informar o CPF, ofereça apenas mostrar os imóveis disponíveis\n"
        "- Nunca invente dados — use apenas as ferramentas disponíveis\n"
        "- Responda sempre em português brasileiro\n"
        "- Use o nome do visitante quando souber\n"
        "- Máximo 2-3 parágrafos por resposta"
    )

    # ── Ferramentas disponíveis ──────────────────────────────────────────────
    ferramentas = [
        {
            "name": "validar_cpf",
            "description": "Valida se um CPF é matematicamente correto.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cpf": {"type": "string", "description": "CPF com ou sem formatação"}
                },
                "required": ["cpf"],
            },
        },
        {
            "name": "buscar_pessoa",
            "description": "Busca uma pessoa pelo CPF no banco de dados da imobiliária.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cpf": {"type": "string", "description": "CPF somente dígitos (11 caracteres)"}
                },
                "required": ["cpf"],
            },
        },
        {
            "name": "registrar_lead",
            "description": "Registra um novo lead/contato da imobiliária.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "nome":      {"type": "string"},
                    "cpf":       {"type": "string", "description": "Somente dígitos"},
                    "telefone":  {"type": "string"},
                    "email":     {"type": "string"},
                    "interesse": {"type": "string", "description": "Compra, Locação, Venda ou Dúvida"},
                    "mensagem":  {"type": "string", "description": "Resumo do que o visitante precisa"},
                },
                "required": ["nome"],
            },
        },
        {
            "name": "buscar_imoveis",
            "description": "Busca imóveis disponíveis na imobiliária conforme filtros.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "finalidade":  {"type": "string", "description": "Venda ou Locação"},
                    "cidade":      {"type": "string"},
                    "quartos_min": {"type": "integer"},
                    "preco_max":   {"type": "number"},
                },
            },
        },
    ]

    # ── Loop de processamento com tool_use ───────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    resposta_texto = ""
    acao = None
    max_iteracoes = 5

    try:
        for _ in range(max_iteracoes):
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                tools=ferramentas,
                messages=historico,
            )

            if resp.stop_reason == "tool_use":
                msg_assistente = {"role": "assistant", "content": resp.content}
                historico.append(msg_assistente)

                resultados_tools = []
                for bloco in resp.content:
                    if bloco.type == "tool_use":
                        resultado = _executar_tool(bloco.name, bloco.input, imob_id)
                        if bloco.name == "registrar_lead" and resultado.get("sucesso"):
                            acao = "lead_salvo"
                        resultados_tools.append({
                            "type": "tool_result",
                            "tool_use_id": bloco.id,
                            "content": json.dumps(resultado, ensure_ascii=False),
                        })

                historico.append({"role": "user", "content": resultados_tools})
            else:
                for bloco in resp.content:
                    if hasattr(bloco, 'text'):
                        resposta_texto = bloco.text
                        break
                historico.append({"role": "assistant", "content": resposta_texto})
                break

    except Exception as exc:
        return jsonify({
            'resposta': (
                'Desculpe, ocorreu um erro no assistente virtual. '
                'Por favor, tente novamente ou entre em contato por telefone.'
            ),
            'acao': None,
        }), 500

    # ── Salva histórico limitado na sessão ───────────────────────────────────
    session['chat_hist'] = historico[-20:]
    session.modified = True

    return jsonify({'resposta': resposta_texto, 'acao': acao})


@site_bp.route('/chat/reset', methods=['POST'])
def chat_reset():
    from flask import session
    session.pop('chat_hist', None)
    return jsonify({'ok': True})
