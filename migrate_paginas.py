"""
Migração: cria as tabelas paginas_site e menu_links.
Execute: python migrate_paginas.py
"""
import sqlite3, os

DB_PATH = os.path.join('instance', 'imobiconectaja.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Verifica se a tabela já existe
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paginas_site'")
    if cur.fetchone():
        print("Tabela paginas_site já existe — nada a fazer.")
    else:
        cur.execute("""
            CREATE TABLE paginas_site (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                imobiliaria_id INTEGER NOT NULL REFERENCES imobiliarias(id),
                tipo           VARCHAR(20) DEFAULT 'custom',
                slug           VARCHAR(100) NOT NULL,
                titulo         VARCHAR(200) NOT NULL,
                conteudo       TEXT,
                ativo          BOOLEAN DEFAULT 1,
                no_menu        BOOLEAN DEFAULT 0,
                ordem          INTEGER DEFAULT 0
            )
        """)
        print("Tabela paginas_site criada.")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='menu_links'")
    if cur.fetchone():
        print("Tabela menu_links já existe — nada a fazer.")
    else:
        cur.execute("""
            CREATE TABLE menu_links (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                imobiliaria_id INTEGER NOT NULL REFERENCES imobiliarias(id),
                label          VARCHAR(100) NOT NULL,
                url            VARCHAR(255) NOT NULL,
                ordem          INTEGER DEFAULT 0,
                ativo          BOOLEAN DEFAULT 1,
                abre_nova_aba  BOOLEAN DEFAULT 0
            )
        """)
        print("Tabela menu_links criada.")

    conn.commit()
    conn.close()
    print("Migração concluída.")

if __name__ == '__main__':
    migrate()
