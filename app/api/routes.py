from flask import Blueprint, request, jsonify, g, current_app
from functools import wraps
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename

EXTENSOES_PERMITIDAS = {'jpg', 'jpeg', 'png', 'webp'}

def _extensao_permitida(nome):
    return '.' in nome and nome.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS

api_bp = Blueprint('api', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ok(dados=None, mensagem=None, status=200):
    resp = {"sucesso": True}
    if mensagem:
        resp["mensagem"] = mensagem
    if dados is not None:
        resp["dados"] = dados
    return jsonify(resp), status


def _erro(mensagem, status=400):
    return jsonify({"sucesso": False, "erro": mensagem}), status


def _paginar(query, pagina, por_pagina=20):
    pagina = max(1, pagina)
    por_pagina = min(max(1, por_pagina), 100)
    total = query.count()
    itens = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    return itens, {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, (total + por_pagina - 1) // por_pagina),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Autenticação via Token
# ─────────────────────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-ImobiConectaJa-Token')
        if not token:
            return _erro("Token ausente. Envie o header 'X-ImobiConectaJa-Token'.", 401)
        from ..models import Imobiliaria
        imob = Imobiliaria.query.filter_by(api_token=token).first()
        if not imob:
            return _erro("Token inválido.", 401)
        if not imob.ativo:
            return _erro("Imobiliária inativa.", 403)
        g.current_imob = imob
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# Status / Docs
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/status', methods=['GET'])
def status():
    return _ok({"versao": "1.0", "plataforma": "ImobiConectaJa"}, "API online")


@api_bp.route('/docs', methods=['GET'])
def docs():
    endpoints = {
        "autenticacao": {
            "header": "X-ImobiConectaJa-Token",
            "descricao": "Todas as rotas (exceto /status e /docs) exigem este header."
        },
        "clientes": {
            "GET    /api/clientes":       "Lista clientes (paginado). Params: pagina, por_pagina, tipo, busca",
            "POST   /api/clientes":       "Cria um novo cliente",
            "GET    /api/clientes/{id}":  "Retorna um cliente pelo ID",
            "PUT    /api/clientes/{id}":  "Atualiza um cliente",
            "DELETE /api/clientes/{id}":  "Remove um cliente",
        },
        "imoveis": {
            "GET    /api/imoveis":                          "Lista imóveis (paginado). Params: pagina, por_pagina, finalidade, cidade, destaque, busca",
            "POST   /api/imoveis":                          "Cria um novo imóvel",
            "GET    /api/imoveis/{id}":                     "Retorna um imóvel pelo ID",
            "PUT    /api/imoveis/{id}":                     "Atualiza um imóvel",
            "DELETE /api/imoveis/{id}":                     "Remove um imóvel",
            "GET    /api/imoveis/tipos":                    "Lista tipos de imóvel cadastrados",
            "POST   /api/imoveis/{id}/fotos":               "Envia uma ou mais fotos (multipart/form-data, campo 'fotos'). Formatos: jpg, jpeg, png, webp",
            "PUT    /api/imoveis/{id}/fotos/{fid}/principal":"Define uma foto como principal",
            "DELETE /api/imoveis/{id}/fotos/{fid}":         "Remove uma foto",
        },
        "leads": {
            "GET    /api/leads":          "Lista leads (paginado). Params: pagina, por_pagina, status, origem, busca",
            "POST   /api/leads":          "Cria um novo lead",
            "GET    /api/leads/{id}":     "Retorna um lead pelo ID",
            "PUT    /api/leads/{id}":     "Atualiza um lead",
            "DELETE /api/leads/{id}":     "Remove um lead",
        },
    }
    return _ok(endpoints)


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

def _serializar_pessoa(p):
    return {
        "id": p.id,
        "tipo": p.tipo,
        "nome": p.nome,
        "email": p.email,
        "documento": p.documento,
        "data_nascimento": p.data_nascimento.isoformat() if p.data_nascimento else None,
        "telefones": [{"numero": t.numero, "tipo": t.tipo} for t in p.telefones],
        "endereco": {
            "cep": p.cep, "logradouro": p.logradouro, "numero": p.numero,
            "complemento": p.complemento, "bairro": p.bairro,
            "cidade": p.cidade, "estado": p.estado,
        },
        "observacoes": p.observacoes,
        "data_cadastro": p.data_cadastro.isoformat() if p.data_cadastro else None,
    }


def _serializar_imovel(iv):
    foto_principal = next((f.url for f in iv.fotos if f.principal), None)
    if not foto_principal and iv.fotos:
        foto_principal = iv.fotos[0].url
    return {
        "id": iv.id,
        "codigo_ref": iv.codigo_ref,
        "titulo": iv.titulo,
        "finalidade": iv.finalidade,
        "tipo": {"id": iv.tipo_id, "nome": iv.tipo.nome if iv.tipo else None},
        "preco": float(iv.preco) if iv.preco else 0,
        "valor_condominio": float(iv.valor_condominio) if iv.valor_condominio else 0,
        "valor_iptu": float(iv.valor_iptu) if iv.valor_iptu else 0,
        "area_util": iv.area_util,
        "area_total": iv.area_total,
        "quartos": iv.quartos,
        "suites": iv.suites,
        "banheiros": iv.banheiros,
        "vagas": iv.vagas,
        "descricao": iv.descricao,
        "destaque": iv.destaque,
        "endereco": {
            "cep": iv.cep, "logradouro": iv.logradouro, "numero": iv.numero,
            "complemento": iv.complemento, "bairro": iv.bairro,
            "cidade": iv.cidade, "estado": iv.estado,
        },
        "foto_principal": foto_principal,
        "total_fotos": len(iv.fotos),
        "data_cadastro": iv.data_cadastro.isoformat() if iv.data_cadastro else None,
    }


def _serializar_lead(l):
    return {
        "id": l.id,
        "nome": l.nome,
        "telefone": l.telefone,
        "email": l.email,
        "origem": l.origem,
        "status": l.status,
        "mensagem": l.mensagem,
        "pessoa_id": l.pessoa_id,
        "interesse": {
            "finalidade": l.interesse_finalidade,
            "preco_min": float(l.interesse_preco_min) if l.interesse_preco_min else None,
            "preco_max": float(l.interesse_preco_max) if l.interesse_preco_max else None,
            "quartos_min": l.interesse_quartos_min,
            "cidade": l.interesse_cidade,
            "bairros": l.interesse_bairros,
        },
        "data_contato": l.data_contato.isoformat() if l.data_contato else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTES (Pessoas)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/clientes', methods=['GET'])
@token_required
def listar_clientes():
    from ..models import Pessoa
    pagina     = request.args.get('pagina',    1,  type=int)
    por_pagina = request.args.get('por_pagina',20, type=int)
    tipo       = request.args.get('tipo')
    busca      = request.args.get('busca', '').strip()

    q = Pessoa.query.filter_by(imobiliaria_id=g.current_imob.id)
    if tipo:
        q = q.filter_by(tipo=tipo)
    if busca:
        like = f"%{busca}%"
        q = q.filter(
            Pessoa.nome.ilike(like) |
            Pessoa.email.ilike(like) |
            Pessoa.documento.ilike(like)
        )
    q = q.order_by(Pessoa.nome)
    itens, paginacao = _paginar(q, pagina, por_pagina)
    return _ok({**paginacao, "itens": [_serializar_pessoa(p) for p in itens]})


@api_bp.route('/clientes', methods=['POST'])
@token_required
def criar_cliente():
    from ..models import Pessoa, TelefonePessoa, TIPOS_PESSOA, db
    dados = request.get_json(silent=True) or {}

    nome = (dados.get('nome') or '').strip()
    if not nome:
        return _erro("Campo 'nome' é obrigatório.")

    tipo = dados.get('tipo', 'Cliente')
    if tipo not in TIPOS_PESSOA:
        return _erro(f"Tipo inválido. Valores aceitos: {', '.join(TIPOS_PESSOA)}")

    data_nasc = None
    if dados.get('data_nascimento'):
        try:
            data_nasc = datetime.strptime(dados['data_nascimento'], '%Y-%m-%d').date()
        except ValueError:
            return _erro("Formato de 'data_nascimento' inválido. Use YYYY-MM-DD.")

    pessoa = Pessoa(
        imobiliaria_id=g.current_imob.id,
        nome=nome,
        tipo=tipo,
        email=dados.get('email'),
        documento=dados.get('documento'),
        data_nascimento=data_nasc,
        cep=dados.get('cep'),
        logradouro=dados.get('logradouro'),
        numero=dados.get('numero'),
        complemento=dados.get('complemento'),
        bairro=dados.get('bairro'),
        cidade=dados.get('cidade'),
        estado=dados.get('estado'),
        observacoes=dados.get('observacoes'),
    )
    db.session.add(pessoa)
    db.session.flush()

    for tel in dados.get('telefones', []):
        numero = (tel.get('numero') or '').strip()
        if numero:
            db.session.add(TelefonePessoa(
                pessoa_id=pessoa.id,
                numero=numero,
                tipo=tel.get('tipo', 'Celular'),
            ))

    db.session.commit()
    return _ok(_serializar_pessoa(pessoa), "Cliente criado com sucesso.", 201)


@api_bp.route('/clientes/<int:id>', methods=['GET'])
@token_required
def obter_cliente(id):
    from ..models import Pessoa
    p = Pessoa.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not p:
        return _erro("Cliente não encontrado.", 404)
    return _ok(_serializar_pessoa(p))


@api_bp.route('/clientes/<int:id>', methods=['PUT'])
@token_required
def atualizar_cliente(id):
    from ..models import Pessoa, TelefonePessoa, TIPOS_PESSOA, db
    p = Pessoa.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not p:
        return _erro("Cliente não encontrado.", 404)

    dados = request.get_json(silent=True) or {}

    if 'nome' in dados:
        nome = dados['nome'].strip()
        if not nome:
            return _erro("Campo 'nome' não pode ser vazio.")
        p.nome = nome

    if 'tipo' in dados:
        if dados['tipo'] not in TIPOS_PESSOA:
            return _erro(f"Tipo inválido. Valores aceitos: {', '.join(TIPOS_PESSOA)}")
        p.tipo = dados['tipo']

    for campo in ('email', 'documento', 'observacoes', 'cep', 'logradouro',
                  'numero', 'complemento', 'bairro', 'cidade', 'estado'):
        if campo in dados:
            setattr(p, campo, dados[campo])

    if 'data_nascimento' in dados:
        if dados['data_nascimento']:
            try:
                p.data_nascimento = datetime.strptime(dados['data_nascimento'], '%Y-%m-%d').date()
            except ValueError:
                return _erro("Formato de 'data_nascimento' inválido. Use YYYY-MM-DD.")
        else:
            p.data_nascimento = None

    if 'telefones' in dados:
        for tel in p.telefones:
            db.session.delete(tel)
        for tel in dados['telefones']:
            numero = (tel.get('numero') or '').strip()
            if numero:
                db.session.add(TelefonePessoa(
                    pessoa_id=p.id,
                    numero=numero,
                    tipo=tel.get('tipo', 'Celular'),
                ))

    db.session.commit()
    return _ok(_serializar_pessoa(p), "Cliente atualizado com sucesso.")


@api_bp.route('/clientes/<int:id>', methods=['DELETE'])
@token_required
def excluir_cliente(id):
    from ..models import Pessoa, db
    p = Pessoa.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not p:
        return _erro("Cliente não encontrado.", 404)
    db.session.delete(p)
    db.session.commit()
    return _ok(mensagem="Cliente removido com sucesso.")


# ─────────────────────────────────────────────────────────────────────────────
# IMÓVEIS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/imoveis/tipos', methods=['GET'])
@token_required
def listar_tipos_imovel():
    from ..models import TipoImovel
    tipos = TipoImovel.query.filter_by(imobiliaria_id=g.current_imob.id).order_by(TipoImovel.nome).all()
    return _ok([{"id": t.id, "nome": t.nome, "prefixo": t.prefixo} for t in tipos])


@api_bp.route('/imoveis', methods=['GET'])
@token_required
def listar_imoveis():
    from ..models import Imovel
    pagina     = request.args.get('pagina',    1,  type=int)
    por_pagina = request.args.get('por_pagina',20, type=int)
    finalidade = request.args.get('finalidade')
    cidade     = request.args.get('cidade', '').strip()
    destaque   = request.args.get('destaque')
    busca      = request.args.get('busca', '').strip()

    q = Imovel.query.filter_by(imobiliaria_id=g.current_imob.id)
    if finalidade:
        q = q.filter(Imovel.finalidade.ilike(f"%{finalidade}%"))
    if cidade:
        q = q.filter(Imovel.cidade.ilike(f"%{cidade}%"))
    if destaque is not None:
        q = q.filter_by(destaque=(destaque.lower() == 'true'))
    if busca:
        like = f"%{busca}%"
        q = q.filter(
            Imovel.titulo.ilike(like) |
            Imovel.codigo_ref.ilike(like) |
            Imovel.bairro.ilike(like)
        )
    q = q.order_by(Imovel.data_cadastro.desc())
    itens, paginacao = _paginar(q, pagina, por_pagina)
    return _ok({**paginacao, "itens": [_serializar_imovel(iv) for iv in itens]})


@api_bp.route('/imoveis', methods=['POST'])
@token_required
def criar_imovel():
    from ..models import Imovel, TipoImovel, db
    dados = request.get_json(silent=True) or {}

    titulo = (dados.get('titulo') or '').strip()
    if not titulo:
        return _erro("Campo 'titulo' é obrigatório.")

    tipo_id = dados.get('tipo_id')
    if not tipo_id:
        return _erro("Campo 'tipo_id' é obrigatório. Consulte GET /api/imoveis/tipos.")
    tipo = TipoImovel.query.filter_by(id=tipo_id, imobiliaria_id=g.current_imob.id).first()
    if not tipo:
        return _erro("tipo_id inválido ou não pertence a esta imobiliária.")

    finalidades_validas = ['Venda', 'Locação', 'Venda e Locação']
    finalidade = dados.get('finalidade', 'Venda')
    if finalidade not in finalidades_validas:
        return _erro(f"finalidade inválida. Valores aceitos: {', '.join(finalidades_validas)}")

    def _num(v, default=0):
        try:
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    codigo_ref = dados.get('codigo_ref')
    if not codigo_ref:
        ultimo = (Imovel.query
                  .filter_by(imobiliaria_id=g.current_imob.id)
                  .order_by(Imovel.id.desc()).first())
        proximo = (ultimo.id + 1) if ultimo else 1
        codigo_ref = f"{tipo.prefixo}{proximo:04d}"

    imovel = Imovel(
        imobiliaria_id=g.current_imob.id,
        tipo_id=tipo_id,
        codigo_ref=codigo_ref,
        titulo=titulo,
        finalidade=finalidade,
        cep=dados.get('cep'),
        logradouro=dados.get('logradouro'),
        numero=dados.get('numero'),
        complemento=dados.get('complemento'),
        bairro=dados.get('bairro'),
        cidade=dados.get('cidade'),
        estado=dados.get('estado'),
        preco=_num(dados.get('preco')),
        valor_condominio=_num(dados.get('valor_condominio')),
        valor_iptu=_num(dados.get('valor_iptu')),
        area_util=_num(dados.get('area_util')),
        area_total=_num(dados.get('area_total')),
        quartos=int(_num(dados.get('quartos'))),
        suites=int(_num(dados.get('suites'))),
        banheiros=int(_num(dados.get('banheiros'))),
        vagas=int(_num(dados.get('vagas'))),
        descricao=dados.get('descricao'),
        destaque=bool(dados.get('destaque', False)),
    )
    db.session.add(imovel)
    db.session.commit()
    return _ok(_serializar_imovel(imovel), "Imóvel criado com sucesso.", 201)


@api_bp.route('/imoveis/<int:id>', methods=['GET'])
@token_required
def obter_imovel(id):
    from ..models import Imovel
    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)
    return _ok(_serializar_imovel(iv))


@api_bp.route('/imoveis/<int:id>', methods=['PUT'])
@token_required
def atualizar_imovel(id):
    from ..models import Imovel, TipoImovel, db
    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)

    dados = request.get_json(silent=True) or {}

    if 'titulo' in dados:
        titulo = dados['titulo'].strip()
        if not titulo:
            return _erro("Campo 'titulo' não pode ser vazio.")
        iv.titulo = titulo

    if 'tipo_id' in dados:
        tipo = TipoImovel.query.filter_by(id=dados['tipo_id'], imobiliaria_id=g.current_imob.id).first()
        if not tipo:
            return _erro("tipo_id inválido.")
        iv.tipo_id = dados['tipo_id']

    if 'finalidade' in dados:
        finalidades_validas = ['Venda', 'Locação', 'Venda e Locação']
        if dados['finalidade'] not in finalidades_validas:
            return _erro(f"finalidade inválida. Valores aceitos: {', '.join(finalidades_validas)}")
        iv.finalidade = dados['finalidade']

    for campo in ('codigo_ref', 'cep', 'logradouro', 'numero', 'complemento',
                  'bairro', 'cidade', 'estado', 'descricao'):
        if campo in dados:
            setattr(iv, campo, dados[campo])

    def _num(v, default=None):
        try:
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    for campo in ('preco', 'valor_condominio', 'valor_iptu', 'area_util', 'area_total'):
        if campo in dados:
            setattr(iv, campo, _num(dados[campo], 0))

    for campo in ('quartos', 'suites', 'banheiros', 'vagas'):
        if campo in dados:
            setattr(iv, campo, int(_num(dados[campo], 0)))

    if 'destaque' in dados:
        iv.destaque = bool(dados['destaque'])

    db.session.commit()
    return _ok(_serializar_imovel(iv), "Imóvel atualizado com sucesso.")


@api_bp.route('/imoveis/<int:id>', methods=['DELETE'])
@token_required
def excluir_imovel(id):
    from ..models import Imovel, db
    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)
    db.session.delete(iv)
    db.session.commit()
    return _ok(mensagem="Imóvel removido com sucesso.")


