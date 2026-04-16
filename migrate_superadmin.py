"""
Migração: adiciona colunas ativo/plano/criado_em em imobiliarias e cria tabela superadmins.
Também cria o primeiro SuperAdmin se ainda não existir.

Execute: python migrate_superadmin.py
"""
import sqlite3, os
from datetime import datetime

DB_PATH   = os.path.join('instance', 'imobiconectaja.db')
SA_EMAIL  = os.environ.get('SA_EMAIL',  'admin@imobiconectaja.com.br')
SA_SENHA  = os.environ.get('SA_SENHA',  'admin123')
SA_NOME   = os.environ.get('SA_NOME',   'Super Admin')


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # ── Colunas em imobiliarias ────────────────────────────────────
    cur.execute("PRAGMA table_info(imobiliarias)")
    colunas = {r[1] for r in cur.fetchall()}

    if 'ativo' not in colunas:
        cur.execute("ALTER TABLE imobiliarias ADD COLUMN ativo BOOLEAN DEFAULT 1")
        cur.execute("UPDATE imobiliarias SET ativo = 1 WHERE ativo IS NULL")
        print("Coluna 'ativo' adicionada.")

    if 'plano' not in colunas:
        cur.execute("ALTER TABLE imobiliarias ADD COLUMN plano VARCHAR(30) DEFAULT 'basico'")
        cur.execute("UPDATE imobiliarias SET plano = 'basico' WHERE plano IS NULL")
        print("Coluna 'plano' adicionada.")

    if 'criado_em' not in colunas:
        cur.execute("ALTER TABLE imobiliarias ADD COLUMN criado_em DATETIME")
        cur.execute("UPDATE imobiliarias SET criado_em = ? WHERE criado_em IS NULL",
                    (datetime.utcnow().isoformat(),))
        print("Coluna 'criado_em' adicionada.")

    # ── Tabela superadmins ─────────────────────────────────────────
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='superadmins'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE superadmins (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                nome       VARCHAR(100) NOT NULL,
                email      VARCHAR(120) UNIQUE NOT NULL,
                senha_hash VARCHAR(256),
                criado_em  DATETIME
            )
        """)
        print("Tabela 'superadmins' criada.")
    else:
        print("Tabela 'superadmins' já existe.")

    conn.commit()
    conn.close()

    # ── Cria o primeiro SuperAdmin via Flask/SQLAlchemy ────────────
    from app import create_app
    from app.models import SuperAdmin, db

    app = create_app()
    with app.app_context():
        if not SuperAdmin.query.filter_by(email=SA_EMAIL).first():
            sa = SuperAdmin(nome=SA_NOME, email=SA_EMAIL)
            sa.set_senha(SA_SENHA)
            db.session.add(sa)
            db.session.commit()
            print(f"\nSuperAdmin criado!")
            print(f"  E-mail : {SA_EMAIL}")
            print(f"  Senha  : {SA_SENHA}")
            print(f"\n  IMPORTANTE: altere a senha após o primeiro login.")
        else:
            print(f"SuperAdmin '{SA_EMAIL}' já existe.")

    print("\nMigração concluída.")


if __name__ == '__main__':
    migrate()
