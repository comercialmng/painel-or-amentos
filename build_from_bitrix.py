#!/usr/bin/env python3
"""
GitHub Actions - Busca dados do Bitrix24 (crm.quote) e gera data.json
v2.1 - Diagnostico STATUS_ID adicionado (sem alteracao de logica)
"""
import os, json, requests, sys
from datetime import datetime, timedelta

WEBHOOK = os.environ.get('BITRIX_WEBHOOK', '')
if not WEBHOOK:
    print("ERRO: BITRIX_WEBHOOK nao definido")
    sys.exit(1)

# ══ SUPERVISORES ══
SUPERVISORES_OFICIAIS = [
    'Igor Lajusticia','Humberto Cavalcanti','Franckllyn Moreira','Vagner de Brito',
    'Raul Rodrigues','Fernando Melgarejo','Flavio Bezerra','Thiago dos Anjos',
    'Edwilder Costa','Ronie Bandeira','Daniel Brandao','Bruno Lima','Bruno Almeida',
    'Andre Jose','Elton Douglas','Pedro Vargas','Felipe Benicio',
    # com acentos
    'Flávio Bezerra','André José','Daniel Brandão','Franckllyn Moreira',
]
NAME_MAP = {
    'Ronie Bandeira Lima':'Ronie Bandeira',
    'Franckllyn Moreira da Silva':'Franckllyn Moreira',
    'Raul Rodrigues de Sales':'Raul Rodrigues',
    'Raul Sales Rodrigues':'Raul Rodrigues',
    'Fernando Melgarejo de Lima':'Fernando Melgarejo',
    'Elton Douglas Lourenco Xavier':'Elton Douglas',
    'Elton Douglas Lourenço Xavier':'Elton Douglas',
    'Andre Jose do Nascimento':'André José',
    'Washington Kalleby Lima Pereira':'Ronie Bandeira',
    'Washington Kalleby':'Ronie Bandeira',
    'Jefferson Guedes':'Felipe Benício',
    'Jefferson Guedes ':'Felipe Benício',
    'Geniclecio Fabio Amorim':'Thiago dos Anjos',
    'Geniclécio Fabio Amorim':'Thiago dos Anjos',
    'Fabio Amorim':'Thiago dos Anjos',
    'Fábio Amorim':'Thiago dos Anjos',
    'Moyses Souza':'Thiago dos Anjos',
    'Isis Martins':'Thiago dos Anjos',
    'Matheus Lourenco':'Thiago dos Anjos',
    'Matheus Lourenço':'Thiago dos Anjos',
    'Joatan Mendes':'Thiago dos Anjos',
    'Jorge':'Humberto Cavalcanti',
    'Lucas Garrido':'Ronie Bandeira',
    'Marcos Amorim':'Ronie Bandeira',
    'Paulo Henrique':'Ronie Bandeira',
    'ADM Maneng':'Ronie Bandeira',
    'Marcelo Vergne':'Bruno Lima',
    'Rodrigo Silva':'Ronie Bandeira',
    'Adelaide Matos': None,
    'Nayra Dutra':'Francyne Lima',
    'Vinicius Santana':'Thiago dos Anjos',
    'Felipe Benicio':'Felipe Benício',
    'Felipe Benício':'Felipe Benício',
}

def norm_sup(name):
    if not name: return 'Ronie Bandeira'
    name = str(name).strip()
    m = NAME_MAP.get(name)
    if m is None and name in NAME_MAP: return None
    if m: return m
    for s in SUPERVISORES_OFICIAIS:
        if s.lower() == name.lower(): return s
    return 'Ronie Bandeira'

