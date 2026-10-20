"""
Migração: prepara o Postgres de produção e copia os dados do SQLite local.

  1. Cria as tabelas que não existem no Postgres (a partir dos models).
  2. Adiciona colunas que faltam em tabelas já existentes.
  3. Copia os registros do instance/imobiconectaja.db para as tabelas VAZIAS
     do Postgres (tabelas que já têm dados são puladas, para não duplicar).
  4. Ajusta as sequências de ID do Postgres.

Execute (Git Bash):
  PG_URL="postgresql://..." python migrar_para_postgres.py
Execute (PowerShell):
  $env:PG_URL="postgresql://..."; python migrar_para_postgres.py

PG_URL = DATABASE_PUBLIC_URL do serviço Postgres no Railway.
"""
import os, sys

PG_URL = os.environ.get('PG_URL', '').strip()
if not PG_URL:
    sys.exit('Defina a variável PG_URL com a DATABASE_PUBLIC_URL do Postgres.')
if PG_URL.startswith('postgres://'):
    PG_URL = PG_URL.replace('postgres://', 'postgresql+psycopg2://', 1)

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'instance', 'imobiconectaja.db')
if not os.path.exists(SQLITE_PATH):
    sys.exit(f'Banco local não encontrado: {SQLITE_PATH}')

# A app passa a apontar para o Postgres (sobrepõe o DATABASE_URL do .env)
os.environ['DATABASE_URL'] = PG_URL

from sqlalchemy import create_engine, inspect, select, text, func
from sqlalchemy.schema import CreateColumn
from app import create_app, db
from app import models  # noqa: F401  (registra os models no metadata)

app = create_app()

with app.app_context():
    pg = db.engine
    sqlite = create_engine(f'sqlite:///{SQLITE_PATH}')
    tabelas = db.metadata.sorted_tables   # ordem respeitando chaves estrangeiras

    # ── 1. Tabelas que faltam ───────────────────────────────────────
    existentes = set(inspect(pg).get_table_names())
    db.metadata.create_all(pg)
    for t in tabelas:
        if t.name not in existentes:
            print(f'[criada]  tabela {t.name}')

    # ── 2. Colunas que faltam ───────────────────────────────────────
    insp = inspect(pg)
    with pg.begin() as conn:
        for t in tabelas:
            cols_pg = {c['name'] for c in insp.get_columns(t.name)}
            for col in t.columns:
                if col.name not in cols_pg:
                    ddl = CreateColumn(col).compile(dialect=pg.dialect)
                    # NOT NULL sem default quebraria em tabela com dados
                    ddl = str(ddl).replace(' NOT NULL', '')
                    conn.execute(text(f'ALTER TABLE {t.name} ADD COLUMN {ddl}'))
                    print(f'[coluna]  {t.name}.{col.name} adicionada')

    # ── 3. Cópia dos dados ──────────────────────────────────────────
    insp_sqlite = inspect(sqlite)
    tabelas_sqlite = set(insp_sqlite.get_table_names())
    with pg.begin() as dst, sqlite.connect() as src:
        for t in tabelas:
            if t.name not in tabelas_sqlite:
                print(f'[pulada]  {t.name}: não existe no SQLite')
                continue
            if dst.execute(select(func.count()).select_from(t)).scalar():
                print(f'[pulada]  {t.name}: já tem dados no Postgres')
                continue
            cols_sqlite = {c['name'] for c in insp_sqlite.get_columns(t.name)}
            cols = [c for c in t.columns if c.name in cols_sqlite]
            linhas = [dict(r._mapping) for r in src.execute(select(*cols))]
            if linhas:
                dst.execute(t.insert(), linhas)
            print(f'[copiada] {t.name}: {len(linhas)} registro(s)')

    # ── 4. Sequências de ID ─────────────────────────────────────────
    with pg.begin() as conn:
        for t in tabelas:
            if 'id' in t.c:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t.name}), 1), "
                    f"(SELECT MAX(id) FROM {t.name}) IS NOT NULL)"
                ))

    print('\nMigração concluída.')
