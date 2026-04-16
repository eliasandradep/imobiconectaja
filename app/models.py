from . import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Imobiliaria(db.Model):
    __tablename__ = 'imobiliarias'
    id         = db.Column(db.Integer, primary_key=True)
    nome       = db.Column(db.String(100), nullable=False)
    dominio    = db.Column(db.String(100), unique=True, nullable=False)
    api_token  = db.Column(db.String(100), unique=True, nullable=False)
    ativo                 = db.Column(db.Boolean, default=True)
    plano                 = db.Column(db.String(30),  default='basico')
    criado_em             = db.Column(db.DateTime,    default=datetime.utcnow)
    # Domínios
    slug                  = db.Column(db.String(80),  unique=True)   # ex: "imob-master" → imob-master.imobiconectaja.com.br
    dominio_personalizado = db.Column(db.String(255))                # ex: "www.imobiliaria.com.br"
    tema_ativo     = db.Column(db.String(50),  default='clean')
    logo_url       = db.Column(db.String(255))
    whatsapp       = db.Column(db.String(20))
    layout_banner  = db.Column(db.String(20),  default='fullscreen')
    layout_busca   = db.Column(db.String(20),  default='abaixo')
    layout_grid    = db.Column(db.String(5),   default='3')
    layout_logo    = db.Column(db.String(20),  default='esquerda')
    # Configurações gerais
    email_contato      = db.Column(db.String(120))   # recebe leads/mensagens
    email_exibicao     = db.Column(db.String(120))   # exibido no site
    telefone           = db.Column(db.String(30))    # telefone fixo no rodapé
    slogan             = db.Column(db.String(200))   # texto do rodapé/hero
    ordenacao_imoveis  = db.Column(db.String(20),  default='recentes')  # recentes|destaque|preco_asc|preco_desc
    imoveis_por_pagina = db.Column(db.Integer,     default=9)

    usuarios     = db.relationship('Usuario',    backref='imobiliaria', lazy=True)
    imoveis      = db.relationship('Imovel',     backref='imobiliaria', lazy=True)
    tipos_imovel = db.relationship('TipoImovel', backref='imobiliaria', lazy=True)
    leads        = db.relationship('Lead',       backref='imobiliaria', lazy=True)
    banners      = db.relationship('BannerSite', backref='imobiliaria', lazy=True,
                                   order_by='BannerSite.ordem')
    paginas      = db.relationship('PaginaSite', backref='imobiliaria', lazy=True,
                                   order_by='PaginaSite.ordem')
    menu_links   = db.relationship('MenuLink',   backref='imobiliaria', lazy=True,
                                   order_by='MenuLink.ordem')
    pessoas      = db.relationship('Pessoa',     backref='imobiliaria', lazy=True)


class TipoImovel(db.Model):
    __tablename__ = 'tipos_imovel'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    nome           = db.Column(db.String(50), nullable=False)
    prefixo        = db.Column(db.String(5),  nullable=False)


class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    nome           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash     = db.Column(db.String(256))

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Imovel(db.Model):
    __tablename__ = 'imoveis'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    tipo_id        = db.Column(db.Integer, db.ForeignKey('tipos_imovel.id'), nullable=False)

    # Identificação
    codigo_ref = db.Column(db.String(20))
    titulo     = db.Column(db.String(200), nullable=False)
    finalidade = db.Column(db.String(30))   # Venda | Locação | Venda e Locação

    # Localização
    cep         = db.Column(db.String(10))
    logradouro  = db.Column(db.String(200))
    numero      = db.Column(db.String(10))
    complemento = db.Column(db.String(60))
    bairro      = db.Column(db.String(100))
    cidade      = db.Column(db.String(100))
    estado      = db.Column(db.String(2))

    # Valores
    preco            = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    valor_condominio = db.Column(db.Numeric(14, 2), default=0)
    valor_iptu       = db.Column(db.Numeric(14, 2), default=0)

    # Medidas
    area_util  = db.Column(db.Float, default=0)
    area_total = db.Column(db.Float, default=0)

    # Características
    quartos   = db.Column(db.Integer, default=0)
    suites    = db.Column(db.Integer, default=0)
    banheiros = db.Column(db.Integer, default=0)
    vagas     = db.Column(db.Integer, default=0)

    # Conteúdo
    descricao = db.Column(db.Text)
    destaque  = db.Column(db.Boolean, default=False)

    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)

    fotos = db.relationship('Foto',      backref='imovel',            lazy=True,
                            cascade="all, delete-orphan")
    tipo  = db.relationship('TipoImovel', backref='imoveis_deste_tipo', lazy=True)


class Foto(db.Model):
    __tablename__ = 'fotos'
    id          = db.Column(db.Integer, primary_key=True)
    imovel_id   = db.Column(db.Integer, db.ForeignKey('imoveis.id'), nullable=False)
    url         = db.Column(db.String(255), nullable=False)
    principal   = db.Column(db.Boolean, default=False)
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)


TIPOS_PESSOA    = ['Cliente', 'Corretor', 'Proprietário', 'Locatário', 'Interessado', 'Outro']
TIPOS_TELEFONE  = ['Celular', 'WhatsApp', 'Fixo', 'Comercial']


