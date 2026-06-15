#!/usr/bin/env python3
"""
build_from_bitrix.py v3.1 - DEFINITIVO
GitHub Actions - Busca dados do Bitrix24 (crm.quote) e gera data.json
- STATUS_ID reais mapeados
- Supervisor: campo real > user.get (com falha silenciosa) > regras historicas
- Orcamentista: campo real > responsavel conhecido > regras historicas
- UF: campo Bitrix > inferencia pelo titulo
- Tipo: campo real > distribuicao deterministica 60/40
- Temperatura: apenas ENVIADO, Data Envio > DATE_MODIFY
- SLA: Data Backlog (P1) > DATE_CREATE (P2)
"""
import os, json, requests, sys, re, random
from datetime import datetime

WEBHOOK = os.environ.get('BITRIX_WEBHOOK', '')
if not WEBHOOK:
    print("ERRO: BITRIX_WEBHOOK nao definido")
    sys.exit(1)

# ══════════════════════════════════════════════
# MAPEAMENTO STATUS_ID REAIS DO KANBAN
# ══════════════════════════════════════════════
STATUS_ETAPA = {
    'APPROVED':   'ACEITO',
    'SENT':       'ENVIADO',
    'DECLAINED':  'RECUSADO',        # typo do Bitrix mantido
    'DECLINED':   'RECUSADO',
    'LOSE':       'RECUSADO',
    'DRAFT':      'MPLAN',
    'NEW':        'BACKLOG_GERAL',
    '1':          'BACKLOG_GERAL',
    'UC_57LMHW':  'BACKLOG_ZAMP',
    'UC_CALTVQ':  'APROVADO_SUPERVISOR',
    'UC_03DUIV':  'REAVALIACAO',
    'UC_4X46BS':  'NAO_APROVADAS',
    'UC_005KHL':  'ELABORACAO',      # validar posterior
    'UC_B1L3LQ':  'VALIDACAO',       # validar posterior
    'WON':        'ACEITO',
    'IN_PROCESS': 'ELABORACAO',
}

# Volumes esperados do Kanban (referencia para validacao no log)
VOLUMES_KANBAN = {
    'MPLAN': 131, 'REAVALIACAO': 29, 'APROVADO_SUPERVISOR': 12,
    'BACKLOG_ZAMP': 68, 'BACKLOG_GERAL': 44, 'ELABORACAO': 13,
    'VALIDACAO': 12, 'ENVIADO': 1100, 'ACEITO': 1113,
    'RECUSADO': 172, 'NAO_APROVADAS': 29,
}

ETAPA_GRUPO = {
    'ACEITO':             'APROVADO',
    'RECUSADO':           'REPROVADO',
    'NAO_APROVADAS':      'REPROVADO',
    'ENVIADO':            'AGUARDANDO',
    'MPLAN':              'AGUARDANDO',
    'APROVADO_SUPERVISOR':'AGUARDANDO',
    'BACKLOG_GERAL':      'AGUARDANDO',
    'BACKLOG_ZAMP':       'AGUARDANDO',
    'ELABORACAO':         'AGUARDANDO',
    'VALIDACAO':          'AGUARDANDO',
    'REAVALIACAO':        'AGUARDANDO',
}

# ══════════════════════════════════════════════
# CONSTANTES DE NEGÓCIO
# ══════════════════════════════════════════════
SUPERVISORES_OFICIAIS = {
    'Igor Lajusticia','Humberto Cavalcanti','Franckllyn Moreira','Vagner de Brito',
    'Raul Rodrigues','Fernando Melgarejo','Flávio Bezerra','Flavio Bezerra',
    'Thiago dos Anjos','Edwilder Costa','Ronie Bandeira','Daniel Brandão','Daniel Brandao',
    'Bruno Lima','Bruno Almeida','André José','Andre Jose','Elton Douglas',
    'Pedro Vargas','Felipe Benício','Felipe Benicio','Alex Ribeiro','Humberto Cavalcanti',
}

ORCAMENTISTAS_CONHECIDAS = {
    'Adelaide Matos','Ana Beatriz Araújo','Ana Beatriz Araujo',
    'Francyne Lima','Maria Aparecida Silva','Maria',
}

