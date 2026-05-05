# -*- coding: utf-8 -*-
from fpdf import FPDF
from datetime import datetime

VERDE   = (29, 158, 117)
ESCURO  = (28, 28, 26)
CINZA   = (100, 100, 98)
BRANCO  = (255, 255, 255)
FUNDO   = (245, 250, 248)


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(*CINZA)
        self.cell(0, 8, 'ImobiConectaJa  |  Desenho de Solucao: Cadastro Inteligente com IA', align='L')
        self.set_font('Helvetica', '', 8)
        self.cell(0, 8, f'Pagina {self.page_no()}', align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*VERDE)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font('Helvetica', '', 7)
        self.set_text_color(*CINZA)
        self.cell(0, 8, f'Confidencial  |  Gerado em {datetime.now().strftime("%d/%m/%Y")}  |  imobiconectaja.com.br', align='C')

    def titulo_secao(self, num, texto):
        self.ln(4)
        self.set_fill_color(*VERDE)
        self.set_text_color(*BRANCO)
        self.set_font('Helvetica', 'B', 11)
        self.cell(0, 9, f'  {num}. {texto}', fill=True, new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*ESCURO)
        self.ln(3)

    def subtitulo(self, texto):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(*VERDE)
        self.cell(0, 7, texto, new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*ESCURO)

    def corpo(self, texto):
        self.set_font('Helvetica', '', 9.5)
        self.set_text_color(*ESCURO)
        self.multi_cell(0, 6, texto)
        self.ln(1)

    def item(self, texto):
        self.set_font('Helvetica', '', 9.5)
        self.set_text_color(*ESCURO)
        self.set_x(self.l_margin + 4)
        self.multi_cell(self.epw - 4, 6, f'* {texto}')

    def tabela(self, cabecalho, linhas, col_widths=None):
        if col_widths is None:
            n = len(cabecalho)
            col_widths = [self.epw / n] * n
        self.set_font('Helvetica', 'B', 8.5)
        self.set_fill_color(*VERDE)
        self.set_text_color(*BRANCO)
        for i, h in enumerate(cabecalho):
            self.cell(col_widths[i], 7, h, border=1, fill=True)
        self.ln()
        self.set_font('Helvetica', '', 8.5)
        fill = False
        for linha in linhas:
            self.set_fill_color(*FUNDO)
            self.set_text_color(*ESCURO)
            for i, cel in enumerate(linha):
                self.multi_cell(col_widths[i], 6, str(cel), border=1, fill=fill,
                                new_x='RIGHT', new_y='TOP', max_line_height=6)
            self.ln()
            fill = not fill
        self.ln(3)

    def caixa_codigo(self, texto):
        self.set_fill_color(240, 248, 244)
        self.set_draw_color(*VERDE)
        self.set_font('Courier', '', 8.5)
        self.set_text_color(28, 28, 26)
        self.multi_cell(0, 5.5, texto, border=1, fill=True)
        self.set_font('Helvetica', '', 9.5)
        self.ln(3)

    def diagrama(self, linhas):
        self.set_fill_color(28, 28, 26)
        self.set_draw_color(*VERDE)
        self.set_font('Courier', '', 8)
        self.set_text_color(*BRANCO)
        self.multi_cell(0, 5, '\n'.join(linhas), border=1, fill=True)
        self.set_font('Helvetica', '', 9.5)
        self.set_text_color(*ESCURO)
        self.ln(3)


pdf = PDF()
pdf.set_auto_page_break(True, margin=20)
pdf.set_margins(18, 18, 18)

# ── CAPA ─────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.set_fill_color(28, 28, 26)
pdf.rect(0, 0, 210, 297, 'F')

pdf.set_y(55)
pdf.set_font('Helvetica', 'B', 28)
pdf.set_text_color(*VERDE)
pdf.cell(0, 13, 'ImobiConectaJa', align='C', new_x='LMARGIN', new_y='NEXT')

pdf.set_font('Helvetica', '', 14)
pdf.set_text_color(*BRANCO)
pdf.cell(0, 8, 'Desenho de Solucao', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.ln(2)
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 10, 'Cadastro Inteligente de Imoveis com IA', align='C', new_x='LMARGIN', new_y='NEXT')

