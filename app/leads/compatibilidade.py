"""
Regra de negócio: cruzamento do perfil de busca do lead com o catálogo.

Um imóvel é compatível quando atende a TODOS os critérios preenchidos no perfil
(critério vazio não filtra):

  finalidade   Compra → Venda | Venda e Locação ; Locação → Locação | Venda e Locação
               Ambos/vazio + faixa de preço → a finalidade é deduzida pelo valor
               (até LIMITE_ALUGUEL = aluguel mensal; acima = valor de venda)
  tipo         mesmo tipo de imóvel
  preço        dentro da faixa mínima/máxima
  quartos      quartos >= mínimo
  cidade       contém o texto informado (sem diferenciar maiúsculas)
  bairros      contém ALGUM dos bairros informados (separados por vírgula ou ;)

Leads Arquivados ou Perdidos não recebem compatíveis.
"""
import re

from .. import db
from ..models import Imovel

LIMITE_ALUGUEL = 30000          # R$ — valores até aqui são tratados como aluguel mensal
STATUS_INATIVOS = ('Arquivado', 'Perdido')


def bairros_do_lead(lead):
    if not lead.interesse_bairros:
        return []
    return [b.strip() for b in re.split(r'[,;]', lead.interesse_bairros) if b.strip()]


def lead_tem_perfil(lead):
    return any([
        lead.interesse_finalidade, lead.interesse_tipo_id,
        lead.interesse_preco_min, lead.interesse_preco_max,
        lead.interesse_quartos_min, lead.interesse_cidade,
        bairros_do_lead(lead),
    ])


def lead_ativo(lead):
    return lead.status not in STATUS_INATIVOS


def finalidade_efetiva(lead):
    """'Compra', 'Locação' ou None (qualquer finalidade)."""
    fin = lead.interesse_finalidade
    if fin in ('Compra', 'Locação'):
        return fin
    referencia = lead.interesse_preco_max or lead.interesse_preco_min
    if referencia:
        return 'Locação' if referencia <= LIMITE_ALUGUEL else 'Compra'
    return None


def query_compativeis(lead):
    """Query dos imóveis da imobiliária do lead que atendem ao perfil de busca."""
    query = Imovel.query.filter_by(imobiliaria_id=lead.imobiliaria_id)

    fin = {'Compra': 'Venda', 'Locação': 'Locação'}.get(finalidade_efetiva(lead))
    if fin:
        query = query.filter(db.or_(Imovel.finalidade == fin,
                                    Imovel.finalidade == 'Venda e Locação'))
    if lead.interesse_tipo_id:
        query = query.filter(Imovel.tipo_id == lead.interesse_tipo_id)
    if lead.interesse_preco_min:
        query = query.filter(Imovel.preco >= lead.interesse_preco_min)
    if lead.interesse_preco_max:
        query = query.filter(Imovel.preco <= lead.interesse_preco_max)
    if lead.interesse_quartos_min:
        query = query.filter(Imovel.quartos >= lead.interesse_quartos_min)
    if lead.interesse_cidade:
        query = query.filter(Imovel.cidade.ilike(f'%{lead.interesse_cidade.strip()}%'))
    bairros = bairros_do_lead(lead)
    if bairros:
        query = query.filter(db.or_(*[Imovel.bairro.ilike(f'%{b}%') for b in bairros]))
    return query