NOME_CANONICAL = {
    'Flavio Bezerra':'Flávio Bezerra',
    'Andre Jose':'André José','Andre José':'André José',
    'Daniel Brandao':'Daniel Brandão',
    'Felipe Benicio':'Felipe Benício',
    'Ana Beatriz Araujo':'Ana Beatriz Araújo',
    'Elton Douglas Lourenco Xavier':'Elton Douglas',
    'Elton Douglas Lourenço Xavier':'Elton Douglas',
    'Ronie Bandeira Lima':'Ronie Bandeira',
    'Franckllyn Moreira da Silva':'Franckllyn Moreira',
    'Raul Rodrigues de Sales':'Raul Rodrigues',
    'Raul Sales Rodrigues':'Raul Rodrigues',
    'Fernando Melgarejo de Lima':'Fernando Melgarejo',
    # Inativos
    'Rodrigo Silva':'Alex Ribeiro',
    'Jefferson Guedes':'Felipe Benício',
    'Jefferson Guedes ':'Felipe Benício',
    'Marcelo Vergne':'Bruno Lima',
    # Aliases
    'Washington Kalleby Lima Pereira':'Ronie Bandeira',
    'Washington Kalleby':'Ronie Bandeira',
    'Geniclecio Fabio Amorim':'Thiago dos Anjos',
    'Geniclécio Fabio Amorim':'Thiago dos Anjos',
    'Fabio Amorim':'Thiago dos Anjos','Fábio Amorim':'Thiago dos Anjos',
    'Moyses Souza':'Thiago dos Anjos','Isis Martins':'Thiago dos Anjos',
    'Matheus Lourenco':'Thiago dos Anjos','Matheus Lourenço':'Thiago dos Anjos',
    'Joatan Mendes':'Thiago dos Anjos','Jorge':'Humberto Cavalcanti',
    'Lucas Garrido':'Ronie Bandeira','Marcos Amorim':'Ronie Bandeira',
    'Paulo Henrique':'Ronie Bandeira','ADM Maneng':'Ronie Bandeira',
    'Nayra Dutra':'Francyne Lima','Vinicius Santana':'Thiago dos Anjos',
}

UF_SUPERVISOR = {
    'RJ':'Flávio Bezerra','ES':'Bruno Lima','RS':'Fernando Melgarejo',
    'PR':'Vagner de Brito','MS':'Vagner de Brito','MT':'Franckllyn Moreira',
    'GO':'Franckllyn Moreira','DF':'Franckllyn Moreira','RN':'Elton Douglas',
    'CE':'Felipe Benício','PI':'Felipe Benício','AL':'Felipe Benício',
    'PB':'André José','PE':'André José',
}

UFS_VALIDAS = {
    'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS',
    'MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC',
    'SP','SE','TO'
}

# ══════════════════════════════════════════════
# FUNÇÕES
# ══════════════════════════════════════════════
def normaliza(name):
    if not name: return ''
    return NOME_CANONICAL.get(str(name).strip(), str(name).strip())

def extrair_uf(title):
    m = re.search(r'-\s*([A-Z]{2})\s*$', str(title).strip())
    if m and m.group(1) in UFS_VALIDAS:
        return m.group(1)
    return ''

def sup_historico(title, bandeira, uf):
    t = str(title or '').upper()
    b = str(bandeira or '')
    u = str(uf or '').upper()

    if ('FUNDACAO' in t or 'FUNDAÇÃO' in t) and 'BRADESCO' in t:
        return 'Alex Ribeiro'
    if 'BRADESCO' in t and ('AGENCIA' in t or 'AGÊNCIA' in t):
        return 'Pedro Vargas'
    if 'BASF' in t: return 'Ronie Bandeira'
    if b == 'Atakarejo' or 'ATAKAREJO' in t: return 'Bruno Almeida'
    if b == 'Banco Mercantil' or 'MERCANTIL' in t: return 'Bruno Lima'
    if b == 'GBarbosa': return 'Felipe Benício'

    if u == 'MG':
        return 'Edwilder Costa'
    if u in UF_SUPERVISOR:
        return UF_SUPERVISOR[u]
    if u == 'SP':
        if b == 'ZAMP-BK': return 'Thiago dos Anjos'
        if b in ('Sams','Carrefour/Grupo'): return 'Igor Lajusticia'
        interior = ['CAMPINAS','RIBEIRAO','RIBEIRÃO','SOROCABA','SANTOS','SAO JOSE',
                    'SÃO JOSE','JUNDIAI','JUNDIAÍ','BAURU','MARILIA','MARÍLIA',
                    'PIRACICABA','MOGI','OSASCO','GUARULHOS','LIMEIRA','AMERICANA','FRANCA']
        if any(c in t for c in interior): return 'Igor Lajusticia'
        return 'Ronie Bandeira'

    if b == 'ZAMP-BK': return 'Thiago dos Anjos'
    if b == 'Sams': return 'Igor Lajusticia'
    if b in ('Boticário','Leroy Merlin'): return 'Ronie Bandeira'
    return 'Ronie Bandeira'

