"""
Webhook para integração com Evolution API (WhatsApp).
Gerencia estado de conversa em memória (substituível por Redis em produção).

Fluxo:
  INICIO → pede CPF → identifica/cadastra cliente → pede finalidade
  → coleta descrição → IA extrai dados → confirma → pede fotos → CONCLUIDO
"""
import os, uuid, json, requests as req
from flask import Blueprint, request, jsonify, current_app
from ..models import db, Imobiliaria, Pessoa, TelefonePessoa, Imovel, TipoImovel, Foto

whatsapp_bp = Blueprint('whatsapp', __name__)

# Estado de conversa em memória (use Redis em produção)
_conversas: dict[str, dict] = {}

ETAPAS = ['INICIO', 'CPF', 'NOME', 'FINALIDADE', 'DESCRICAO', 'CONFIRMACAO', 'FOTOS', 'CONCLUIDO']


def _estado(numero: str) -> dict:
    if numero not in _conversas:
        _conversas[numero] = {'etapa': 'INICIO', 'dados': {}, 'msgs': []}
    return _conversas[numero]


def _enviar(numero: str, texto: str, imob: Imobiliaria):
    """Envia mensagem de texto via Evolution API."""
    base = current_app.config.get('EVOLUTION_API_URL', '').rstrip('/')
    key  = current_app.config.get('EVOLUTION_API_KEY', '')
    inst = current_app.config.get('EVOLUTION_INSTANCE', '')
    if not base or not inst:
        current_app.logger.warning('Evolution API não configurada.')
        return
    try:
        req.post(
            f'{base}/message/sendText/{inst}',
            headers={'apikey': key, 'Content-Type': 'application/json'},
            json={'number': numero, 'text': texto},
            timeout=10,
        )
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar WhatsApp: {e}')