def get_bandeira(title='', band=''):
    c = (str(title or '') + ' ' + str(band or '')).upper()
    if any(x in c for x in ['ZAMP','BKN','BKB','BURGER KING',' BK ','OSZ']): return 'ZAMP-BK'
    if any(x in c for x in ['BOTICARIO','BOTICÁRIO']): return 'Boticário'
    if 'LEROY' in c: return 'Leroy Merlin'
    if 'BRADESCO' in c: return 'Bradesco'
    if 'FUNDAÇÃO' in c or 'FUNDACAO' in c: return 'Fundação'
    if any(x in c for x in ['CARREFOUR','ASSAI','GPA','GIGA']): return 'Carrefour/Grupo'
    if "SAM'S" in c or 'SAMS' in c: return 'Sams'
    if 'MERCANTIL' in c: return 'Banco Mercantil'
    if 'OBRAMAX' in c: return 'Obramax'
    if 'SMARTIFT' in c or 'SMARTFIT' in c: return 'SmartFit'
    if 'ATAKAREJO' in c: return 'Atakarejo'
    if 'GBARBOSA' in c: return 'GBarbosa'
    if 'AUTOZONE' in c: return 'Autozone'
    return 'Outros'

def get_status(s):
    if not s: return 'AGUARDANDO'
    s = str(s).upper()
    if any(x in s for x in ['APPROVED','WON','ACEITO','APROV','ACCEPTED']): return 'APROVADO'
    if any(x in s for x in ['DECLINED','LOSE','RECUS','REPROV','NAO APROV','NÃO APROV']): return 'REPROVADO'
    return 'AGUARDANDO'

def parse_dt(val):
    if not val: return None
    try:
        s = str(val).replace('T',' ').split('+')[0].split('.')[0].strip()
        return datetime.fromisoformat(s)
    except:
        return None

def calc_sla(dt_backlog, dt_criado, dt_envio, tipo):
    prazo = 24 if str(tipo or '').upper() == 'EMERGENCIAL' else 72
    dt_entrada = dt_backlog or dt_criado
    if not dt_entrada or not dt_envio:
        return '-', 'SEM_DATA'
    horas = (dt_envio - dt_entrada).total_seconds() / 3600
    if horas < 0:
        horas = abs(horas)
    resultado = 'CUMPRIU' if horas <= prazo else 'NÃO CUMPRIU'
    fonte = 'backlog' if dt_backlog else 'criado_em'
    return resultado, fonte

# ══ ETAPA 1: DESCOBERTA DE CAMPOS ══
print("=" * 60)
print("ETAPA 1: Descoberta de campos UF_CRM via crm.quote.fields")
print("=" * 60)

FIELD_MAP = {}
FIELD_TYPES = {}

try:
    r = requests.get(WEBHOOK + 'crm.quote.fields.json', timeout=30)
    fields_data = r.json()
    all_fields = fields_data.get('result', {})

    TARGETS = {
        'número da proposta':   'f_numero_proposta',
        'numero da proposta':   'f_numero_proposta',
        'supervisor':           'f_supervisor',
        'elaborado por':        'f_elaborado_por',
        'tipo de solicitação':  'f_tipo_solicitacao',
        'tipo de solicitacao':  'f_tipo_solicitacao',
        'data de entrada no backlog': 'f_data_backlog',
        'data de envio da proposta':  'f_data_envio',
        'bandeira':             'f_bandeira',
        'orçamentista':         'f_orcamentista',
        'orcamentista':         'f_orcamentista',
    }

    print(f"\nTotal de campos no módulo Quote: {len(all_fields)}")
    print("\nCAMPOS CUSTOMIZADOS (UF_CRM_*):")
    print(f"{'Código':<40} {'Tipo':<20} {'Label'}")
    print("-" * 90)

    for code, finfo in sorted(all_fields.items()):
        if not code.startswith('UF_'):
            continue
        label = finfo.get('listLabel') or finfo.get('title') or finfo.get('formLabel') or ''
        ftype = finfo.get('type', '')
        label_clean = str(label).lower().strip()
        print(f"{code:<40} {ftype:<20} {label}")
        for target_label, key in TARGETS.items():
            if target_label in label_clean:
                FIELD_MAP[key] = code
                FIELD_TYPES[key] = ftype

    print("\nCAMPOS PADRÃO RELEVANTES:")
    std = ['ID','TITLE','STATUS_ID','OPPORTUNITY','DATE_CREATE',
           'ASSIGNED_BY_ID','STAGE_ID','CLOSED','DATE_MODIFY']
    for code in std:
        if code in all_fields:
            finfo = all_fields[code]
            print(f"  {code:<30} {finfo.get('type',''):<15} {finfo.get('title','')}")

