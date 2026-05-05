import os, uuid, json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, current_app
from ..models import db, Imobiliaria, Pessoa, TelefonePessoa, Imovel, TipoImovel, Foto

cliente_bp = Blueprint('cliente', __name__)


def _imobiliaria_ou_404():
    """Resolve a imobiliária pelo contexto (subdomínio ou slug na sessão)."""
    from flask import g, abort
    imob = getattr(g, 'imobiliaria', None)
    if not imob:
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
    """Chama a Claude API e retorna JSON com os dados do imóvel extraídos do texto."""
    import anthropic

    api_key = current_app.config.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada."}

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
                "descricao":      {"type": "string", "description": "Resumo descritivo do imóvel para o anúncio"},
                "caracteristicas":{"type": "array", "items": {"type": "string"},
                                   "description": "Lista de características extras (closet, piscina, churrasqueira etc.)"},
            },
            "required": ["finalidade", "tipo", "titulo", "cidade"],
        },
    }

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

    for bloco in resposta.content:
        if bloco.type == "tool_use" and bloco.name == "cadastrar_imovel":
            return bloco.input

    return {}


# ── ROTAS ─────────────────────────────────────────────────────────────────────

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
        tipo_nome = request.form.get('tipo', '').strip()
        tipo = TipoImovel.query.filter_by(imobiliaria_id=imob.id, nome=tipo_nome).first()
        if not tipo and tipos:
            tipo = tipos[0]

        if not tipo:
            flash('Nenhum tipo de imóvel cadastrado. Contate a imobiliária.', 'danger')
            return redirect(url_for('cliente.anunciar'))

        imovel = Imovel(
            imobiliaria_id=imob.id,
            tipo_id=tipo.id,
            titulo=request.form.get('titulo', 'Imóvel a anunciar')[:200],
            finalidade=request.form.get('finalidade', 'Venda'),
            cidade=request.form.get('cidade', '')[:100],
            estado=request.form.get('estado', '')[:2],
            bairro=request.form.get('bairro', '')[:100],
            logradouro=request.form.get('logradouro', '')[:200],
            cep=request.form.get('cep', '')[:10],
            quartos=int(request.form.get('quartos') or 0),
            suites=int(request.form.get('suites') or 0),
            banheiros=int(request.form.get('banheiros') or 0),
            vagas=int(request.form.get('vagas') or 0),
            area_construida=float(request.form.get('area_construida') or 0) or None,
            area_terreno=float(request.form.get('area_terreno') or 0) or None,
            preco=float(request.form.get('preco') or 0) or None,
            descricao=request.form.get('descricao', ''),
        )
        db.session.add(imovel)
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