@api_bp.route('/imoveis/<int:id>/fotos', methods=['POST'])
@token_required
def upload_fotos_imovel(id):
    from ..models import Imovel, Foto, db

    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)

    arquivos = request.files.getlist('fotos')
    if not arquivos or all(f.filename == '' for f in arquivos):
        return _erro("Nenhum arquivo enviado. Use o campo 'fotos' como multipart/form-data.")

    # Valida extensões antes de salvar qualquer arquivo
    for arq in arquivos:
        if arq.filename and not _extensao_permitida(arq.filename):
            return _erro(f"Arquivo '{arq.filename}' não permitido. Use: jpg, jpeg, png ou webp.")

    base_dir = os.path.join(current_app.root_path, 'static', 'uploads',
                            str(g.current_imob.id), str(iv.id))
    os.makedirs(base_dir, exist_ok=True)

    ja_tem_fotos = Foto.query.filter_by(imovel_id=iv.id).count() > 0
    salvas = []

    for i, arq in enumerate(arquivos):
        if not arq.filename:
            continue

        ext      = arq.filename.rsplit('.', 1)[1].lower()
        nome     = f"{uuid.uuid4().hex}.{ext}"
        caminho  = os.path.join(base_dir, nome)
        arq.save(caminho)

        # Primeira foto da requisição vira principal se o imóvel ainda não tinha fotos
        eh_principal = (not ja_tem_fotos and i == 0)
        foto = Foto(
            imovel_id=iv.id,
            url=f"uploads/{g.current_imob.id}/{iv.id}/{nome}",
            principal=eh_principal,
        )
        db.session.add(foto)
        salvas.append({"nome_original": arq.filename, "principal": eh_principal})

    db.session.commit()

    total = Foto.query.filter_by(imovel_id=iv.id).count()
    return _ok(
        {"enviadas": len(salvas), "total_fotos": total, "arquivos": salvas},
        f"{len(salvas)} foto(s) salva(s) com sucesso.",
        201,
    )