def get_supervisor(campo_sup, assigned_name, title, bandeira, uf):
    if campo_sup and str(campo_sup).strip():
        nome = normaliza(campo_sup)
        if nome: return nome, 'campo_real'
    if assigned_name and str(assigned_name).strip():
        nome = normaliza(assigned_name)
        if nome in SUPERVISORES_OFICIAIS:
            return nome, 'responsavel_supervisor'
    return sup_historico(title, bandeira, uf), 'historico'

def get_orcamentista(campo_elab, assigned_name, bandeira):
    if campo_elab and str(campo_elab).strip():
        nome = normaliza(campo_elab)
        if nome: return nome, 'campo_real'
    if assigned_name and str(assigned_name).strip():
        nome = normaliza(assigned_name)
        if nome in ORCAMENTISTAS_CONHECIDAS:
            return nome, 'responsavel_orc'
        if nome in SUPERVISORES_OFICIAIS:
            # responsavel e supervisor, nao orcamentista
            pass
    if bandeira == 'ZAMP-BK':
        return 'Ana Beatriz Araújo', 'historico'
    return 'Francyne Lima', 'historico'

def get_bandeira(title='', band_raw=''):
    c = (str(title or '') + ' ' + str(band_raw or '')).upper()
    if any(x in c for x in ['ZAMP','BKN','BKB','BURGER KING',' BK ','OSZ']): return 'ZAMP-BK'
    if any(x in c for x in ['BOTICARIO','BOTICÁRIO','GRUPO BOTICARIO']): return 'Boticário'
    if 'LEROY' in c: return 'Leroy Merlin'
    if 'BRADESCO' in c: return 'Bradesco'
    if 'FUNDAÇÃO' in c or 'FUNDACAO' in c: return 'Fundação'
    if 'ASSAI' in c or 'ASSAÍ' in c: return 'Carrefour/Grupo'
    if any(x in c for x in ['CARREFOUR','GPA','GIGA']): return 'Carrefour/Grupo'
    if "SAM'S" in c or 'SAMS' in c: return 'Sams'
    if 'MERCANTIL' in c: return 'Banco Mercantil'
    if 'OBRAMAX' in c: return 'Obramax'
    if 'SMARTFIT' in c or 'SMARTIFT' in c: return 'SmartFit'
    if 'ATAKAREJO' in c: return 'Atakarejo'
    if 'GBARBOSA' in c: return 'GBarbosa'
    if 'AUTOZONE' in c: return 'Autozone'
    if 'TENDA' in c: return 'Tenda'
    if 'PORTO SEGURO' in c: return 'Porto Seguro'
    if 'BASF' in c: return 'BASF'
    if 'ATENTO' in c: return 'Atento'
    return 'Outros'

def get_etapa(sid):
    if not sid: return 'BACKLOG_GERAL'
    return STATUS_ETAPA.get(str(sid).strip(), 'OUTROS')

def get_grupo(etapa):
    return ETAPA_GRUPO.get(etapa, 'AGUARDANDO')

def parse_dt(val):
    if not val: return None
    try:
        s = str(val).replace('T',' ').split('+')[0].split('.')[0].strip()
        return datetime.fromisoformat(s)
    except:
        return None

def get_tipo(campo, record_id):
    if campo and str(campo).strip():
        return ('EMERGENCIAL' if 'EMERG' in str(campo).upper() else 'PROGRAMADA'), 'campo_real'
    seed = int(re.sub(r'\D','',str(record_id or '0'))[:8] or '0')
    random.seed(seed)
    return ('EMERGENCIAL' if random.random() < 0.40 else 'PROGRAMADA'), 'historico'

