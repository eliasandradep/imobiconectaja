"""
seed.py — Script de inicialização do banco de dados ImobiConectaJa.
Execute UMA vez após apagar o instance/imobiconectaja.db:

    python seed.py
"""
from app import create_app, db
from app.models import Imobiliaria, Usuario, TipoImovel, Lead
import uuid
from datetime import datetime, timedelta
import random

app = create_app()

with app.app_context():
    print("🔄 Resetando banco de dados...")
    db.drop_all()
    db.create_all()

    # ── 1. Imobiliária ────────────────────────────────────────────
    imob = Imobiliaria(
        nome="Imobiliária Master",
        dominio="127.0.0.1",
        api_token=str(uuid.uuid4())
    )
    db.session.add(imob)
    db.session.commit()
    print(f"✅ Imobiliária criada: {imob.nome}  (token API: {imob.api_token})")

    # ── 2. Usuário admin ──────────────────────────────────────────
    user = Usuario(
        imobiliaria_id=imob.id,
        nome="Administrador",
        email="admin@teste.com"
    )
    user.set_senha("123456")
    db.session.add(user)

    # ── 3. Tipos de imóvel ────────────────────────────────────────
    tipos_base = [
        ("Casa",        "CA"),
        ("Apartamento", "AP"),
        ("Terreno",     "TE"),
        ("Sobrado",     "SO"),
        ("Comercial",   "CO"),
        ("Galpão",      "GA"),
    ]
    for nome, prefixo in tipos_base:
        db.session.add(TipoImovel(
            imobiliaria_id=imob.id,
            nome=nome,
            prefixo=prefixo
        ))

    # ── 4. Leads de exemplo ───────────────────────────────────────
    origens   = ['Manual', 'Site', 'WhatsApp', 'Facebook', 'Instagram']
    status    = ['Novo', 'Novo', 'Novo', 'Qualificado', 'Arquivado']
    exemplos  = [
        ("Carlos Mendes",      "11987654321", "carlos@email.com",   "WhatsApp", "Novo",        "Interesse em apartamentos de 2 quartos no Centro"),
        ("Ana Paula Souza",    "11976543210", "ana@email.com",      "Site",     "Qualificado", "Procura casa com piscina, até R$ 800.000"),
        ("Roberto Lima",       "11965432109", None,                 "Instagram","Novo",        None),
        ("Fernanda Costa",     "11954321098", "fe@empresa.com.br",  "Facebook", "Novo",        "Apartamento para locação, 1 quarto"),
        ("Marcos Oliveira",    "11943210987", None,                 "Manual",   "Arquivado",   "Não respondeu após 3 tentativas de contato"),
        ("Juliana Barbosa",    "11932109876", "ju.barb@gmail.com",  "WhatsApp", "Novo",        "Interessada em imóvel comercial no centro"),
        ("Pedro Alves",        "11921098765", "pedro@email.com",    "Site",     "Qualificado", "Quer imóvel próximo a escolas, 3 quartos, garagem"),
    ]
    for nome, tel, email, origem, st, msg in exemplos:
        dias_atras = random.randint(0, 30)
        db.session.add(Lead(
            imobiliaria_id=imob.id,
            nome=nome,
            telefone=tel,
            email=email,
            origem=origem,
            status=st,
            mensagem=msg,
            data_contato=datetime.utcnow() - timedelta(days=dias_atras)
        ))

    db.session.commit()

    print("✅ Tipos de imóvel criados:", ", ".join(n for n, _ in tipos_base))
    print(f"✅ {len(exemplos)} leads de exemplo inseridos")
    print()
    print("═" * 50)
    print("  ACESSO AO SISTEMA")
    print("═" * 50)
    print(f"  URL:   http://127.0.0.1:5000/auth/login")
    print(f"  Email: admin@teste.com")
    print(f"  Senha: 123456")
    print("═" * 50)