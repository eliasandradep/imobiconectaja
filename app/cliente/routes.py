import os, uuid, json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, current_app
from ..models import db, Imobiliaria, Pessoa, TelefonePessoa, Imovel, TipoImovel, Foto

cliente_bp = Blueprint('cliente', __name__)


def _imobiliaria_ou_404():
    """
    Resolve a imobiliária pelo contexto (domínio/subdomínio ou slug na sessão).
    O portal de cadastro pelo proprietário só existe nos planos com chatbot.
    """
    from flask import g, abort
    from ..planos import plano_permite
    imob = getattr(g, 'imobiliaria', None)
    if not imob or not plano_permite(imob, 'chatbot'):
        abort(404)
    return imob


def _validar_cpf(cpf: str) -> str | None:
    """Retorna CPF limpo (só dígitos) se válido, None caso contrário."""
    try:
        from validate_docbr import CPF
        c = CPF()
        limpo = ''.join(filter(str.isdigit, cpf))
        return limpo if c.validate(limpo) else None
    except Exception:
        return None


def _extrair_imovel_ia(texto: str, imob_id: int) -> dict:
    """
    Chama a Claude API e retorna JSON com os dados do imóvel extraídos do texto.
    Usa a chave Anthropic da imobiliária; sem ela, usa a da plataforma e consome
    1 crédito de IA do plano (ver app/planos.py).
    """
    import anthropic
    from ..planos import chave_ia, consumir_credito_ia

    imob = Imobiliaria.query.get(imob_id)
    api_key, consome_credito = chave_ia(imob)
    if not api_key:
        return {"erro": consome_credito}

    client = anthropic.Anthropic(api_key=api_key)

    tipos = TipoImovel.query.filter_by(imobiliaria_id=imob_id).all()
    lista_tipos = ', '.join(t.nome for t in tipos) if tipos else 'Casa, Apartamento, Terreno, Sala Comercial'

    ferramenta = {
        "name": "cadastrar_imovel",
        "description": "Extrai dados estruturados de um imóvel a partir de descrição em texto livre.",
        "input_schema": {
            "type": "object",
            "properties": {
                "finalidade":     {"type": "string", "enum": ["Venda", "Locação", "Venda e Locação"], "description": "Finalidade do imóvel"},
                "tipo":           {"type": "string", "description": f"Tipo do imóvel. Opções: {lista_tipos}"},
                "titulo":         {"type": "string", "description": "Título curto e descritivo para o anúncio"},
                "logradouro":     {"type": "string", "description": "Rua/Avenida, se mencionada"},
                "bairro":         {"type": "string", "description": "Bairro, se mencionado"},
                "cidade":         {"type": "string", "description": "Cidade do imóvel"},
                "estado":         {"type": "string", "description": "UF com 2 letras, ex: SP"},
                "cep":            {"type": "string", "description": "CEP, se mencionado"},
                "area_construida":{"type": "number", "description": "Área construída em m²"},
                "area_terreno":   {"type": "number", "description": "Área do terreno em m²"},
                "quartos":        {"type": "integer", "description": "Número de quartos"},
                "suites":         {"type": "integer", "description": "Número de suítes"},
                "banheiros":      {"type": "integer", "description": "Número de banheiros"},
                "vagas":          {"type": "integer", "description": "Vagas de garagem"},
                "preco":          {"type": "number", "description": "Preço em R$, se mencionado"},
                "aceita_permuta": {"type": "boolean", "description": "true se o proprietário aceita permuta/troca (só para venda)"},
                "permuta_obs":    {"type": "string", "description": "O que aceita na permuta, se mencionado (ex: carro, apartamento menor)"},
                "descricao":      {"type": "string", "description": "Resumo descritivo do imóvel para o anúncio"},
                "caracteristicas":{"type": "array", "items": {"type": "string"},
                                   "description": "Lista de características extras (closet, piscina, churrasqueira etc.)"},
            },
            "required": ["finalidade", "tipo", "titulo", "cidade"],
        },
    }

    try:
        resposta = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=[ferramenta],
            messages=[{
                "role": "user",
                "content": (
                    "Você é um assistente especializado em imóveis brasileiros. "
                    "Analise a descrição abaixo e extraia todos os dados do imóvel.\n\n"
                    f"Descrição: {texto}"
                ),
            }],
            tool_choice={"type": "any"},
        )
    except Exception as e:
        current_app.logger.error(f'Erro na extração por IA (imobiliária {imob_id}): {e}')
        return {"erro": "Não foi possível analisar a descrição agora. Tente novamente."}

    if consome_credito:
        consumir_credito_ia(imob)

    for bloco in resposta.content:
        if bloco.type == "tool_use" and bloco.name == "cadastrar_imovel":
            return bloco.input

    return {}


