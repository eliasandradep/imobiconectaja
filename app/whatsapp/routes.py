"""
Webhook para integração com Evolution API (WhatsApp).

Isolamento por imobiliária (tenant):
  - cada imobiliária tem a própria instância/número na Evolution
    (evolution_instance / evolution_apikey / evolution_url);
  - o webhook de cada instância aponta para /webhook/whatsapp/<webhook_token>,
    um token exclusivo do webhook (não é o token da API REST);
  - o estado da conversa fica no banco (ConversaBot), por imobiliária + telefone.

Fluxo:
  INICIO → pede CPF → identifica/cadastra cliente → pede finalidade
  → coleta descrição → IA extrai dados → confirma → pede fotos → CONCLUIDO
"""
import base64, json, os, uuid
from datetime import datetime, timedelta

import requests as req
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.exc import IntegrityError

from ..models import db, Imobiliaria, Pessoa, TelefonePessoa, Foto, ConversaBot

whatsapp_bp = Blueprint('whatsapp', __name__)

ETAPAS = ['INICIO', 'CPF', 'NOME', 'FINALIDADE', 'DESCRICAO', 'CONFIRMACAO', 'FOTOS', 'CONCLUIDO']

# Conversa parada há mais tempo que isso recomeça do início
EXPIRACAO_CONVERSA = timedelta(hours=24)


# ── Evolution API (sempre com a instância da imobiliária) ────────────────────

def _evolution(imob: Imobiliaria):
    """(url_base, instancia, apikey) da imobiliária, ou None se não configurada."""
    base = (imob.evolution_url or current_app.config.get('EVOLUTION_API_URL', '')).rstrip('/')
    if not base or not imob.evolution_instance or not imob.evolution_apikey:
        return None
    return base, imob.evolution_instance, imob.evolution_apikey


def _enviar(numero: str, texto: str, imob: Imobiliaria):
    """Envia mensagem de texto pelo número da própria imobiliária."""
    cfg = _evolution(imob)
    if not cfg:
        current_app.logger.warning(f'Evolution não configurada para a imobiliária {imob.id}.')
        return
    base, inst, key = cfg
    try:
        req.post(
            f'{base}/message/sendText/{inst}',
            headers={'apikey': key, 'Content-Type': 'application/json'},
            json={'number': numero, 'text': texto},
            timeout=10,
        )
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar WhatsApp (imobiliária {imob.id}): {e}')


def _baixar_midia(msg_data: dict, imob: Imobiliaria) -> bytes | None:
    """
    Obtém a imagem recebida. A URL da mídia do WhatsApp vem criptografada, então
    usa o base64 do webhook (se a instância envia) ou pede à Evolution o conteúdo
    já descriptografado (getBase64FromMediaMessage).
    """
    b64 = msg_data.get('message', {}).get('base64')
    if not b64:
        cfg = _evolution(imob)
        if not cfg:
            return None
        base, inst, key = cfg
        try:
            r = req.post(
                f'{base}/chat/getBase64FromMediaMessage/{inst}',
                headers={'apikey': key, 'Content-Type': 'application/json'},
                json={'message': {'key': msg_data.get('key', {})}, 'convertToMp4': False},
                timeout=30,
            )
            if r.status_code in (200, 201):
                b64 = r.json().get('base64')
        except Exception as e:
            current_app.logger.error(f'Erro ao baixar mídia (imobiliária {imob.id}): {e}')
    if not b64:
        return None
    try:
        return base64.b64decode(b64.split(',')[-1])
    except Exception:
        return None


def _extrair_ia(texto: str, imob_id: int) -> dict:
    """Reutiliza a função de extração do blueprint cliente."""
    from ..cliente.routes import _extrair_imovel_ia
    return _extrair_imovel_ia(texto, imob_id)


# ── Estado da conversa (banco, por imobiliária + telefone) ───────────────────