class Pessoa(db.Model):
    __tablename__ = 'pessoas'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    tipo           = db.Column(db.String(20), default='Cliente')
    nome           = db.Column(db.String(150), nullable=False)
    documento      = db.Column(db.String(20))
    email          = db.Column(db.String(120))
    data_nascimento= db.Column(db.Date)
    # Endereço
    cep            = db.Column(db.String(10))
    logradouro     = db.Column(db.String(200))
    numero         = db.Column(db.String(10))
    complemento    = db.Column(db.String(60))
    bairro         = db.Column(db.String(100))
    cidade         = db.Column(db.String(100))
    estado         = db.Column(db.String(2))
    observacoes    = db.Column(db.Text)
    data_cadastro  = db.Column(db.DateTime, default=datetime.utcnow)

    telefones = db.relationship('TelefonePessoa', backref='pessoa', lazy=True,
                                cascade='all, delete-orphan', order_by='TelefonePessoa.id')
    leads     = db.relationship('Lead', backref='pessoa', lazy=True,
                                foreign_keys='Lead.pessoa_id')


class TelefonePessoa(db.Model):
    __tablename__ = 'telefones_pessoa'
    id        = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('pessoas.id'), nullable=False)
    numero    = db.Column(db.String(20), nullable=False)
    tipo      = db.Column(db.String(20), default='Celular')  # Celular|WhatsApp|Fixo|Comercial


class Lead(db.Model):
    __tablename__ = 'leads'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    pessoa_id      = db.Column(db.Integer, db.ForeignKey('pessoas.id'), nullable=True)

    # Dados do contato
    nome     = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20),  nullable=False)
    email    = db.Column(db.String(120))

    # Classificação
    # Origens válidas: Manual | Site | WhatsApp | Facebook | Instagram
    origem  = db.Column(db.String(30), default='Manual')
    # Status válidos:  Novo | Qualificado | Arquivado | Perdido
    status  = db.Column(db.String(30), default='Novo')

    # Conteúdo
    mensagem = db.Column(db.Text)

    # Perfil de busca (interesse do lead)
    interesse_finalidade  = db.Column(db.String(30))   # Compra | Locação | Ambos
    interesse_preco_min   = db.Column(db.Numeric(14, 2))
    interesse_preco_max   = db.Column(db.Numeric(14, 2))
    interesse_quartos_min = db.Column(db.Integer)
    interesse_cidade      = db.Column(db.String(100))
    interesse_bairros     = db.Column(db.String(500))

    data_contato = db.Column(db.DateTime, default=datetime.utcnow)


class SuperAdmin(db.Model, UserMixin):
    """Usuário da plataforma ImobiConectaJa — gerencia todas as imobiliárias."""
    __tablename__ = 'superadmins'
    id         = db.Column(db.Integer, primary_key=True)
    nome       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256))
    criado_em  = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        # Prefixo 'sa:' para distinguir do user_loader de Usuario
        return f"sa:{self.id}"

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_superadmin(self):
        return True


class BannerSite(db.Model):
    __tablename__ = 'banners_site'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    url_imagem     = db.Column(db.String(255), nullable=False)
    titulo         = db.Column(db.String(100))
    subtitulo      = db.Column(db.String(200))
    ordem          = db.Column(db.Integer, default=0)


class PaginaSite(db.Model):
    """Páginas do site público (institucionais pré-definidas + páginas extras criadas pelo usuário)."""
    __tablename__ = 'paginas_site'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    tipo           = db.Column(db.String(20), default='custom')   # 'institucional' | 'custom'
    slug           = db.Column(db.String(100), nullable=False)
    titulo         = db.Column(db.String(200), nullable=False)
    conteudo       = db.Column(db.Text)
    ativo          = db.Column(db.Boolean, default=True)
    no_menu        = db.Column(db.Boolean, default=False)
    ordem          = db.Column(db.Integer, default=0)


class ImoveCompativel(db.Model):
    """Relação entre um Lead e um Imóvel — resultado do cruzamento de perfil de busca."""
    __tablename__ = 'imoveis_compativeis'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    lead_id        = db.Column(db.Integer, db.ForeignKey('leads.id'),        nullable=False)
    imovel_id      = db.Column(db.Integer, db.ForeignKey('imoveis.id'),      nullable=False)
    # 'compativel' | 'favorito' | 'descartado'
    status         = db.Column(db.String(20), default='compativel', nullable=False)
    email_enviado  = db.Column(db.Boolean, default=False, nullable=False)
    criado_em      = db.Column(db.DateTime, default=datetime.utcnow)

    lead   = db.relationship('Lead',   backref='compativeis', lazy=True)
    imovel = db.relationship('Imovel', backref='compativeis', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('lead_id', 'imovel_id', name='uq_lead_imovel'),
    )


class MenuLink(db.Model):
    """Links exibidos no menu de navegação do site público."""
    __tablename__ = 'menu_links'
    id             = db.Column(db.Integer, primary_key=True)
    imobiliaria_id = db.Column(db.Integer, db.ForeignKey('imobiliarias.id'), nullable=False)
    label          = db.Column(db.String(100), nullable=False)
    url            = db.Column(db.String(255), nullable=False)
    ordem          = db.Column(db.Integer, default=0)
    ativo          = db.Column(db.Boolean, default=True)
    abre_nova_aba  = db.Column(db.Boolean, default=False)