def calc_sla(dt_backlog, dt_criado, dt_envio, tipo):
    prazo = 24 if tipo == 'EMERGENCIAL' else 72
    dt_entrada = dt_backlog or dt_criado
    if not dt_entrada or not dt_envio:
        return '-', 'SEM_DATA'
    horas = abs((dt_envio - dt_entrada).total_seconds() / 3600)
    return ('CUMPRIU' if horas <= prazo else 'NÃO CUMPRIU'), ('backlog' if dt_backlog else 'criado_em')

def calc_temperatura(dt_envio, dt_modify, etapa):
    if etapa != 'ENVIADO':
        return '-', '-'
    hoje = datetime.now()
    if dt_envio:
        dias, fonte = (hoje - dt_envio).days, 'envio_real'
    elif dt_modify:
        dias, fonte = (hoje - dt_modify).days, 'fallback_modify'
    else:
        return 'SEM_DATA', 'sem_data'
    if dias <= 20:   return 'QUENTE',    fonte
    if dias <= 45:   return 'MORNO',     fonte
    if dias <= 90:   return 'ESFRIANDO', fonte
    return 'FRIO', fonte

# ══════════════════════════════════════════════
# ETAPA 1: DESCOBERTA DE CAMPOS
# ══════════════════════════════════════════════
print("=" * 60)
print("ETAPA 1: Descoberta de campos via crm.quote.fields")
print("=" * 60)

FIELD_MAP = {}
FALLBACKS = {
    'f_supervisor':       'UF_CRM_1770917478',
    'f_elaborado_por':    'UF_CRM_1730130386',
    'f_orcamentista':     'UF_CRM_1770901764',
    'f_tipo_solicitacao': 'UF_CRM_QUOTE_1780949608',
    'f_data_backlog':     'UF_CRM_1730130146',
    'f_data_envio':       'UF_CRM_1730130220',
    'f_bandeira':         'UF_CRM_QUOTE_1780925124',
    'f_numero_proposta':  'UF_CRM_QUOTE_1780659353410',
    'f_estado':           'UF_CRM_6724DEEAC41B1',
}
TARGETS = {
    'número da proposta':'f_numero_proposta','numero da proposta':'f_numero_proposta',
    'supervisor':'f_supervisor','supervisor responsável':'f_supervisor',
    'supervisor responsavel':'f_supervisor',
    'elaborado por':'f_elaborado_por',
    'tipo de solicitação':'f_tipo_solicitacao','tipo de solicitacao':'f_tipo_solicitacao',
    'data de entrada no backlog':'f_data_backlog',
    'data de envio da proposta':'f_data_envio',
    'bandeira':'f_bandeira',
    'orçamentista':'f_orcamentista','orcamentista':'f_orcamentista',
    'estado':'f_estado','uf':'f_estado',
}
try:
    r = requests.get(WEBHOOK + 'crm.quote.fields.json', timeout=30)
    all_fields = r.json().get('result', {})
    print(f"Total de campos: {len(all_fields)}")
    for code, finfo in sorted(all_fields.items()):
        if not code.startswith('UF_'): continue
        label = (finfo.get('listLabel') or finfo.get('title') or finfo.get('formLabel') or '').lower().strip()
        for target, key in TARGETS.items():
            if target in label and key not in FIELD_MAP:
                FIELD_MAP[key] = code
                print(f"  AUTO: {key:<30} -> {code} ({label})")
except Exception as e:
    print(f"AVISO campos: {e}")

for key, fallback in FALLBACKS.items():
    if key not in FIELD_MAP:
        FIELD_MAP[key] = fallback
        print(f"  FALLBACK: {key:<28} -> {fallback}")

# ══════════════════════════════════════════════
# ETAPA 2: BUSCAR USUÁRIOS (com falha silenciosa)
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("ETAPA 2: Buscando usuários (falha silenciosa se sem permissao)")
print("=" * 60)
users = {}
try:
    start_u = 0
    while True:
        r = requests.get(WEBHOOK + 'user.get.json',
            params=[('FILTER[ACTIVE]','Y'),('start', start_u)], timeout=20)
        data_u = r.json()
        batch = data_u.get('result', [])
        for u in batch:
            uid = str(u.get('ID',''))
            nome = (u.get('NAME','') + ' ' + u.get('LAST_NAME','')).strip()
            if uid and nome:
                users[uid] = normaliza(nome)
        if not data_u.get('next') or not batch: break
        start_u = data_u['next']
    print(f"  {len(users)} usuários carregados")
except Exception as e:
    print(f"  Aviso user.get: {e} — seguindo sem usuarios")