def _num(v):
    """Converte número vindo da IA ou de formulário (aceita '550.000,00', '550000', 120.5)."""
    if v in (None, ''):
        return 0
    if isinstance(v, (int, float)):
        return float(v)
    s = ''.join(c for c in str(v) if c.isdigit() or c in ',.')
    if ',' in s:                       # formato brasileiro: ponto = milhar, vírgula = decimal
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1 or (s.count('.') == 1 and len(s.split('.')[1]) == 3):
        s = s.replace('.', '')         # '550.000' / '1.250.000' → separador de milhar
    try:
        return float(s) if s else 0
    except ValueError:
        return 0


def _sim(v):
    """Booleano vindo de JSON (True) ou de formulário ('on', '1', 'sim')."""
    return v is True or str(v).strip().lower() in ('on', '1', 'true', 'sim', 's')


def criar_imovel_proprietario(imob, pessoa_id, dados, origem):
    """
    Cria o imóvel enviado pelo próprio proprietário (WhatsApp ou portal).
    Entra como 'pendente': só aparece no site depois que o corretor aprova.
    `dados` usa os nomes da extração por IA (area_construida, area_terreno...).
    Retorna o Imovel (sem commit) ou None se a imobiliária não tem tipos cadastrados.
    """
    tipos = TipoImovel.query.filter_by(imobiliaria_id=imob.id).all()
    nome_tipo = (dados.get('tipo') or '').strip().lower()
    tipo = next((t for t in tipos if t.nome.lower() == nome_tipo), None) or (tipos[0] if tipos else None)
    if not tipo:
        return None

    finalidade = dados.get('finalidade')
    if finalidade not in ('Venda', 'Locação', 'Venda e Locação'):
        finalidade = 'Venda'

    ultimo = Imovel.query.filter_by(imobiliaria_id=imob.id).order_by(Imovel.id.desc()).first()
    codigo_ref = f"{tipo.prefixo}{((ultimo.id + 1) if ultimo else 1):04d}"

    imovel = Imovel(
        imobiliaria_id=imob.id,
        tipo_id=tipo.id,
        codigo_ref=codigo_ref,
        titulo=(dados.get('titulo') or f'{tipo.nome} para {finalidade}')[:200],
        finalidade=finalidade,
        cidade=(dados.get('cidade') or '')[:100],
        estado=(dados.get('estado') or '')[:2].upper(),
        bairro=(dados.get('bairro') or '')[:100],
        logradouro=(dados.get('logradouro') or '')[:200],
        cep=(dados.get('cep') or '')[:10],
        quartos=int(_num(dados.get('quartos'))),
        suites=int(_num(dados.get('suites'))),
        banheiros=int(_num(dados.get('banheiros'))),
        vagas=int(_num(dados.get('vagas'))),
        area_util=_num(dados.get('area_construida')),
        area_total=_num(dados.get('area_terreno')) or _num(dados.get('area_construida')),
        preco=_num(dados.get('preco')),
        descricao=dados.get('descricao') or '',
        proprietario_id=pessoa_id,
        status_publicacao='pendente',
        origem_cadastro=origem,
        aceita_permuta=_sim(dados.get('aceita_permuta')) and finalidade != 'Locação',
        permuta_obs=((dados.get('permuta_obs') or '').strip()[:300] or None) if finalidade != 'Locação' else None,
    )
    db.session.add(imovel)
    return imovel


# ── ROTAS ─────────────────────────────────────────────────────────────────────

@cliente_bp.route('/<slug>/cliente')
def portal_por_slug(slug):
    """Acesso pelo host da plataforma: /{slug}/cliente → grava a imobiliária na sessão."""
    from flask import abort
    imob = Imobiliaria.query.filter_by(slug=slug, ativo=True).first()
    if not imob:
        abort(404)
    session['_site_imob_id'] = imob.id
    return redirect(url_for('cliente.portal'))


@cliente_bp.route('/cliente')
def portal():
    imob = _imobiliaria_ou_404()
    return render_template('cliente/portal.html', imob=imob)