def _carregar_conversa(imob: Imobiliaria, numero: str) -> ConversaBot:
    conversa = ConversaBot.query.filter_by(imobiliaria_id=imob.id, telefone=numero).first()
    if conversa and conversa.atualizado_em and \
            datetime.utcnow() - conversa.atualizado_em > EXPIRACAO_CONVERSA:
        conversa.etapa, conversa.dados_json = 'INICIO', '{}'
    if not conversa:
        conversa = ConversaBot(imobiliaria_id=imob.id, telefone=numero,
                               etapa='INICIO', dados_json='{}')
        db.session.add(conversa)
        try:
            db.session.commit()
        except IntegrityError:          # duas mensagens simultâneas criaram a conversa
            db.session.rollback()
            conversa = ConversaBot.query.filter_by(imobiliaria_id=imob.id, telefone=numero).first()
    return conversa


def _salvar_conversa(conversa: ConversaBot, conv: dict):
    if conv['etapa'] == 'CONCLUIDO':
        db.session.delete(conversa)
    else:
        conversa.etapa = conv['etapa']
        conversa.dados_json = json.dumps(conv['dados'], ensure_ascii=False, default=str)
        conversa.atualizado_em = datetime.utcnow()
    db.session.commit()


# ── Máquina de estados ───────────────────────────────────────────────────────