def _baixar_midia(url: str, destino: str):
    """Baixa arquivo de mídia da Evolution API e salva localmente."""
    key = current_app.config.get('EVOLUTION_API_KEY', '')
    try:
        r = req.get(url, headers={'apikey': key}, timeout=30)
        if r.status_code == 200:
            with open(destino, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        current_app.logger.error(f'Erro ao baixar mídia: {e}')
    return False


def _extrair_ia(texto: str, imob_id: int) -> dict:
    """Reutiliza a função de extração do blueprint cliente."""
    from ..cliente.routes import _extrair_imovel_ia
    return _extrair_imovel_ia(texto, imob_id)


def _resolver_imob(numero: str) -> Imobiliaria | None:
    """Tenta encontrar a imobiliária pelo estado da conversa ou pelo host."""
    conv = _estado(numero)
    imob_id = conv.get('imob_id')
    if imob_id:
        return Imobiliaria.query.get(imob_id)
    return None


def _processar(numero: str, tipo_msg: str, conteudo: str, media_url: str | None,
               imob: Imobiliaria):
    conv  = _estado(numero)
    etapa = conv['etapa']
    dados = conv['dados']

    def responder(txt):
        _enviar(numero, txt, imob)

    def avancar(nova_etapa):
        conv['etapa'] = nova_etapa

    # ── INICIO ────────────────────────────────────────────────────────────────
    if etapa == 'INICIO':
        conv['imob_id'] = imob.id
        responder(
            f'Olá! Bem-vindo à *{imob.nome}*.\n\n'
            'Vou te ajudar a cadastrar seu imóvel em poucos passos.\n\n'
            'Para começar, me informe seu *CPF* (somente números):'
        )
        avancar('CPF')
        return

    # ── CPF ───────────────────────────────────────────────────────────────────
    if etapa == 'CPF':
        from ..cliente.routes import _validar_cpf
        cpf = _validar_cpf(conteudo)
        if not cpf:
            responder('CPF inválido. Por favor, informe apenas os 11 dígitos do seu CPF:')
            return
        dados['cpf'] = cpf
        pessoa = Pessoa.query.filter_by(imobiliaria_id=imob.id, documento=cpf).first()
        if pessoa:
            dados['pessoa_id'] = pessoa.id
            responder(
                f'Olá, *{pessoa.nome.split()[0]}*! Que bom ter você aqui 😊\n\n'
                'Você deseja anunciar o imóvel para:\n'
                '1️⃣ Venda\n2️⃣ Locação\n3️⃣ Venda e Locação\n\n'
                'Responda com o número da opção:'
            )
            avancar('FINALIDADE')
        else:
            responder(
                'Não encontrei seu cadastro. Qual é o seu *nome completo*?'
            )
            avancar('NOME')
        return

    # ── NOME ──────────────────────────────────────────────────────────────────
    if etapa == 'NOME':
        nome = conteudo.strip().title()
        if len(nome) < 3:
            responder('Por favor, informe seu nome completo:')
            return
        dados['nome'] = nome
        pessoa = Pessoa(
            imobiliaria_id=imob.id,
            nome=nome,
            documento=dados['cpf'],
            tipo='Proprietário',
        )
        db.session.add(pessoa)
        db.session.flush()
        db.session.add(TelefonePessoa(pessoa_id=pessoa.id, numero=numero))
        db.session.commit()
        dados['pessoa_id'] = pessoa.id
        responder(
            f'Cadastro realizado, *{nome.split()[0]}*! ✅\n\n'
            'Você deseja anunciar o imóvel para:\n'
            '1️⃣ Venda\n2️⃣ Locação\n3️⃣ Venda e Locação\n\n'
            'Responda com o número da opção:'
        )
        avancar('FINALIDADE')
        return

    # ── FINALIDADE ────────────────────────────────────────────────────────────
    if etapa == 'FINALIDADE':
        mapa = {'1': 'Venda', '2': 'Locação', '3': 'Venda e Locação',
                'venda': 'Venda', 'locacao': 'Locação', 'locação': 'Locação',
                'aluguel': 'Locação', 'alugar': 'Locação'}
        finalidade = mapa.get(conteudo.strip().lower())
        if not finalidade:
            responder('Responda com 1 (Venda), 2 (Locação) ou 3 (Venda e Locação):')
            return
        dados['finalidade'] = finalidade
        responder(
            'Perfeito! Agora me descreva o imóvel com o máximo de detalhes:\n\n'
            '_Exemplo: Casa com 3 quartos, 1 suíte, 2 banheiros, sala, cozinha, '
            '150m² construídos, 200m² de terreno, garagem para 2 carros, em São Paulo-SP._'
        )
        avancar('DESCRICAO')
        return

    # ── DESCRICAO ─────────────────────────────────────────────────────────────
    if etapa == 'DESCRICAO':
        # Acumula mensagens de descrição
        dados.setdefault('descricao_raw', '')
        dados['descricao_raw'] += ' ' + conteudo

        responder('⏳ Analisando a descrição com IA, aguarde um momento...')

        extraido = _extrair_ia(dados['descricao_raw'], imob.id)
        dados['extraido'] = extraido

        if not extraido or 'erro' in extraido:
            responder(
                'Não consegui extrair as informações. '
                'Tente descrever novamente com mais detalhes:'
            )
            return

        resumo = (
            f'✅ *Dados identificados:*\n\n'
            f'📍 Tipo: {extraido.get("tipo", "-")}\n'
            f'📌 Finalidade: {dados["finalidade"]}\n'
            f'🏙️ Cidade: {extraido.get("cidade", "-")} / {extraido.get("estado", "-")}\n'
            f'🛏️ Quartos: {extraido.get("quartos", 0)} '
            f'(suítes: {extraido.get("suites", 0)})\n'
            f'🚿 Banheiros: {extraido.get("banheiros", 0)}\n'
            f'🚗 Vagas: {extraido.get("vagas", 0)}\n'
            f'📐 Área construída: {extraido.get("area_construida", "-")} m²\n'
            f'📐 Área terreno: {extraido.get("area_terreno", "-")} m²\n'
        )
        if extraido.get('preco'):
            resumo += f'💰 Preço: R$ {extraido["preco"]:,.0f}\n'

        resumo += '\nAs informações estão corretas?\n*1 - Sim, continuar*\n*2 - Não, descrever novamente*'
        responder(resumo)
        avancar('CONFIRMACAO')
        return

    # ── CONFIRMACAO ───────────────────────────────────────────────────────────
    if etapa == 'CONFIRMACAO':
        resp = conteudo.strip().lower()
        if resp in ('2', 'não', 'nao', 'n', 'corrigir'):
            dados.pop('descricao_raw', None)
            dados.pop('extraido', None)
            responder('Ok! Me descreva novamente o imóvel com as correções:')
            avancar('DESCRICAO')
            return

        # Salva o imóvel
        extraido = dados.get('extraido', {})
        tipo_nome = extraido.get('tipo', '')
        tipo = TipoImovel.query.filter_by(imobiliaria_id=imob.id, nome=tipo_nome).first()
        if not tipo:
            tipo = TipoImovel.query.filter_by(imobiliaria_id=imob.id).first()

        if not tipo:
            responder('Erro: nenhum tipo de imóvel cadastrado. Contate a imobiliária.')
            return

        imovel = Imovel(
            imobiliaria_id=imob.id,
            tipo_id=tipo.id,
            titulo=extraido.get('titulo') or f'{tipo_nome} para {dados["finalidade"]}',
            finalidade=dados['finalidade'],
            cidade=extraido.get('cidade', '')[:100],
            estado=extraido.get('estado', '')[:2],
            bairro=extraido.get('bairro', '')[:100],
            logradouro=extraido.get('logradouro', '')[:200],
            cep=extraido.get('cep', '')[:10],
            quartos=int(extraido.get('quartos') or 0),
            suites=int(extraido.get('suites') or 0),
            banheiros=int(extraido.get('banheiros') or 0),
            vagas=int(extraido.get('vagas') or 0),
            area_construida=extraido.get('area_construida') or None,
            area_terreno=extraido.get('area_terreno') or None,
            preco=extraido.get('preco') or None,
            descricao=extraido.get('descricao') or dados.get('descricao_raw', ''),
        )
        db.session.add(imovel)
        db.session.commit()
        dados['imovel_id'] = imovel.id

        responder(
            '🎉 Imóvel cadastrado!\n\n'
            'Agora envie as *fotos do imóvel* pelo WhatsApp.\n'
            'Quando terminar de enviar todas as fotos, escreva *"pronto"*.'
        )
        avancar('FOTOS')
        return

    # ── FOTOS ─────────────────────────────────────────────────────────────────
    if etapa == 'FOTOS':
        if conteudo.strip().lower() in ('pronto', 'ok', 'fim', 'finalizar', 'concluir'):
            total = dados.get('fotos_count', 0)
            responder(
                f'✅ *Cadastro concluído com sucesso!*\n\n'
                f'Recebemos {total} foto(s) do seu imóvel.\n'
                'Nossa equipe analisará as informações e entrará em contato em breve.\n\n'
                f'Obrigado por escolher a *{imob.nome}*! 🏠'
            )
            avancar('CONCLUIDO')
            _conversas.pop(numero, None)
            return

        if tipo_msg == 'image' and media_url:
            imovel_id = dados.get('imovel_id')
            if imovel_id:
                upload_dir = os.path.join(
                    'app', 'static', 'uploads', str(imob.id), 'imoveis', str(imovel_id)
                )
                os.makedirs(upload_dir, exist_ok=True)
                nome_arquivo = f'{uuid.uuid4().hex}.jpg'
                caminho = os.path.join(upload_dir, nome_arquivo)
                if _baixar_midia(media_url, caminho):
                    count = dados.get('fotos_count', 0)
                    db.session.add(Foto(
                        imovel_id=imovel_id,
                        url=f'uploads/{imob.id}/imoveis/{imovel_id}/{nome_arquivo}',
                        principal=(count == 0),
                    ))
                    db.session.commit()
                    dados['fotos_count'] = count + 1
                    responder(f'📸 Foto {count + 1} recebida! Envie mais ou escreva *"pronto"* para finalizar.')
        return


# ── WEBHOOK ───────────────────────────────────────────────────────────────────

@whatsapp_bp.route('/webhook/whatsapp', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'servico': 'ImobiConectaJa WhatsApp Webhook'})

    payload = request.get_json(silent=True) or {}
    current_app.logger.debug(f'WA webhook: {json.dumps(payload)[:500]}')

    try:
        evento = payload.get('event', '')
        if evento not in ('messages.upsert', 'message'):
            return jsonify({'ok': True})

        msg_data = payload.get('data', {})
        key      = msg_data.get('key', {})
        from_me  = key.get('fromMe', False)
        if from_me:
            return jsonify({'ok': True})

        numero   = key.get('remoteJid', '').split('@')[0]
        msg_obj  = msg_data.get('message', {})

        tipo_msg  = 'text'
        conteudo  = ''
        media_url = None

        if 'conversation' in msg_obj:
            conteudo = msg_obj['conversation']
        elif 'extendedTextMessage' in msg_obj:
            conteudo = msg_obj['extendedTextMessage'].get('text', '')
        elif 'imageMessage' in msg_obj:
            tipo_msg  = 'image'
            media_url = msg_obj['imageMessage'].get('url')
            conteudo  = msg_obj['imageMessage'].get('caption', '')
        elif 'documentMessage' in msg_obj:
            tipo_msg = 'document'
            conteudo = msg_obj['documentMessage'].get('caption', '')

        # Resolve a imobiliária pelo token do webhook (header ou query param)
        token = (request.headers.get('X-Imob-Token')
                 or request.args.get('token', ''))
        imob = Imobiliaria.query.filter_by(api_token=token, ativo=True).first()

        if not imob:
            conv = _estado(numero)
            imob_id = conv.get('imob_id')
            imob = Imobiliaria.query.get(imob_id) if imob_id else None

        if not imob:
            return jsonify({'ok': True, 'aviso': 'imobiliária não identificada'})

        _processar(numero, tipo_msg, conteudo, media_url, imob)

    except Exception as e:
        current_app.logger.error(f'Erro no webhook WhatsApp: {e}', exc_info=True)

    return jsonify({'ok': True})
