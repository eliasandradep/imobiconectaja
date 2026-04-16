"""
Migração: adiciona colunas 'slug' e 'dominio_personalizado' em imobiliarias
e gera slugs para as imobiliárias existentes.

Execute: python migrate_dominios.py
"""
import sqlite3, os, re

DB_PATH = os.path.join('instance', 'imobiconectaja.db')


def gerar_slug(nome, existentes):
    import unicodedata
    normalizado = unicodedata.normalize('NFD', nome)
    sem_acentos = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    base = re.sub(r'[^a-z0-9]+', '-', sem_acentos.lower()).strip('-') or 'imob'
    slug = base
    contador = 1
    while slug in existentes:
        slug = f"{base}-{contador}"
        contador += 1
    return slug


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Verifica colunas existentes
    cur.execute("PRAGMA table_info(imobiliarias)")
    colunas = {r[1] for r in cur.fetchall()}

    if 'slug' not in colunas:
        # SQLite não permite ADD COLUMN UNIQUE — adiciona coluna e cria índice separado
        cur.execute("ALTER TABLE imobiliarias ADD COLUMN slug VARCHAR(80)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_imobiliarias_slug ON imobiliarias(slug)")
        print("Coluna 'slug' + índice único adicionados.")
    else:
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_imobiliarias_slug ON imobiliarias(slug)")
        print("Coluna 'slug' já existe (índice garantido).")

    if 'dominio_personalizado' not in colunas:
        cur.execute("ALTER TABLE imobiliarias ADD COLUMN dominio_personalizado VARCHAR(255)")
        print("Coluna 'dominio_personalizado' adicionada.")
    else:
        print("Coluna 'dominio_personalizado' já existe.")

    conn.commit()

    # Gera slugs para imobiliárias que ainda não têm
    cur.execute("SELECT id, nome, slug FROM imobiliarias WHERE slug IS NULL OR slug = ''")
    sem_slug = cur.fetchall()

    if sem_slug:
        cur.execute("SELECT slug FROM imobiliarias WHERE slug IS NOT NULL AND slug != ''")
        existentes = {r[0] for r in cur.fetchall()}

        for (imob_id, nome, _) in sem_slug:
            slug = gerar_slug(nome, existentes)
            existentes.add(slug)
            cur.execute("UPDATE imobiliarias SET slug = ? WHERE id = ?", (slug, imob_id))
            print(f"  id={imob_id} '{nome}' => slug='{slug}'")

        conn.commit()
        print(f"{len(sem_slug)} slug(s) gerado(s).")
    else:
        print("Todas as imobiliárias já possuem slug.")

    conn.close()
    print("\nMigração de domínios concluída.")


if __name__ == '__main__':
    migrate()