@api_bp.route('/imoveis/<int:id>/fotos/<int:foto_id>/principal', methods=['PUT'])
@token_required
def definir_foto_principal_api(id, foto_id):
    from ..models import Imovel, Foto, db

    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)

    foto = Foto.query.filter_by(id=foto_id, imovel_id=iv.id).first()
    if not foto:
        return _erro("Foto não encontrada.", 404)

    Foto.query.filter_by(imovel_id=iv.id).update({"principal": False})
    foto.principal = True
    db.session.commit()
    return _ok({"foto_id": foto_id}, "Foto definida como principal.")


@api_bp.route('/imoveis/<int:id>/fotos/<int:foto_id>', methods=['DELETE'])
@token_required
def excluir_foto_imovel(id, foto_id):
    from ..models import Imovel, Foto, db

    iv = Imovel.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not iv:
        return _erro("Imóvel não encontrado.", 404)

    foto = Foto.query.filter_by(id=foto_id, imovel_id=iv.id).first()
    if not foto:
        return _erro("Foto não encontrada.", 404)

    era_principal = foto.principal

    # Remove o arquivo do disco
    caminho = os.path.join(current_app.root_path, 'static', foto.url)
    if os.path.exists(caminho):
        os.remove(caminho)

    db.session.delete(foto)
    db.session.commit()

    # Se era principal, promove a próxima foto disponível
    if era_principal:
        proxima = Foto.query.filter_by(imovel_id=iv.id).first()
        if proxima:
            proxima.principal = True
            db.session.commit()

    return _ok(mensagem="Foto removida com sucesso.")


