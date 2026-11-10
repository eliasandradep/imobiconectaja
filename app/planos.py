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