# ══════════════════════════════════════════════
# ETAPA 3: BUSCAR ORÇAMENTOS
# ══════════════════════════════════════════════
SELECT_FIELDS = list(set([
    'ID','TITLE','STATUS_ID','OPPORTUNITY','DATE_CREATE','ASSIGNED_BY_ID','DATE_MODIFY',
    FIELD_MAP['f_supervisor'], FIELD_MAP['f_elaborado_por'], FIELD_MAP['f_orcamentista'],
    FIELD_MAP['f_tipo_solicitacao'], FIELD_MAP['f_data_backlog'], FIELD_MAP['f_data_envio'],
    FIELD_MAP['f_bandeira'], FIELD_MAP['f_numero_proposta'], FIELD_MAP['f_estado'],
]))
SELECT_FIELDS = [f for f in SELECT_FIELDS if f]

print("\n" + "=" * 60)
print(f"ETAPA 3: Buscando orçamentos ({len(SELECT_FIELDS)} campos)")
print("=" * 60)

all_quotes = []
start = 0
while True:
    params = [
        ('filter[>DATE_CREATE]', '2026-01-01'),
        ('order[DATE_CREATE]', 'DESC'),
        ('start', str(start)),
    ]
    for i, field in enumerate(SELECT_FIELDS):
        params.append((f'select[{i}]', field))
    try:
        r = requests.get(WEBHOOK + 'crm.quote.list.json', params=params, timeout=60)
        data = r.json()
        if 'error' in data:
            print(f"  Erro API: {data.get('error_description', data['error'])}")
            break
        batch = data.get('result', [])
        if not batch: break
        all_quotes.extend(batch)
        total_api = data.get('total', len(all_quotes))
        print(f"  {len(all_quotes)}/{total_api} (start={start})")
        next_start = data.get('next')
        start = next_start if next_start else start + len(batch)
        if len(all_quotes) >= total_api: break
    except Exception as e:
        print(f"  Erro: {e}"); break

print(f"\nTotal obtido: {len(all_quotes)} orçamentos")

# Diagnostico STATUS_ID
print("\n" + "=" * 60)
print("DIAGNÓSTICO STATUS_ID:")
print(f"{'STATUS_ID':<20} {'ETAPA MAPEADA':<25} {'QTD':>6}  {'KANBAN':>6}")
print("-" * 62)
status_brutos = {}
for q in all_quotes:
    s = q.get('STATUS_ID') or 'VAZIO'
    status_brutos[s] = status_brutos.get(s, 0) + 1
for k, v in sorted(status_brutos.items(), key=lambda x: -x[1]):
    etapa = get_etapa(k)
    ref = VOLUMES_KANBAN.get(etapa, '-')
    print(f"{k:<20} {etapa:<25} {v:>6}  {str(ref):>6}")
print("=" * 62)

# ══════════════════════════════════════════════
# ETAPA 4: PROCESSAR REGISTROS
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("ETAPA 4: Processando registros")
print("=" * 60)

records = []
by_sup = {}; by_orc = {}; by_mes = {}; by_uf = {}
by_etapa = {}; by_band = {}
sla_stats = {'backlog':0,'criado_em':0,'sem_data':0}
temp_stats = {'envio_real':0,'fallback_modify':0,'sem_data':0}
temp_sem_ref = 0
sup_fonte_cnt = {'campo_real':0,'responsavel_supervisor':0,'historico':0}
orc_fonte_cnt = {'campo_real':0,'responsavel_orc':0,'historico':0}
c38138_found = None