@cliente_bp.route('/cliente/identificar', methods=['POST'])
def identificar():
    imob  = _imobiliaria_ou_404()
    cpf_raw = request.form.get('cpf', '')
    cpf = _validar_cpf(cpf_raw)

    if not cpf:
        flash('CPF inválido. Verifique e tente novamente.', 'danger')
        return redirect(url_for('cliente.portal'))

    pessoa = Pessoa.query.filter_by(imobiliaria_id=imob.id, documento=cpf).first()

    if pessoa:
        session['cliente_pessoa_id'] = pessoa.id
        session['cliente_imob_id']   = imob.id
        flash(f'Bem-vindo de volta, {pessoa.nome.split()[0]}!', 'success')
        return redirect(url_for('cliente.anunciar'))

    session['cliente_cpf']      = cpf
    session['cliente_imob_id']  = imob.id
    return redirect(url_for('cliente.cadastro'))


@cliente_bp.route('/cliente/cadastro', methods=['GET', 'POST'])
def cadastro():
    imob = _imobiliaria_ou_404()
    cpf = session.get('cliente_cpf')
    if not cpf:
        return redirect(url_for('cliente.portal'))

    if request.method == 'POST':
        nome  = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        fone  = request.form.get('telefone', '').strip()

        if not nome:
            flash('Informe seu nome completo.', 'danger')
            return render_template('cliente/cadastro.html', imob=imob, cpf=cpf)

        pessoa = Pessoa(
            imobiliaria_id=imob.id,
            nome=nome,
            email=email or None,
            documento=cpf,
            tipo='Proprietário',
        )
        db.session.add(pessoa)
        db.session.flush()

        if fone:
            db.session.add(TelefonePessoa(pessoa_id=pessoa.id, numero=fone))

        db.session.commit()
        session['cliente_pessoa_id'] = pessoa.id
        session.pop('cliente_cpf', None)
        return redirect(url_for('cliente.anunciar'))

    return render_template('cliente/cadastro.html', imob=imob, cpf=cpf)


@cliente_bp.route('/cliente/anunciar', methods=['GET', 'POST'])
def anunciar():
    imob = _imobiliaria_ou_404()
    if not session.get('cliente_pessoa_id') or session.get('cliente_imob_id') != imob.id:
        return redirect(url_for('cliente.portal'))

    tipos = TipoImovel.query.filter_by(imobiliaria_id=imob.id).all()

    if request.method == 'POST':
        imovel = criar_imovel_proprietario(
            imob, session['cliente_pessoa_id'], request.form.to_dict(), origem='Portal')
        if not imovel:
            flash('Nenhum tipo de imóvel cadastrado. Contate a imobiliária.', 'danger')
            return redirect(url_for('cliente.anunciar'))
        db.session.flush()

        fotos = request.files.getlist('fotos')
        upload_dir = os.path.join('app', 'static', 'uploads', str(imob.id), 'imoveis', str(imovel.id))
        os.makedirs(upload_dir, exist_ok=True)
        primeira = True
        for f in fotos:
            if f and f.filename:
                ext = f.filename.rsplit('.', 1)[-1].lower()
                if ext in {'jpg', 'jpeg', 'png', 'webp'}:
                    nome = f'{uuid.uuid4().hex}.{ext}'
                    caminho = os.path.join(upload_dir, nome)
                    f.save(caminho)
                    db.session.add(Foto(
                        imovel_id=imovel.id,
                        url=f'uploads/{imob.id}/imoveis/{imovel.id}/{nome}',
                        principal=primeira,
                    ))
                    primeira = False

        db.session.commit()
        session.pop('cliente_pessoa_id', None)
        session.pop('cliente_imob_id', None)
        flash('Imóvel cadastrado com sucesso! Nossa equipe entrará em contato em breve.', 'success')
        return redirect(url_for('cliente.confirmacao'))

    return render_template('cliente/anunciar.html', imob=imob, tipos=tipos)


@cliente_bp.route('/cliente/confirmacao')
def confirmacao():
    imob = _imobiliaria_ou_404()
    return render_template('cliente/confirmacao.html', imob=imob)


# ── API: extração via IA ──────────────────────────────────────────────────────

@cliente_bp.route('/api/extrair-imovel', methods=['POST'])
def extrair_imovel():
    imob = _imobiliaria_ou_404()
    dados = request.get_json(silent=True) or {}
    texto = (dados.get('texto') or '').strip()

    if not texto or len(texto) < 20:
        return jsonify({'erro': 'Descreva o imóvel com mais detalhes.'}), 400

    resultado = _extrair_imovel_ia(texto, imob.id)

    if 'erro' in resultado:
        return jsonify(resultado), 500

    return jsonify(resultado)
