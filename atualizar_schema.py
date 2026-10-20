"""
Atualiza o schema do banco a partir dos models, sem perder dados:
  - cria tabelas que não existem;
  - adiciona colunas que faltam (sempre como NULL permitido).
Não remove nem altera colunas existentes.

Executado no start do deploy (nixpacks.toml / Procfile), antes do gunicorn.
Também pode ser rodado manualmente: python atualizar_schema.py
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

from app import create_app, db
from app import models  # noqa: F401  (registra os models no metadata)

app = create_app()

with app.app_context():
    engine = db.engine
    existentes = set(inspect(engine).get_table_names())
    db.metadata.create_all(engine)
    for t in db.metadata.sorted_tables:
        if t.name not in existentes:
            print(f'atualizar_schema: tabela {t.name} criada')

    insp = inspect(engine)
    with engine.begin() as conn:
        for t in db.metadata.sorted_tables:
            colunas = {c['name'] for c in insp.get_columns(t.name)}
            for col in t.columns:
                if col.name not in colunas:
                    ddl = str(CreateColumn(col).compile(dialect=engine.dialect)).replace(' NOT NULL', '')
                    conn.execute(text(f'ALTER TABLE {t.name} ADD COLUMN {ddl}'))
                    print(f'atualizar_schema: coluna {t.name}.{col.name} adicionada')

    print('atualizar_schema: ok')
