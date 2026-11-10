"""
Recursos liberados por plano (PLANOS_CONFIG em superadmin/routes.py).

Use plano_permite(imob, 'chatbot') antes de liberar recursos pagos.
"""

# Valores antigos gravados no banco → chave atual do PLANOS_CONFIG
_ALIASES = {'basico': 'basic', 'básico': 'basic', 'padrao': 'standard', 'padrão': 'standard'}


def plano_da(imob):
    from .superadmin.routes import PLANOS_CONFIG
    chave = (getattr(imob, 'plano', None) or 'basic').strip().lower()
    chave = _ALIASES.get(chave, chave)
    return PLANOS_CONFIG.get(chave, PLANOS_CONFIG['basic'])


def plano_permite(imob, recurso):
    return bool(imob) and bool(plano_da(imob).get(recurso))


# ── Créditos de IA ───────────────────────────────────────────────────────────
# Extração de imóveis por IA (bot de WhatsApp e portal do proprietário):
#  - imobiliária com chave Anthropic própria → usa a chave dela, sem limite;
#  - sem chave própria → usa a chave da plataforma e consome 1 crédito por
#    extração, até o limite mensal 'ia_creditos' do plano.

def _mes_atual():
    from datetime import datetime
    return datetime.utcnow().strftime('%Y-%m')


def creditos_ia_usados(imob):
    from .models import UsoIA
    uso = UsoIA.query.filter_by(imobiliaria_id=imob.id, mes=_mes_atual()).first()
    return uso.usos if uso else 0


def chave_ia(imob):
    """
    Retorna (api_key, consome_credito) ou (None, motivo) se não houver IA disponível.
    """
    import os
    from flask import current_app
    if getattr(imob, 'anthropic_api_key', None):
        return imob.anthropic_api_key, False
    chave = current_app.config.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not chave:
        return None, 'IA não configurada para esta imobiliária.'
    limite = plano_da(imob).get('ia_creditos', 0)
    if creditos_ia_usados(imob) >= limite:
        return None, ('Limite mensal de créditos de IA do plano atingido. '
                      'Fale com a imobiliária para concluir o cadastro.')
    return chave, True


def consumir_credito_ia(imob):
    from .models import UsoIA, db
    uso = UsoIA.query.filter_by(imobiliaria_id=imob.id, mes=_mes_atual()).first()
    if not uso:
        uso = UsoIA(imobiliaria_id=imob.id, mes=_mes_atual(), usos=0)
        db.session.add(uso)
    uso.usos += 1
    db.session.commit()