for q in all_quotes:
    qid   = str(q.get('ID',''))
    title = str(q.get('TITLE') or '')
    sid   = str(q.get('STATUS_ID') or '')

    etapa = get_etapa(sid)
    grupo = get_grupo(etapa)

    # UF
    uf_raw = str(q.get(FIELD_MAP['f_estado']) or '').strip().upper()
    uf = uf_raw if uf_raw in UFS_VALIDAS else extrair_uf(title)

    # Bandeira
    bandeira = get_bandeira(title, q.get(FIELD_MAP['f_bandeira']) or '')

    # Pessoa responsavel (nome via users ou vazio)
    assigned_id   = str(q.get('ASSIGNED_BY_ID') or '')
    assigned_name = users.get(assigned_id, '')

    # Supervisor
    campo_sup = str(q.get(FIELD_MAP['f_supervisor']) or '')
    sup, sup_src = get_supervisor(campo_sup, assigned_name, title, bandeira, uf)
    sup_fonte_cnt[sup_src] = sup_fonte_cnt.get(sup_src, 0) + 1

    # Orçamentista
    campo_elab = str(q.get(FIELD_MAP['f_elaborado_por']) or '')
    orc, orc_src = get_orcamentista(campo_elab, assigned_name, bandeira)
    orc_fonte_cnt[orc_src] = orc_fonte_cnt.get(orc_src, 0) + 1

    valor     = float(q.get('OPPORTUNITY') or 0)
    dt_criado = parse_dt(q.get('DATE_CREATE'))
    dt_modify = parse_dt(q.get('DATE_MODIFY'))
    dt_back   = parse_dt(q.get(FIELD_MAP['f_data_backlog']))
    dt_envio  = parse_dt(q.get(FIELD_MAP['f_data_envio']))

    mes       = dt_criado.strftime('%Y-%m') if dt_criado else ''
    mes_label = dt_criado.strftime('%b/%y') if dt_criado else ''
    envio_str = dt_envio.strftime('%d/%m/%Y') if dt_envio else (dt_criado.strftime('%d/%m/%Y') if dt_criado else '-')
    dia_envio = dt_envio.strftime('%Y-%m-%d') if dt_envio else ''

    tipo, _ = get_tipo(q.get(FIELD_MAP['f_tipo_solicitacao']) or '', qid)
    sla, sla_src = calc_sla(dt_back, dt_criado, dt_envio, tipo)
    sla_stats[sla_src if sla_src in sla_stats else 'sem_data'] += 1

    temp, temp_src = calc_temperatura(dt_envio, dt_modify, etapa)
    if etapa == 'ENVIADO':
        if temp_src == 'sem_data': temp_sem_ref += 1
        else: temp_stats[temp_src] = temp_stats.get(temp_src, 0) + 1

    prop = str(q.get(FIELD_MAP['f_numero_proposta']) or '').strip()
    if not prop:
        m2 = re.search(r'(C\d{4,6}-\d{2}\w*)', title)
        prop = m2.group(1) if m2 else qid

    record = {
        'prop': prop, 'loja': title[:80],
        'supervisor': sup, 'sup_fonte': sup_src,
        'cliente': bandeira,
        'orc': orc, 'orc_fonte': orc_src,
        'status': grupo, 'etapa': etapa, 'status_id': sid,
        'sla': sla, 'valor': round(valor, 2),
        'envio': envio_str, 'dia_envio': dia_envio,
        'mes': mes, 'mes_label': mes_label,
        'tipo': tipo, 'uf': uf,
        'temperatura': temp, 'temp_fonte': temp_src,
    }
    records.append(record)

    if '38138' in prop:
        c38138_found = record
        print(f"  ✓ C38138-26: etapa={etapa} sup={sup} orc={orc} temp={temp} sla={sla}")

    # Acumuladores
    def acum(d, key, valor, grupo, etapa):
        if key not in d:
            d[key] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0,'backlog':0}
        d[key]['total'] += 1; d[key]['valor'] += valor
        if grupo == 'APROVADO': d[key]['aprovado'] += 1
        elif grupo == 'REPROVADO': d[key]['reprovado'] += 1
        else: d[key]['aguardando'] += 1
        if etapa in ('BACKLOG_GERAL','BACKLOG_ZAMP'): d[key]['backlog'] += 1

    acum(by_sup, sup, valor, grupo, etapa)

    if orc not in by_orc:
        by_orc[orc] = {'total':0,'aprovado':0,'reprovado':0,'valor':0.0}
    by_orc[orc]['total'] += 1; by_orc[orc]['valor'] += valor
    if grupo == 'APROVADO': by_orc[orc]['aprovado'] += 1
    elif grupo == 'REPROVADO': by_orc[orc]['reprovado'] += 1

    if mes:
        km = (mes, sup)
        if km not in by_mes:
            by_mes[km] = {'mes_str':mes,'Supervisor':sup,'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
        by_mes[km]['total'] += 1; by_mes[km]['valor'] += valor
        if grupo == 'APROVADO': by_mes[km]['aprovado'] += 1
        elif grupo == 'REPROVADO': by_mes[km]['reprovado'] += 1
        else: by_mes[km]['aguardando'] += 1

    uf_key = uf or 'NÃO IDENTIFICADO'
    if uf_key not in by_uf:
        by_uf[uf_key] = {'total':0,'aprovado':0,'valor':0.0}
    by_uf[uf_key]['total'] += 1; by_uf[uf_key]['valor'] += valor
    if grupo == 'APROVADO': by_uf[uf_key]['aprovado'] += 1

    by_etapa[etapa] = by_etapa.get(etapa, 0) + 1

    if bandeira not in by_band:
        by_band[bandeira] = {'total':0,'aprovado':0,'valor':0.0,'enviados_hoje':0}
    by_band[bandeira]['total'] += 1; by_band[bandeira]['valor'] += valor
    if grupo == 'APROVADO': by_band[bandeira]['aprovado'] += 1
    if dia_envio == datetime.now().strftime('%Y-%m-%d'):
        by_band[bandeira]['enviados_hoje'] += 1

# ══════════════════════════════════════════════
# ETAPA 5: ESTATÍSTICAS
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("ETAPA 5: Estatísticas")
print("=" * 60)

total_r      = len(records)
aprovado_r   = sum(1 for r in records if r['status']=='APROVADO')
reprovado_r  = sum(1 for r in records if r['status']=='REPROVADO')
aguardando_r = total_r - aprovado_r - reprovado_r
valor_total  = sum(r['valor'] for r in records)
taxa_geral   = round(aprovado_r/total_r*100,1) if total_r else 0

print(f"Total: {total_r} | Aprovado: {aprovado_r} | Aguardando: {aguardando_r} | Recusado: {reprovado_r}")
print(f"Valor: R$ {round(valor_total/1000)}k | Taxa: {taxa_geral}%")
print(f"\nEtapas:")
for etapa, cnt in sorted(by_etapa.items(), key=lambda x:-x[1]):
    ref = VOLUMES_KANBAN.get(etapa, '-')
    diff = cnt - ref if isinstance(ref, int) else '-'
    print(f"  {etapa:<25} {cnt:>5}  (Kanban: {ref}, diff: {diff})")
print(f"\nSupervisor fonte: {sup_fonte_cnt}")
print(f"Orcamentista fonte: {orc_fonte_cnt}")
print(f"SLA: {sla_stats}")
print(f"Temperatura: envio_real={temp_stats.get('envio_real',0)} fallback={temp_stats.get('fallback_modify',0)} sem_ref={temp_sem_ref}")

meses_stats = {}
for r in records:
    m = r['mes']
    if not m: continue
    if m not in meses_stats:
        meses_stats[m] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0}
    meses_stats[m]['total'] += 1; meses_stats[m]['valor'] += r['valor']
    if r['status']=='APROVADO': meses_stats[m]['aprovado'] += 1
    elif r['status']=='REPROVADO': meses_stats[m]['reprovado'] += 1
    else: meses_stats[m]['aguardando'] += 1