except Exception as e:
    print(f"ERRO ao buscar campos: {e}")

print("\nMAPEAMENTO DESCOBERTO:")
for key, code in FIELD_MAP.items():
    print(f"  {key:<30} -> {code}")

FALLBACKS = {
    'f_numero_proposta': ['UF_CRM_QUOTE_NUMERO','UF_CRM_1_NUMERO_PROPOSTA','UF_CRM_NUMBER'],
    'f_supervisor':      ['UF_CRM_QUOTE_SUPERVISOR','UF_CRM_1_SUPERVISOR','UF_CRM_SUPERVISOR'],
    'f_elaborado_por':   ['UF_CRM_QUOTE_ELABORADO','UF_CRM_1_ELABORADO_POR','UF_CRM_ELABORADO'],
    'f_tipo_solicitacao':['UF_CRM_QUOTE_TIPO','UF_CRM_1_TIPO_SOLIC','UF_CRM_TIPO_SOLICITACAO'],
    'f_data_backlog':    ['UF_CRM_QUOTE_DATA_BACKLOG','UF_CRM_1_DATA_BACKLOG','UF_CRM_BACKLOG'],
    'f_data_envio':      ['UF_CRM_QUOTE_DATA_ENVIO','UF_CRM_1_DATA_ENVIO','UF_CRM_DATA_ENVIO'],
    'f_bandeira':        ['UF_CRM_QUOTE_BANDEIRA','UF_CRM_1_BANDEIRA','UF_CRM_BANDEIRA'],
}
for key, candidates in FALLBACKS.items():
    if key not in FIELD_MAP:
        FIELD_MAP[key] = candidates[0]
        print(f"  {key:<30} -> {candidates[0]} (FALLBACK - nao descoberto)")

SELECT_FIELDS = list(set([
    'ID', 'TITLE', 'STATUS_ID', 'OPPORTUNITY', 'DATE_CREATE',
    'ASSIGNED_BY_ID', 'DATE_MODIFY',
    FIELD_MAP.get('f_numero_proposta',''),
    FIELD_MAP.get('f_supervisor',''),
    FIELD_MAP.get('f_elaborado_por',''),
    FIELD_MAP.get('f_tipo_solicitacao',''),
    FIELD_MAP.get('f_data_backlog',''),
    FIELD_MAP.get('f_data_envio',''),
    FIELD_MAP.get('f_bandeira',''),
    FIELD_MAP.get('f_orcamentista',''),
]))
SELECT_FIELDS = [f for f in SELECT_FIELDS if f]

print(f"\nSELECT total: {len(SELECT_FIELDS)} campos")
print(f"  {SELECT_FIELDS}")

# ══ ETAPA 2: USUARIOS (mantida por compatibilidade) ══
print("\n" + "=" * 60)
print("ETAPA 2: Buscando usuários")
print("=" * 60)
users = {}
try:
    start_u = 0
    while True:
        r = requests.get(WEBHOOK + 'user.get.json',
            params=[('FILTER[ACTIVE]','Y'),('start', start_u)], timeout=30)
        data = r.json()
        batch = data.get('result', [])
        for u in batch:
            users[str(u['ID'])] = (u.get('NAME','') + ' ' + u.get('LAST_NAME','')).strip()
        if not data.get('next'):
            break
        start_u = data['next']
    print(f"  {len(users)} usuários encontrados")
except Exception as e:
    print(f"  Aviso: {e}")

# ══ ETAPA 3: BUSCAR ORCAMENTOS ══
print("\n" + "=" * 60)
print("ETAPA 3: Buscando orçamentos (todas as páginas)")
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
        if not batch:
            print(f"  Sem resultados em start={start}")
            break

        all_quotes.extend(batch)
        total_api = data.get('total', len(all_quotes))
        print(f"  {len(all_quotes)}/{total_api} (start={start})")

        next_start = data.get('next')
        if next_start:
            start = next_start
        else:
            start += len(batch)

        if len(all_quotes) >= total_api:
            break

    except Exception as e:
        print(f"  Erro: {e}")
        break