pdf.set_y(160)
pdf.set_font('Helvetica', '', 10)
pdf.set_text_color(180, 180, 180)
pdf.multi_cell(0, 7, 'Canais: Portal Web + WhatsApp\nExtracao de dados com Claude API (Anthropic)', align='C')

pdf.set_y(230)
pdf.set_fill_color(*VERDE)
pdf.rect(18, 235, 174, 0.5, 'F')
pdf.set_y(240)
pdf.set_font('Helvetica', '', 9)
pdf.set_text_color(150, 150, 150)
pdf.multi_cell(0, 6, f'Versao 1.0  |  {datetime.now().strftime("%B de %Y")}  |  imobiconectaja.com.br', align='C')

# ── PAG 2 - VISAO GERAL ──────────────────────────────────────────────────────
pdf.add_page()

pdf.titulo_secao(1, 'VISAO GERAL DA SOLUCAO')
pdf.corpo(
    'A solucao permite que proprietarios de imoveis cadastrem seus bens por dois canais '
    'simultaneos: Portal Web publico e WhatsApp. Em ambos, o usuario descreve o imovel '
    'em linguagem natural e a inteligencia artificial extrai automaticamente os dados '
    'estruturados (cidade, tipo, area, comodos etc.), preenchendo o formulario de cadastro. '
    'As fotos tambem sao enviadas e organizadas automaticamente pela IA.'
)
pdf.corpo(
    'O nucleo de IA e fornecido pela Claude API (Anthropic), que oferece compreensao '
    'avancada de portugues brasileiro, extracao de dados em JSON estruturado via '
    'function calling, e analise de imagens (visao computacional) para categorizar '
    'e selecionar a melhor foto de capa.'
)

pdf.titulo_secao(2, 'ARQUITETURA GERAL')
pdf.subtitulo('Canal Web')
pdf.diagrama([
    '  Cliente Acessa /cliente                               ',
    '       |                                                ',
    '  Informa CPF  -->  Ja cadastrado?  -->  Carrega dados  ',
    '       |                 Nao --> Cadastro rapido        ',
    '  Descreve o imovel em texto livre                      ',
    '       |                                                ',
    '  POST /api/extrair-imovel  -->  Claude API (Anthropic) ',
    '       |                              |                 ',
    '       <------ JSON estruturado ------+                 ',
    '       |                                                ',
    '  Formulario preenchido automaticamente (JavaScript)    ',
    '       |                                                ',
    '  Cliente revisa + envia fotos                          ',
    '       |                                                ',
    '  Imovel salvo no banco  +  Fotos salvas no storage     ',
    '       |                                                ',
    '  E-mail de confirmacao (Flask-Mail)                    ',
])
pdf.subtitulo('Canal WhatsApp')
pdf.diagrama([
    '  Cliente envia mensagem no WhatsApp da imobiliaria     ',
    '       |                                                ',
    '  Evolution API  -->  Webhook POST /webhook/whatsapp    ',
    '       |                                                ',
    '  Flask identifica numero  -->  Estado no Redis         ',
    '       |                                                ',
    '  Bot solicita CPF  -->  Valida e identifica cliente    ',
    '       |                                                ',
    '  Bot coleta descricao do imovel (varias mensagens)     ',
    '       |                                                ',
    '  Claude API processa descricao  -->  JSON estruturado  ',
    '       |                                                ',
    '  Bot envia resumo para confirmacao do cliente          ',
    '       |                                                ',
    '  Cliente envia fotos pelo WhatsApp                     ',
    '       |                                                ',
    '  Download automatico da midia  -->  Salvo no storage   ',
    '       |                                                ',
    '  Imovel cadastrado  -->  Notificacao para imobiliaria  ',
])

# ── PAG 3 - COMPONENTES ──────────────────────────────────────────────────────
pdf.add_page()
pdf.titulo_secao(3, 'COMPONENTES E TECNOLOGIAS')