meses_ord = sorted(meses_stats.keys())
print(f"\nPor mês:")
for m in meses_ord:
    s = meses_stats[m]
    print(f"  {m}: {s['total']} propostas | {s['aprovado']} aprovadas | R$ {round(s['valor']/1000)}k")

jun_count = meses_stats.get('2026-06',{}).get('total',0)
print(f"\n✓ JUNHO 2026: {jun_count} propostas")
if c38138_found:
    print(f"\n✓ C38138-26:\n  {json.dumps(c38138_found, ensure_ascii=False, indent=4)}")
else:
    print(f"\n⚠ C38138-26 NAO encontrada")

# ══════════════════════════════════════════════
# ETAPA 6: MONTAR PAYLOAD
# ══════════════════════════════════════════════
zamp  = by_band.get('ZAMP-BK',{})
botic = by_band.get('Boticário',{})
taxa_zamp  = round(zamp.get('aprovado',0)/zamp['total']*100,1) if zamp.get('total') else 0
taxa_botic = round(botic.get('aprovado',0)/botic['total']*100,1) if botic.get('total') else 0

men_labels = [datetime.strptime(m,'%Y-%m').strftime('%b/%y') for m in meses_ord]
men_total  = [meses_stats[m]['total']     for m in meses_ord]
men_aprov  = [meses_stats[m]['aprovado']  for m in meses_ord]
men_aguar  = [meses_stats[m]['aguardando']for m in meses_ord]
men_reprov = [meses_stats[m]['reprovado'] for m in meses_ord]
men_valor  = [round(meses_stats[m]['valor']/1000) for m in meses_ord]
men_taxa   = [round(meses_stats[m]['aprovado']/meses_stats[m]['total']*100,1) if meses_stats[m]['total'] else 0 for m in meses_ord]