# ─────────────────────────────────────────────────────────────────────────────
# LEADS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/leads', methods=['GET'])
@token_required
def listar_leads():
    from ..models import Lead
    pagina     = request.args.get('pagina',    1,  type=int)
    por_pagina = request.args.get('por_pagina',20, type=int)
    status     = request.args.get('status')
    origem     = request.args.get('origem')
    busca      = request.args.get('busca', '').strip()

    q = Lead.query.filter_by(imobiliaria_id=g.current_imob.id)
    if status:
        q = q.filter_by(status=status)
    if origem:
        q = q.filter_by(origem=origem)
    if busca:
        like = f"%{busca}%"
        q = q.filter(
            Lead.nome.ilike(like) |
            Lead.telefone.ilike(like) |
            Lead.email.ilike(like)
        )
    q = q.order_by(Lead.data_contato.desc())
    itens, paginacao = _paginar(q, pagina, por_pagina)
    return _ok({**paginacao, "itens": [_serializar_lead(l) for l in itens]})


@api_bp.route('/leads', methods=['POST'])
@token_required
def criar_lead():
    from ..models import Lead, db
    dados = request.get_json(silent=True) or {}

    nome     = (dados.get('nome') or '').strip()
    telefone = (dados.get('telefone') or dados.get('whatsapp') or '').strip()

    if not nome:
        return _erro("Campo 'nome' é obrigatório.")
    if not telefone:
        return _erro("Campo 'telefone' é obrigatório.")

    origens_validas = ['Manual', 'Site', 'WhatsApp', 'Facebook', 'Instagram']
    origem = dados.get('origem', 'Manual')
    if origem not in origens_validas:
        return _erro(f"origem inválida. Valores aceitos: {', '.join(origens_validas)}")

    status_validos = ['Novo', 'Qualificado', 'Arquivado', 'Perdido']
    status = dados.get('status', 'Novo')
    if status not in status_validos:
        return _erro(f"status inválido. Valores aceitos: {', '.join(status_validos)}")

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    lead = Lead(
        imobiliaria_id=g.current_imob.id,
        nome=nome,
        telefone=telefone,
        email=dados.get('email'),
        origem=origem,
        status=status,
        mensagem=dados.get('mensagem'),
        interesse_finalidade=dados.get('interesse_finalidade'),
        interesse_preco_min=_num(dados.get('interesse_preco_min')),
        interesse_preco_max=_num(dados.get('interesse_preco_max')),
        interesse_quartos_min=dados.get('interesse_quartos_min'),
        interesse_cidade=dados.get('interesse_cidade'),
        interesse_bairros=dados.get('interesse_bairros'),
    )
    db.session.add(lead)
    db.session.commit()
    return _ok(_serializar_lead(lead), "Lead criado com sucesso.", 201)