print(f"\nTotal obtido: {len(all_quotes)} orçamentos")

# ══ DIAGNÓSTICO STATUS_ID ══
print("\n" + "=" * 60)
print("DIAGNÓSTICO: STATUS_ID encontrados no dataset")
print("=" * 60)
status_brutos = {}
for q in all_quotes:
    s = q.get('STATUS_ID') or 'VAZIO'
    status_brutos[s] = status_brutos.get(s, 0) + 1
print(f"\n{'STATUS_ID':<35} {'QUANTIDADE':>10}")
print("-" * 47)
for k, v in sorted(status_brutos.items(), key=lambda x: -x[1]):
    print(f"{k:<35} {v:>10}")
print("-" * 47)
print(f"{'TOTAL':<35} {len(all_quotes):>10}")
print("=" * 60)

# Debug primeiro registro
if all_quotes:
    q0 = all_quotes[0]
    print(f"\nDebug primeiro registro:")
    print(f"  ID: {q0.get('ID')}")
    print(f"  TITLE: {str(q0.get('TITLE',''))[:60]}")
    print(f"  STATUS_ID: {q0.get('STATUS_ID','N/A')}")
    print(f"  OPPORTUNITY: {q0.get('OPPORTUNITY','N/A')}")
    print(f"  DATE_CREATE: {q0.get('DATE_CREATE','N/A')}")
    f_num  = FIELD_MAP.get('f_numero_proposta','')
    f_sup  = FIELD_MAP.get('f_supervisor','')
    f_elab = FIELD_MAP.get('f_elaborado_por','')
    f_tipo = FIELD_MAP.get('f_tipo_solicitacao','')
    f_back = FIELD_MAP.get('f_data_backlog','')
    f_envio = FIELD_MAP.get('f_data_envio','')
    print(f"  Número proposta ({f_num}): {q0.get(f_num,'N/A')}")
    print(f"  Supervisor ({f_sup}): {q0.get(f_sup,'N/A')}")
    print(f"  Elaborado por ({f_elab}): {q0.get(f_elab,'N/A')}")
    print(f"  Tipo ({f_tipo}): {q0.get(f_tipo,'N/A')}")
    print(f"  Data Backlog ({f_back}): {q0.get(f_back,'N/A')}")
    print(f"  Data Envio ({f_envio}): {q0.get(f_envio,'N/A')}")

# ══ ETAPA 4: PROCESSAR ══
print("\n" + "=" * 60)
print("ETAPA 4: Processando registros")
print("=" * 60)

records = []
by_sup = {}
by_mes = {}
sla_stats = {'backlog':0, 'fallback_criado':0, 'sem_data':0}
c38138_found = None