pdf.subtitulo('3.1  Plataforma Base (ja existente)')
pdf.tabela(
    ['Componente', 'Tecnologia', 'Status'],
    [
        ['Framework web', 'Flask (Python)', 'Existente'],
        ['Banco de dados', 'SQLite (dev) / PostgreSQL (prod)', 'Existente'],
        ['ORM', 'SQLAlchemy', 'Existente'],
        ['Autenticacao', 'Flask-Login', 'Existente'],
        ['E-mail', 'Flask-Mail (SMTP)', 'Existente'],
        ['Frontend', 'Bootstrap 5 + Jinja2', 'Existente'],
        ['Modelo Pessoa', 'campo documento (CPF)', 'Existente'],
        ['Modelo Imovel', 'todos os campos necessarios', 'Existente'],
    ],
    [62, 80, 38]
)

pdf.subtitulo('3.2  Inteligencia Artificial')
pdf.tabela(
    ['Item', 'Detalhe'],
    [
        ['Provedor', 'Anthropic Claude API'],
        ['Modelo recomendado', 'claude-sonnet-4-6 (custo/beneficio ideal)'],
        ['SDK Python', 'anthropic (pip install anthropic)'],
        ['Uso principal', 'Extracao de dados em JSON via tool use (function calling)'],
        ['Uso secundario', 'Analise e categorizacao de fotos (visao computacional)'],
        ['Custo estimado', 'R$ 0,01 a R$ 0,05 por cadastro completo'],
    ],
    [60, 120]
)

pdf.subtitulo('3.3  Canal WhatsApp')
pdf.tabela(
    ['Item', 'Detalhe'],
    [
        ['Provedor recomendado', 'Evolution API (open source, auto-hospedado via Docker)'],
        ['Alternativa SaaS', 'Twilio WhatsApp API (mais simples, pago por mensagem)'],
        ['Protocolo', 'Webhook HTTP POST recebido pelo Flask'],
        ['Mensagens suportadas', 'Texto, imagem, audio (transcricao futura), documento'],
        ['Estado de conversa', 'Redis (sessao por numero de telefone)'],
        ['Hospedagem', 'Docker no mesmo VPS da aplicacao'],
    ],
    [60, 120]
)

pdf.subtitulo('3.4  Armazenamento de Fotos')
pdf.tabela(
    ['Ambiente', 'Tecnologia', 'Custo'],
    [
        ['Desenvolvimento', 'Sistema de arquivos local (static/uploads/)', 'Gratuito'],
        ['Producao (recomendado)', 'Cloudflare R2 (compativel S3)', 'Primeiros 10 GB gratis'],
        ['Alternativa producao', 'AWS S3 Standard', 'R$ 0,12/GB/mes'],
        ['Recebimento WhatsApp', 'Download via API + salvo no storage', 'Incluso'],
        ['Recebimento Web', 'Upload multipart/form-data tradicional', 'Incluso'],
    ],
    [55, 85, 40]
)

pdf.subtitulo('3.5  Validacao de CPF')
pdf.item('Biblioteca Python: validate-docbr (pip install validate-docbr)')
pdf.item('Valida formato e digito verificador')
pdf.item('Busca no campo documento da tabela pessoas')
pdf.item('Identifica se o cliente ja esta cadastrado na imobiliaria')
pdf.ln(3)

# ── PAG 4 - FLUXOS DETALHADOS ────────────────────────────────────────────────
pdf.add_page()
pdf.titulo_secao(4, 'FLUXO DETALHADO - PORTAL WEB')
linhas_web = [
    'Passo 1: Cliente acessa /cliente (portal publico, sem login)',
    'Passo 2: Informa CPF',
    '         - CPF ja cadastrado: carrega dados, pula formulario',
    '         - CPF novo: cadastro rapido (nome, telefone, e-mail)',
    'Passo 3: Escolhe finalidade: Quero Vender / Quero Alugar',
    'Passo 4: Descreve o imovel em campo de texto livre',
    'Passo 5: Clica em "Analisar com IA"',
    '         -> chamada fetch() assincrona para /api/extrair-imovel',
    'Passo 6: Claude API processa o texto e retorna JSON estruturado',
    'Passo 7: JavaScript preenche automaticamente os campos do formulario',
    'Passo 8: Cliente revisa, corrige e faz upload das fotos',
    'Passo 9: Submissao -> imovel salvo vinculado a Pessoa (pelo CPF)',
    'Passo 10: E-mail de confirmacao ao cliente + notificacao a imobiliaria',
]
for l in linhas_web:
    pdf.item(l)
