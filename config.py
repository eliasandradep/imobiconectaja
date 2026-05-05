import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'chave-secreta-muito-dificil'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///imobiconectaja.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False  # Permite acentos no JSON da API

    # Domínio base da plataforma (sem http://).
    # Se definido, subdomínios no formato slug.BASE_DOMAIN são roteados automaticamente.
    # Exemplo: "imobiconectaja.com.br"  →  minha-imob.imobiconectaja.com.br
    BASE_DOMAIN = os.environ.get('BASE_DOMAIN', '').strip().lower().lstrip('.')

    # Hosts que pertencem à própria plataforma (não são sites de imobiliárias)
    PLATFORM_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0'}

    # ── Configurações de E-mail (Flask-Mail) ────────────────────────
    # Defina via .env: MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD,
    #                  MAIL_USE_TLS, MAIL_DEFAULT_SENDER
    MAIL_SERVER   = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
    MAIL_PORT     = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS  = os.environ.get('MAIL_USE_TLS',  'true').lower() == 'true'
    MAIL_USE_SSL  = os.environ.get('MAIL_USE_SSL',  'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    # ── IA — Claude API (Anthropic) ─────────────────────────────────
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    # ── WhatsApp — Evolution API ────────────────────────────────────
    EVOLUTION_API_URL  = os.environ.get('EVOLUTION_API_URL', '')
    EVOLUTION_API_KEY  = os.environ.get('EVOLUTION_API_KEY', '')
    EVOLUTION_INSTANCE = os.environ.get('EVOLUTION_INSTANCE', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)