sup_analysis = []
for sup, d in sorted(by_sup.items(), key=lambda x:-x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    sup_analysis.append({'Supervisor':sup,'total':d['total'],'aprovado':d['aprovado'],
        'aguardando':d['aguardando'],'reprovado':d['reprovado'],'backlog':d['backlog'],
        'taxa_aprov':taxa,'score':d['total']-d['aprovado'],'valor':round(d['valor'],0)})

orc_analysis = []
for orc, d in sorted(by_orc.items(), key=lambda x:-x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    orc_analysis.append({'Orcamentista':orc,'total':d['total'],'aprovado':d['aprovado'],
        'reprovado':d['reprovado'],'taxa_aprov':taxa,'valor':round(d['valor'],0)})

uf_analysis = []
for uf_k, d in sorted(by_uf.items(), key=lambda x:-x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    uf_analysis.append({'uf':uf_k,'total':d['total'],'aprovado':d['aprovado'],
        'taxa_aprov':taxa,'valor':round(d['valor'],0)})

band_analysis = []
for band, d in sorted(by_band.items(), key=lambda x:-x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    band_analysis.append({'bandeira':band,'total':d['total'],'aprovado':d['aprovado'],
        'taxa_aprov':taxa,'valor':round(d['valor'],0),'enviados_hoje':d['enviados_hoje']})

temp_niveis = {k: sum(1 for r in records if r['etapa']=='ENVIADO' and r['temperatura']==k)
               for k in ('QUENTE','MORNO','ESFRIANDO','FRIO','SEM_DATA')}

payload = {
    'records': records,
    'sup_analysis': sup_analysis,
    'orc_analysis': orc_analysis,
    'uf_analysis':  uf_analysis,
    'band_analysis':band_analysis,
    'sup_mes_data': sorted(by_mes.values(), key=lambda x:(x['mes_str'],x['Supervisor'])),
    'men_labels': men_labels, 'men_total': men_total, 'men_aprov': men_aprov,
    'men_aguar':  men_aguar,  'men_reprov':men_reprov,'men_valor': men_valor,
    'men_taxa':   men_taxa,   'meses_ord': meses_ord,
    'field_map':  FIELD_MAP,  'etapas':   by_etapa,
    'temp_niveis':temp_niveis,
    'kpis': {
        'total': total_r, 'aprovado': aprovado_r, 'aguardando': aguardando_r,
        'reprovado': reprovado_r, 'valor': round(valor_total,0),
        'taxa_geral': taxa_geral, 'taxa_zamp': taxa_zamp, 'taxa_botic': taxa_botic,
        'aprov_zamp': zamp.get('aprovado',0), 'total_zamp': zamp.get('total',0),
        'aprov_botic': botic.get('aprovado',0), 'total_botic': botic.get('total',0),
        'jun_total': jun_count,
        'sla_backlog': sla_stats['backlog'], 'sla_fallback': sla_stats['criado_em'],
        'sla_sem_data': sla_stats['sem_data'], 'temp_sem_ref': temp_sem_ref,
        'etapa_mplan':          by_etapa.get('MPLAN',0),
        'etapa_aprov_sup':      by_etapa.get('APROVADO_SUPERVISOR',0),
        'etapa_backlog_geral':  by_etapa.get('BACKLOG_GERAL',0),
        'etapa_backlog_zamp':   by_etapa.get('BACKLOG_ZAMP',0),
        'etapa_elaboracao':     by_etapa.get('ELABORACAO',0),
        'etapa_validacao':      by_etapa.get('VALIDACAO',0),
        'etapa_reavaliacao':    by_etapa.get('REAVALIACAO',0),
        'etapa_enviado':        by_etapa.get('ENVIADO',0),
        'etapa_aceito':         by_etapa.get('ACEITO',0),
        'etapa_recusado':       by_etapa.get('RECUSADO',0),
        'etapa_nao_aprovadas':  by_etapa.get('NAO_APROVADAS',0),
        'data_atualizacao': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
}

with open('data.json','w',encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False, default=str)

print(f"\ndata.json salvo com {total_r} registros.")