pdf.ln(3)

pdf.titulo_secao(5, 'FLUXO DETALHADO - WHATSAPP')
linhas_wa = [
    'Passo 1:  Cliente envia mensagem no WhatsApp da imobiliaria',
    'Passo 2:  Evolution API recebe e envia webhook para /webhook/whatsapp',
    'Passo 3:  Flask identifica o numero de telefone e consulta estado (Redis)',
    'Passo 4:  Conversa nova -> bot solicita CPF ao cliente',
    'Passo 5:  Cliente informa CPF -> sistema valida e identifica ou cadastra',
    'Passo 6:  Bot pergunta: deseja vender ou alugar?',
    'Passo 7:  Cliente descreve o imovel (pode ser em varias mensagens)',
    'Passo 8:  Claude API processa a descricao acumulada -> JSON',
    'Passo 9:  Bot envia resumo dos dados para confirmacao do cliente',
    'Passo 10: Bot solicita o envio das fotos pelo WhatsApp',
    'Passo 11: Sistema faz download de cada imagem e salva no storage',
    'Passo 12: Bot confirma cadastro e informa que a imobiliaria entrara em contato',
    'Passo 13: Imobiliaria recebe notificacao (e-mail + badge no painel admin)',
]
for l in linhas_wa:
    pdf.item(l)

# ── PAG 5 - IA + INFRA ───────────────────────────────────────────────────────
pdf.add_page()
pdf.titulo_secao(6, 'EXTRACAO DE DADOS COM INTELIGENCIA ARTIFICIAL')
pdf.corpo(
    'A Claude API recebe o texto descritivo do cliente e retorna um JSON estruturado '
    'com todos os campos identificados. A tecnica utilizada e tool use (function calling), '
    'que garante que o retorno seja sempre um JSON valido e compativel com os campos '
    'do modelo Imovel da plataforma.'
)
pdf.subtitulo('Exemplo de entrada (texto do cliente):')
pdf.caixa_codigo(
    '"Tenho uma casa para alugar em Sao Jose dos Campos, 3 quartos sendo\n'
    '1 suite com closet, 2 banheiros, sala, cozinha, area construida de\n'
    '150m2, terreno de 200m2, garagem para 2 carros."'
)
pdf.subtitulo('Saida da Claude API (JSON estruturado):')
pdf.caixa_codigo(
    '{\n'
    '  "finalidade":     "Locacao",\n'
    '  "tipo":           "Casa",\n'
    '  "cidade":         "Sao Jose dos Campos",\n'
    '  "estado":         "SP",\n'
    '  "quartos":        3,\n'
    '  "suites":         1,\n'
    '  "banheiros":      2,\n'
    '  "vagas":          2,\n'
    '  "area_construida": 150,\n'
    '  "area_terreno":   200,\n'
    '  "caracteristicas": ["closet", "sala", "cozinha", "garagem"],\n'
    '  "confianca":      0.95\n'
    '}'
)

pdf.titulo_secao(7, 'ANALISE DE FOTOS COM IA (VISAO COMPUTACIONAL)')
pdf.corpo(
    'A Claude API suporta analise de imagens (multimodal). '
    'Ao receber fotos do imovel, a IA realiza automaticamente:'
)
pdf.item('Identificacao do comodo: sala, quarto, cozinha, banheiro, area externa, fachada')
pdf.item('Geracao de legenda automatica para cada foto')
pdf.item('Selecao da melhor foto para definir como imagem principal (capa)')
pdf.item('Deteccao de fotos com baixa qualidade, escuras ou borradas')
pdf.item('Ordenacao sugerida das fotos para melhor apresentacao no site')
pdf.ln(3)