for q in all_quotes:
    status = get_status(q.get('STATUS_ID',''))

    f_sup = FIELD_MAP.get('f_supervisor','')
    sup_raw = q.get(f_sup) or users.get(str(q.get('ASSIGNED_BY_ID','')), '')
    sup = norm_sup(sup_raw)
    if sup is None:
        continue

    f_band = FIELD_MAP.get('f_bandeira','')
    bandeira = get_bandeira(q.get('TITLE',''), q.get(f_band,''))

    valor = float(q.get('OPPORTUNITY') or 0)

    dt_criado  = parse_dt(q.get('DATE_CREATE'))
    f_back     = FIELD_MAP.get('f_data_backlog','')
    f_envio_f  = FIELD_MAP.get('f_data_envio','')
    dt_backlog = parse_dt(q.get(f_back))
    dt_envio   = parse_dt(q.get(f_envio_f))

    mes       = dt_criado.strftime('%Y-%m') if dt_criado else ''
    mes_label = dt_criado.strftime('%b/%y') if dt_criado else ''
    envio_str = dt_envio.strftime('%d/%m/%Y') if dt_envio else (
        dt_criado.strftime('%d/%m/%Y') if dt_criado else '-'
    )

    f_tipo = FIELD_MAP.get('f_tipo_solicitacao','')
    tipo = str(q.get(f_tipo) or 'PROGRAMADA').upper()
    if 'EMERG' in tipo:
        tipo = 'EMERGENCIAL'
    else:
        tipo = 'PROGRAMADA'

    sla, sla_fonte = calc_sla(dt_backlog, dt_criado, dt_envio, tipo)
    sla_stats[{'backlog':'backlog','criado_em':'fallback_criado','SEM_DATA':'sem_data'}.get(sla_fonte,'sem_data')] += 1

    f_elab = FIELD_MAP.get('f_elaborado_por','')
    f_orc  = FIELD_MAP.get('f_orcamentista','')
    orc = q.get(f_elab) or q.get(f_orc)
    if not orc:
        orc = 'Ana Beatriz Araújo' if bandeira == 'ZAMP-BK' else 'Francyne Lima'

    f_num = FIELD_MAP.get('f_numero_proposta','')
    prop = q.get(f_num) or ''
    if not prop:
        import re
        m = re.search(r'(C\d{4,6}-\d{2}\w*)', str(q.get('TITLE','')))
        prop = m.group(1) if m else str(q.get('ID',''))

    cliente = str(q.get('TITLE') or '')[:50]

    record = {
        'prop': str(prop),
        'loja': cliente,
        'supervisor': sup,
        'cliente': bandeira,
        'orc': str(orc),
        'status': status,
        'sla': sla,
        'valor': round(valor, 2),
        'envio': envio_str,
        'dia_envio': dt_envio.strftime('%Y-%m-%d') if dt_envio else '',
        'mes': mes,
        'mes_label': mes_label,
        'tipo': tipo,
        'uf': '-',
    }
    records.append(record)

    if '38138' in str(prop):
        c38138_found = record
        print(f"  ✓ C38138-26 encontrado: status={status} sup={sup} valor={valor} sla={sla}")

    if sup not in by_sup:
        by_sup[sup] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
    by_sup[sup]['total'] += 1
    by_sup[sup]['valor'] += valor
    if status == 'APROVADO': by_sup[sup]['aprovado'] += 1
    elif status == 'REPROVADO': by_sup[sup]['reprovado'] += 1
    else: by_sup[sup]['aguardando'] += 1

    if mes:
        key = (mes, sup)
        if key not in by_mes:
            by_mes[key] = {'mes_str':mes,'Supervisor':sup,'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
        by_mes[key]['total'] += 1
        by_mes[key]['valor'] += valor
        if status == 'APROVADO': by_mes[key]['aprovado'] += 1
        elif status == 'REPROVADO': by_mes[key]['reprovado'] += 1
        else: by_mes[key]['aguardando'] += 1

# ══ ETAPA 5: STATS ══
print("\n" + "=" * 60)
print("ETAPA 5: Estatísticas")
print("=" * 60)

total_r     = len(records)
aprovado_r  = sum(1 for r in records if r['status']=='APROVADO')
aguardando_r= sum(1 for r in records if r['status']=='AGUARDANDO')
reprovado_r = sum(1 for r in records if r['status']=='REPROVADO')
valor_total = sum(r['valor'] for r in records)

meses_stats = {}
for r in records:
    if not r['mes']: continue
    m = r['mes']
    if m not in meses_stats:
        meses_stats[m] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0}
    meses_stats[m]['total'] += 1
    meses_stats[m]['valor'] += r['valor']
    if r['status']=='APROVADO': meses_stats[m]['aprovado'] += 1
    elif r['status']=='REPROVADO': meses_stats[m]['reprovado'] += 1
    else: meses_stats[m]['aguardando'] += 1

meses_ord = sorted(meses_stats.keys())

print(f"\nTotal registros: {total_r}")
print(f"Status: {aprovado_r} aprovados | {aguardando_r} aguardando | {reprovado_r} reprovados")
print(f"Valor total: R$ {round(valor_total/1000)}k")
print(f"\nPor mês:")
for m in meses_ord:
    s = meses_stats[m]
    print(f"  {m}: {s['total']} propostas | {s['aprovado']} aprovadas | R$ {round(s['valor']/1000)}k")