def _processar(conv: dict, numero: str, tipo_msg: str, conteudo: str,
               msg_data: dict, imob: Imobiliaria):
    etapa = conv['etapa']
    dados = conv['dados']

    def responder(txt):
        _enviar(numero, txt, imob)

    def avancar(nova_etapa):
        conv['etapa'] = nova_etapa

    # ── INICIO ────────────────────────────────────────────────────────────────
    if etapa == 'INICIO':
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
        dados['descricao_raw'] = (dados.get('descricao_raw', '') + ' ' + conteudo).strip()

        responder('⏳ Analisando a descrição com IA, aguarde um momento...')

        extraido = _extrair_ia(dados['descricao_raw'], imob.id)
        dados['extraido'] = extraido

        if not extraido or 'erro' in extraido:
            responder(
                (extraido or {}).get('erro')
                or 'Não consegui extrair as informações. Tente descrever novamente com mais detalhes:'
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
            resumo += f'💰 Preço: R$ {float(extraido["preco"]):,.0f}\n'.replace(',', '.')

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

        # Salva o imóvel (entra como pendente de aprovação, ligado ao proprietário)
        from ..cliente.routes import criar_imovel_proprietario
        extraido = dict(dados.get('extraido', {}))
        extraido['finalidade'] = dados['finalidade']
        extraido['descricao'] = extraido.get('descricao') or dados.get('descricao_raw', '')
        imovel = criar_imovel_proprietario(imob, dados.get('pessoa_id'), extraido, origem='WhatsApp')
        if not imovel:
            responder('Erro: nenhum tipo de imóvel cadastrado. Contate a imobiliária.')
            return
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
        imovel_id = dados.get('imovel_id')

        if conteudo.strip().lower() in ('pronto', 'ok', 'fim', 'finalizar', 'concluir'):
            total = Foto.query.filter_by(imovel_id=imovel_id).count() if imovel_id else 0
            responder(
                f'✅ *Cadastro concluído com sucesso!*\n\n'
                f'Recebemos {total} foto(s) do seu imóvel.\n'
                'Nossa equipe analisará as informações e entrará em contato em breve.\n\n'
                f'Obrigado por escolher a *{imob.nome}*! 🏠'
            )
            avancar('CONCLUIDO')
            return

        if tipo_msg == 'image' and imovel_id:
            conteudo_img = _baixar_midia(msg_data, imob)
            if not conteudo_img:
                responder('Não consegui receber essa foto. Pode enviar novamente?')
                return
            upload_dir = os.path.join(
                current_app.root_path, 'static', 'uploads', str(imob.id), 'imoveis', str(imovel_id)
            )
            os.makedirs(upload_dir, exist_ok=True)
            nome_arquivo = f'{uuid.uuid4().hex}.jpg'
            with open(os.path.join(upload_dir, nome_arquivo), 'wb') as f:
                f.write(conteudo_img)
            ja_tem_fotos = Foto.query.filter_by(imovel_id=imovel_id).count() > 0
            db.session.add(Foto(
                imovel_id=imovel_id,
                url=f'uploads/{imob.id}/imoveis/{imovel_id}/{nome_arquivo}',
                principal=not ja_tem_fotos,
            ))
            db.session.commit()
            total = Foto.query.filter_by(imovel_id=imovel_id).count()
            responder(f'📸 Foto {total} recebida! Envie mais ou escreva *"pronto"* para finalizar.')
        return


# ── WEBHOOK ───────────────────────────────────────────────────────────────────

def _ler_mensagem(payload: dict):
    """Extrai (numero, tipo_msg, conteudo, msg_data) do evento da Evolution, ou None."""
    if payload.get('event', '') not in ('messages.upsert', 'message'):
        return None
    msg_data = payload.get('data', {}) or {}
    key = msg_data.get('key', {}) or {}
    if key.get('fromMe', False):
        return None
    jid = key.get('remoteJid', '')
    if not jid or jid.endswith('@g.us'):          # ignora grupos
        return None
    numero  = jid.split('@')[0]
    msg_obj = msg_data.get('message', {}) or {}

    tipo_msg, conteudo = 'text', ''
    if 'conversation' in msg_obj:
        conteudo = msg_obj['conversation']
    elif 'extendedTextMessage' in msg_obj:
        conteudo = msg_obj['extendedTextMessage'].get('text', '')
    elif 'imageMessage' in msg_obj:
        tipo_msg = 'image'
        conteudo = msg_obj['imageMessage'].get('caption', '')
    elif 'documentMessage' in msg_obj:
        tipo_msg = 'document'
        conteudo = msg_obj['documentMessage'].get('caption', '')
    return numero, tipo_msg, conteudo or '', msg_data


@whatsapp_bp.route('/webhook/whatsapp/<token>', methods=['GET', 'POST'])
def webhook(token):
    imob = Imobiliaria.query.filter_by(webhook_token=token, ativo=True).first() if token else None
    if not imob:
        return jsonify({'ok': False, 'erro': 'webhook inválido'}), 404

    if request.method == 'GET':
        return jsonify({'status': 'ok', 'servico': 'ImobiConectaJa WhatsApp Webhook',
                        'imobiliaria': imob.nome})

    from ..planos import plano_permite
    if not plano_permite(imob, 'chatbot'):
        return jsonify({'ok': True, 'aviso': 'plano sem atendimento por bot'})

    payload = request.get_json(silent=True) or {}

    # O evento precisa vir da instância desta imobiliária
    instancia = payload.get('instance')
    if instancia and imob.evolution_instance and instancia != imob.evolution_instance:
        current_app.logger.warning(
            f'Webhook da imobiliária {imob.id} recebeu evento da instância "{instancia}".')
        return jsonify({'ok': False, 'erro': 'instância não pertence a esta imobiliária'}), 403

    try:
        lido = _ler_mensagem(payload)
        if not lido:
            return jsonify({'ok': True})
        numero, tipo_msg, conteudo, msg_data = lido

        conversa = _carregar_conversa(imob, numero)
        conv = {'etapa': conversa.etapa, 'dados': json.loads(conversa.dados_json or '{}')}
        _processar(conv, numero, tipo_msg, conteudo, msg_data, imob)
        _salvar_conversa(conversa, conv)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Erro no webhook WhatsApp (imobiliária {imob.id}): {e}', exc_info=True)

    return jsonify({'ok': True})


@whatsapp_bp.route('/webhook/whatsapp', methods=['GET', 'POST'])
def webhook_legado():
    """
    Endereço antigo (identificava a imobiliária pelo token da API REST).
    Desativado: cada instância deve usar /webhook/whatsapp/<webhook_token>.
    """
    if request.method == 'POST':
        current_app.logger.warning('Evento recebido no webhook legado /webhook/whatsapp — ignorado.')
    return jsonify({'ok': False, 'erro': 'Use /webhook/whatsapp/<token> da imobiliária.'}), 410
