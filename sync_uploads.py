"""
Copia as imagens de seed_uploads/ para app/static/uploads/ no início do deploy.

Só copia arquivos que ainda não existem no destino, então nunca sobrescreve
uploads feitos em produção. Executado pelo comando de start (nixpacks.toml / Procfile).
"""
import os, shutil

BASE    = os.path.dirname(os.path.abspath(__file__))
ORIGEM  = os.path.join(BASE, 'seed_uploads')
DESTINO = os.path.join(BASE, 'app', 'static', 'uploads')

copiados = 0
for raiz, _, arquivos in os.walk(ORIGEM):
    for nome in arquivos:
        src = os.path.join(raiz, nome)
        dst = os.path.join(DESTINO, os.path.relpath(src, ORIGEM))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copiados += 1

print(f'sync_uploads: {copiados} arquivo(s) copiado(s) para {DESTINO}')