print(f"\nSLA calculado:")
print(f"  Com Data Backlog (P1): {sla_stats['backlog']}")
print(f"  Fallback DATE_CREATE (P2): {sla_stats['fallback_criado']}")
print(f"  Sem data suficiente: {sla_stats['sem_data']}")

jun_count = meses_stats.get('2026-06', {}).get('total', 0)
print(f"\n✓ JUNHO 2026: {jun_count} propostas")

if c38138_found:
    print(f"\n✓ C38138-26 encontrada:")
    print(f"  {json.dumps(c38138_found, ensure_ascii=False, indent=4)}")
else:
    print(f"\n⚠ C38138-26 NAO encontrada no resultado")

# ══ MONTAR PAYLOAD ══
sup_analysis = []
for sup, d in sorted(by_sup.items(), key=lambda x: -x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100, 1) if d['total'] else 0
    sup_analysis.append({
        'Supervisor': sup, 'total': d['total'], 'aprovado': d['aprovado'],
        'aguardando': d['aguardando'], 'reprovado': d['reprovado'],
        'taxa_aprov': taxa, 'score': d['total'] - d['aprovado'],
        'valor': round(d['valor'], 0)
    })

sup_mes_data = sorted(by_mes.values(), key=lambda x: (x['mes_str'], x['Supervisor']))

men_total  = [meses_stats[m]['total']    for m in meses_ord]
men_aprov  = [meses_stats[m]['aprovado'] for m in meses_ord]
men_aguar  = [meses_stats[m]['aguardando'] for m in meses_ord]
men_reprov = [meses_stats[m]['reprovado'] for m in meses_ord]
men_valor  = [round(meses_stats[m]['valor']/1000) for m in meses_ord]
men_taxa   = [round(meses_stats[m]['aprovado']/meses_stats[m]['total']*100,1)
              if meses_stats[m]['total'] else 0 for m in meses_ord]
men_labels = [datetime.strptime(m,'%Y-%m').strftime('%b/%y') for m in meses_ord]

by_band = {}
for r in records:
    b = r['cliente']
    if b not in by_band:
        by_band[b] = {'total':0,'aprovado':0,'valor':0}
    by_band[b]['total'] += 1
    by_band[b]['valor'] += r['valor']
    if r['status']=='APROVADO': by_band[b]['aprovado'] += 1

zamp  = by_band.get('ZAMP-BK',{})
botic = by_band.get('Boticário',{})
taxa_geral = round(aprovado_r/total_r*100,1) if total_r else 0
taxa_zamp  = round(zamp.get('aprovado',0)/zamp.get('total',1)*100,1)  if zamp.get('total')  else 0
taxa_botic = round(botic.get('aprovado',0)/botic.get('total',1)*100,1) if botic.get('total') else 0

payload = {
    'records': records,
    'sup_analysis': sup_analysis,
    'sup_mes_data': sup_mes_data,
    'men_labels': men_labels,
    'men_total': men_total,
    'men_aprov': men_aprov,
    'men_aguar': men_aguar,
    'men_reprov': men_reprov,
    'men_valor': men_valor,
    'men_taxa': men_taxa,
    'meses_ord': meses_ord,
    'field_map': FIELD_MAP,
    'kpis': {
        'total': total_r,
        'aprovado': aprovado_r,
        'aguardando': aguardando_r,
        'reprovado': reprovado_r,
        'valor': round(valor_total, 0),
        'taxa_geral': taxa_geral,
        'taxa_zamp': taxa_zamp,
        'taxa_botic': taxa_botic,
        'aprov_zamp': zamp.get('aprovado',0),
        'total_zamp': zamp.get('total',0),
        'aprov_botic': botic.get('aprovado',0),
        'total_botic': botic.get('total',0),
        'data_atualizacao': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'jun_total': jun_count,
        'sla_backlog': sla_stats['backlog'],
        'sla_fallback': sla_stats['fallback_criado'],
        'sla_sem_data': sla_stats['sem_data'],
    }
}

with open('data.json','w',encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False, default=str)

print(f"\ndata.json salvo com {total_r} registros.")