pdf.titulo_secao(8, 'INFRAESTRUTURA RECOMENDADA PARA PRODUCAO')
pdf.tabela(
    ['Componente', 'Opcao Recomendada', 'Custo/mes (estimado)'],
    [
        ['Servidor da aplicacao', 'VPS 2 vCPU / 4 GB RAM (Contabo/DigitalOcean)', 'R$ 80 - R$ 150'],
        ['Banco de dados', 'PostgreSQL (no mesmo VPS)', 'R$ 0 (incluso)'],
        ['Storage de fotos', 'Cloudflare R2 (10 GB gratuitos)', 'R$ 0 - R$ 30'],
        ['Evolution API', 'Docker no mesmo VPS', 'R$ 0 (incluso)'],
        ['Redis', 'Redis no mesmo VPS', 'R$ 0 (incluso)'],
        ['Claude API (Anthropic)', 'Pay-per-use (volume dependente)', 'R$ 20 - R$ 100'],
        ['Dominio + SSL', 'Cloudflare (SSL gratuito)', 'R$ 40/ano'],
        ['WhatsApp Business', 'Meta (gratuito ate certo volume)', 'R$ 0 - R$ 50'],
    ],
    [58, 80, 42]
)

# ── PAG 6 - ROADMAP + DEPENDENCIAS ──────────────────────────────────────────
pdf.add_page()
pdf.titulo_secao(9, 'ROADMAP DE IMPLEMENTACAO')
pdf.tabela(
    ['Fase', 'Entregas', 'Prazo estimado'],
    [
        ['Fase 1 - Portal Web + IA',
         'Endpoint /api/extrair-imovel, portal /cliente, formulario inteligente, upload de fotos',
         '2 - 3 semanas'],
        ['Fase 2 - WhatsApp Bot',
         'Evolution API (Docker), webhook Flask, Redis, fluxo completo de conversa, recebimento de fotos',
         '3 - 4 semanas'],
        ['Fase 3 - Refinamentos',
         'Notificacoes em tempo real, painel de conversas WhatsApp, metricas de IA, ajuste de prompts',
         '1 - 2 semanas'],
    ],
    [35, 110, 35]
)

pdf.titulo_secao(10, 'DEPENDENCIAS PYTHON A INSTALAR')
pdf.tabela(
    ['Pacote', 'Funcao', 'Comando de instalacao'],
    [
        ['anthropic', 'SDK oficial da Claude API (Anthropic)', 'pip install anthropic'],
        ['validate-docbr', 'Validacao de CPF e CNPJ', 'pip install validate-docbr'],
        ['redis', 'Estado de conversa WhatsApp', 'pip install redis'],
        ['boto3', 'Storage S3 / Cloudflare R2', 'pip install boto3'],
        ['requests', 'Download de midia do WhatsApp', 'pip install requests'],
        ['Pillow', 'Processamento de imagens', 'pip install Pillow'],
        ['fpdf2', 'Geracao de PDFs (interno)', 'pip install fpdf2'],
    ],
    [38, 90, 52]
)

pdf.ln(4)
pdf.set_fill_color(*FUNDO)
pdf.set_draw_color(*VERDE)
pdf.set_font('Helvetica', 'B', 9)
pdf.set_text_color(*VERDE)
pdf.multi_cell(0, 7, '  OBSERVACOES IMPORTANTES', border=1, fill=True)
pdf.set_font('Helvetica', '', 9)
pdf.set_text_color(*ESCURO)
obs = [
    '1. O campo "documento" ja existe no modelo Pessoa - sera utilizado para armazenar o CPF.',
    '2. As fases 1 e 2 sao independentes e podem ser desenvolvidas em paralelo.',
    '3. A Evolution API requer um numero de WhatsApp Business ativo e aprovado pela Meta.',
    '4. Em producao, recomenda-se migrar de SQLite para PostgreSQL antes do lancamento.',
    '5. O Redis pode ser substituido por sessoes em banco de dados em ambientes sem Redis.',
    '6. Todos os custos da Claude API sao pay-per-use - sem mensalidade fixa.',
]
for o in obs:
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, o)
    pdf.ln(1)

output = r'd:\projetos\imobiconectaja\Arquitetura_Solucao_ImobiConectaJa.pdf'
pdf.output(output)
print(f'PDF gerado: {output}')