@api_bp.route('/leads/<int:id>', methods=['GET'])
@token_required
def obter_lead(id):
    from ..models import Lead
    l = Lead.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not l:
        return _erro("Lead não encontrado.", 404)
    return _ok(_serializar_lead(l))


@api_bp.route('/leads/<int:id>', methods=['PUT'])
@token_required
def atualizar_lead(id):
    from ..models import Lead, db
    l = Lead.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not l:
        return _erro("Lead não encontrado.", 404)

    dados = request.get_json(silent=True) or {}

    if 'nome' in dados:
        nome = dados['nome'].strip()
        if not nome:
            return _erro("Campo 'nome' não pode ser vazio.")
        l.nome = nome

    if 'telefone' in dados:
        telefone = dados['telefone'].strip()
        if not telefone:
            return _erro("Campo 'telefone' não pode ser vazio.")
        l.telefone = telefone

    if 'origem' in dados:
        origens_validas = ['Manual', 'Site', 'WhatsApp', 'Facebook', 'Instagram']
        if dados['origem'] not in origens_validas:
            return _erro(f"origem inválida. Valores aceitos: {', '.join(origens_validas)}")
        l.origem = dados['origem']

    if 'status' in dados:
        status_validos = ['Novo', 'Qualificado', 'Arquivado', 'Perdido']
        if dados['status'] not in status_validos:
            return _erro(f"status inválido. Valores aceitos: {', '.join(status_validos)}")
        l.status = dados['status']

    for campo in ('email', 'mensagem', 'interesse_finalidade', 'interesse_cidade',
                  'interesse_bairros', 'interesse_quartos_min'):
        if campo in dados:
            setattr(l, campo, dados[campo])

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    for campo in ('interesse_preco_min', 'interesse_preco_max'):
        if campo in dados:
            setattr(l, campo, _num(dados[campo]))

    db.session.commit()
    return _ok(_serializar_lead(l), "Lead atualizado com sucesso.")


@api_bp.route('/leads/<int:id>', methods=['DELETE'])
@token_required
def excluir_lead(id):
    from ..models import Lead, db
    l = Lead.query.filter_by(id=id, imobiliaria_id=g.current_imob.id).first()
    if not l:
        return _erro("Lead não encontrado.", 404)
    db.session.delete(l)
    db.session.commit()
    return _ok(mensagem="Lead removido com sucesso.")
