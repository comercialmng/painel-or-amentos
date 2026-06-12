#!/usr/bin/env python3
"""
build_from_bitrix.py — Busca crm.quote do Bitrix24 e gera data.json
"""
import os, json, re, requests, sys
from datetime import datetime

WEBHOOK = os.environ.get('BITRIX_WEBHOOK', '')
if not WEBHOOK:
    print("ERRO: BITRIX_WEBHOOK nao definido")
    sys.exit(1)

SUPERVISORES_OFICIAIS = [
    'Igor Lajusticia','Humberto Cavalcanti','Franckllyn Moreira','Vagner de Brito',
    'Raul Rodrigues','Fernando Melgarejo','Flávio Bezerra','Thiago dos Anjos',
    'Edwilder Costa','Ronie Bandeira','Daniel Brandão','Bruno Lima','Bruno Almeida',
    'André José','Elton Douglas','Pedro Vargas','Felipe Benício',
]
NAME_MAP = {
    'Ronie Bandeira Lima':'Ronie Bandeira','Franckllyn Moreira da Silva':'Franckllyn Moreira',
    'Raul Rodrigues de Sales':'Raul Rodrigues','Raul Sales Rodrigues':'Raul Rodrigues',
    'Fernando Melgarejo de Lima':'Fernando Melgarejo','Elton Douglas Lourenço Xavier':'Elton Douglas',
    'Andre José do Nascimento':'André José','Washington Kalleby Lima Pereira':'Ronie Bandeira',
    'Washington Kalleby':'Ronie Bandeira','Jefferson Guedes':'Felipe Benício',
    'Geniclécio Fabio Amorim':'Thiago dos Anjos','Fábio Amorim':'Thiago dos Anjos',
    'Moyses Souza':'Thiago dos Anjos','Isis Martins':'Thiago dos Anjos',
    'Matheus Lourenço':'Thiago dos Anjos','Joatan Mendes':'Thiago dos Anjos',
    'Jorge':'Humberto Cavalcanti','Lucas Garrido':'Ronie Bandeira',
    'Marcos Amorim':'Ronie Bandeira','Paulo Henrique':'Ronie Bandeira',
    'ADM Maneng':'Ronie Bandeira','Marcelo Vergne':'Bruno Lima',
    'Rodrigo Silva':'Ronie Bandeira','Adelaide Matos':None,
    'Nayra Dutra':'Francyne Lima','Vinicius Santana':'Thiago dos Anjos',
}
RODRIGO_UF = {
    'SP':'Ronie Bandeira','MG':'Ronie Bandeira','MS':'Ronie Bandeira',
    'TO':'Franckllyn Moreira','DF':'Franckllyn Moreira','GO':'Franckllyn Moreira',
    'SC':'Vagner de Brito','RR':'Vagner de Brito','AP':'Vagner de Brito','PA':'Vagner de Brito',
    'RJ':'Flávio Bezerra',
}

def norm_sup(name, uf=''):
    if not name: return 'Ronie Bandeira'
    name = name.strip()
    m = NAME_MAP.get(name)
    if m is None and name in NAME_MAP: return 'Ronie Bandeira'
    if m: return m
    if name == 'Rodrigo Silva': return RODRIGO_UF.get(uf, 'Ronie Bandeira')
    return name if name in SUPERVISORES_OFICIAIS else 'Ronie Bandeira'

def get_bandeira(title='', band=''):
    c = ((title or '') + ' ' + (band or '')).upper()
    if any(x in c for x in ['ZAMP','BKN','BKB','BURGER KING',' BK ','OSZ']): return 'ZAMP-BK'
    if any(x in c for x in ['BOTICARIO','BOTICÁRIO']): return 'Boticário'
    if 'LEROY' in c: return 'Leroy Merlin'
    if 'BRADESCO' in c: return 'Bradesco'
    if 'FUNDAÇÃO' in c or 'FUNDACAO' in c: return 'Fundação'
    if any(x in c for x in ['CARREFOUR','ASSAI','GPA','GIGA']): return 'Carrefour/Grupo'
    if "SAM'S" in c or 'SAMS' in c: return 'Sams'
    if 'MERCANTIL' in c: return 'Banco Mercantil'
    if 'OBRAMAX' in c: return 'Obramax'
    if any(x in c for x in ['SMARTFIT','SMARTIFT']): return 'SmartFit'
    if 'ATAKAREJO' in c: return 'Atakarejo'
    if 'GBARBOSA' in c: return 'GBarbosa'
    if 'AUTOZONE' in c: return 'Autozone'
    return 'Outros'

def get_status(q):
    """
    Tenta todos os campos possiveis de status do crm.quote.
    No Bitrix24, crm.quote usa STATUS_ID com valores como:
    1=Rascunho, 2=Em processamento, 3=Aprovado, 4=Recusado, 5=Apresentado
    Ou pode usar strings como NEW, APPROVED, DECLINED, etc.
    """
    # Tenta campo STATUS_ID primeiro
    s = str(q.get('STATUS_ID') or '').upper().strip()
    
    # Valores numericos comuns do Bitrix quote
    if s in ('3', 'APPROVED', 'WON', 'ACEITO', 'APROV', 'C', 'P'):
        return 'APROVADO'
    if s in ('4', 'DECLINED', 'LOSE', 'RECUS', 'REPROV', 'F'):
        return 'REPROVADO'
    if s in ('5', 'SENT', 'PRESENTED', 'D'):
        return 'ENVIADO'
    
    # Tenta STAGE_ID
    stage = str(q.get('STAGE_ID') or '').upper().strip()
    if any(x in stage for x in ['APPROV','WON','ACEITO']):
        return 'APROVADO'
    if any(x in stage for x in ['DECLIN','LOSE','REPROV','RECUS']):
        return 'REPROVADO'
    
    # Tenta UF fields customizados
    for field in ['UF_CRM_QUOTE_STATUS','UF_CRM_STATUS']:
        val = str(q.get(field) or '').upper()
        if any(x in val for x in ['APROV','WON','ACEITO']): return 'APROVADO'
        if any(x in val for x in ['REPROV','RECUS','DECLIN']): return 'REPROVADO'
        if any(x in val for x in ['ENVI','SENT','PRESENT']): return 'ENVIADO'
    
    return 'AGUARDANDO'

def get_valor(q):
    """Tenta todos os campos possiveis de valor."""
    for field in ['OPPORTUNITY', 'PRICE', 'AMOUNT', 'UF_CRM_QUOTE_VALOR',
                  'UF_CRM_QUOTE_TOTAL', 'ACCOUNT_CURRENCY_ID']:
        v = q.get(field)
        if v and str(v).strip() not in ('', '0', 'None'):
            try:
                return float(str(v).replace(',','.'))
            except:
                pass
    return 0.0

# ── Buscar usuarios ──
print("Buscando usuarios...")
users = {}
try:
    r = requests.get(WEBHOOK + 'user.get.json',
                     params={'FILTER[ACTIVE]': 'Y', 'select[]': ['ID','NAME','LAST_NAME']},
                     timeout=30)
    for u in r.json().get('result', []):
        users[str(u['ID'])] = (u.get('NAME','') + ' ' + u.get('LAST_NAME','')).strip()
    print(f"  {len(users)} usuarios carregados")
except Exception as e:
    print(f"Aviso usuarios: {e}")

# ── Inspecionar campos disponiveis (primeiro registro) ──
print("Inspecionando campos do crm.quote...")
try:
    r = requests.get(WEBHOOK + 'crm.quote.list.json',
                     params={'order[ID]': 'DESC', 'start': 0},
                     timeout=30)
    sample = r.json().get('result', [])
    if sample:
        print(f"Campos disponiveis: {list(sample[0].keys())}")
        print(f"Amostra STATUS_ID: {sample[0].get('STATUS_ID')}")
        print(f"Amostra OPPORTUNITY: {sample[0].get('OPPORTUNITY')}")
        print(f"Amostra STAGE_ID: {sample[0].get('STAGE_ID')}")
        # Mostra todos campos UF
        uf_fields = [k for k in sample[0].keys() if k.startswith('UF_')]
        print(f"Campos UF: {uf_fields}")
except Exception as e:
    print(f"Erro inspecao: {e}")

# ── Buscar todos os orcamentos de 2026 ──
print("Buscando orcamentos do Bitrix...")
all_quotes = []
start = 0
total_api = 9999

# Seleciona todos os campos relevantes
select_fields = [
    'ID', 'TITLE', 'STATUS_ID', 'STAGE_ID', 'OPPORTUNITY', 'PRICE',
    'DATE_CREATE', 'DATE_MODIFY', 'ASSIGNED_BY_ID', 'CURRENCY_ID',
    'UF_CRM_QUOTE_SUPERVISOR', 'UF_CRM_QUOTE_NUMERO',
    'UF_CRM_QUOTE_BANDEIRA', 'UF_CRM_QUOTE_ORCAMENTISTA',
    'UF_CRM_QUOTE_DATA_ENVIO', 'UF_CRM_QUOTE_STATUS',
    'UF_CRM_BANDEIRA', 'UF_CRM_STATUS',
]

while len(all_quotes) < total_api:
    params = {
        'filter[>DATE_CREATE]': '2025-12-31T23:59:59',
        'order[DATE_CREATE]': 'DESC',
        'start': start,
    }
    for f in select_fields:
        params['select[]'] = f  # nota: sobrescreve, mas Bitrix aceita lista
    # Manda como lista correta
    params_list = [('filter[>DATE_CREATE]', '2025-12-31T23:59:59'),
                   ('order[DATE_CREATE]', 'DESC'),
                   ('start', start)]
    for f in select_fields:
        params_list.append(('select[]', f))

    try:
        r = requests.get(WEBHOOK + 'crm.quote.list.json',
                         params=params_list, timeout=30)
        data = r.json()
        batch = data.get('result', [])
        if not batch: break
        all_quotes.extend(batch)
        total_api = data.get('total', len(all_quotes))
        start += 50
        print(f"  {len(all_quotes)}/{total_api} orcamentos")
        if len(all_quotes) >= total_api: break
    except Exception as e:
        print(f"Erro paginacao: {e}")
        break

print(f"Total: {len(all_quotes)} orcamentos")

# ── Debug: mostra distribuicao de STATUS_ID ──
status_dist = {}
for q in all_quotes[:100]:
    s = str(q.get('STATUS_ID','(vazio)'))
    status_dist[s] = status_dist.get(s, 0) + 1
print(f"Distribuicao STATUS_ID (primeiros 100): {status_dist}")

opp_sample = [q.get('OPPORTUNITY') for q in all_quotes[:5]]
print(f"OPPORTUNITY amostra: {opp_sample}")

# ── Processar ──
records = []
by_sup = {}
by_mes = {}

for q in all_quotes:
    sup_raw = q.get('UF_CRM_QUOTE_SUPERVISOR') or users.get(str(q.get('ASSIGNED_BY_ID','')), '')
    sup = norm_sup(sup_raw)
    if sup is None: continue

    bandeira = get_bandeira(q.get('TITLE',''), q.get('UF_CRM_QUOTE_BANDEIRA') or q.get('UF_CRM_BANDEIRA',''))
    status = get_status(q)
    valor = get_valor(q)

    date_str = q.get('DATE_CREATE','')
    try:
        dt = datetime.fromisoformat(date_str.replace('T',' ').split('+')[0])
        mes = dt.strftime('%Y-%m')
        mes_label = dt.strftime('%b/%y')
        envio = dt.strftime('%d/%m/%Y')
    except:
        mes = ''; mes_label = ''; envio = '-'

    orc = q.get('UF_CRM_QUOTE_ORCAMENTISTA') or ('Ana Beatriz Araújo' if bandeira=='ZAMP-BK' else 'Francyne Lima')
    prop = q.get('UF_CRM_QUOTE_NUMERO') or str(q.get('ID',''))
    loja = (q.get('TITLE') or '')[:50]

    records.append({
        'prop': prop, 'loja': loja, 'supervisor': sup, 'cliente': bandeira,
        'orc': orc, 'status': status, 'sla': '-', 'valor': round(valor, 2),
        'envio': envio, 'dia_envio': '', 'mes': mes, 'mes_label': mes_label,
        'tipo': 'PROGRAMADA', 'uf': '-'
    })

    if sup not in by_sup:
        by_sup[sup] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'enviado':0,'valor':0.0}
    by_sup[sup]['total'] += 1
    by_sup[sup]['valor'] += valor
    if status == 'APROVADO':    by_sup[sup]['aprovado']   += 1
    elif status == 'REPROVADO': by_sup[sup]['reprovado']  += 1
    elif status == 'ENVIADO':   by_sup[sup]['enviado']    += 1
    else:                       by_sup[sup]['aguardando'] += 1

    if mes:
        key = (mes, sup)
        if key not in by_mes:
            by_mes[key] = {'mes_str':mes,'Supervisor':sup,'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
        by_mes[key]['total'] += 1
        by_mes[key]['valor'] += valor
        if status == 'APROVADO':    by_mes[key]['aprovado']   += 1
        elif status == 'REPROVADO': by_mes[key]['reprovado']  += 1
        else:                       by_mes[key]['aguardando'] += 1

# ── Analise supervisores ──
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

# ── Stats gerais ──
total_r     = len(records)
aprovado_r  = sum(1 for r in records if r['status']=='APROVADO')
aguardando_r= sum(1 for r in records if r['status'] in ('AGUARDANDO','ENVIADO'))
reprovado_r = sum(1 for r in records if r['status']=='REPROVADO')
valor_total = sum(r['valor'] for r in records)

# Por mes
meses_stats = {}
for r in records:
    if not r['mes']: continue
    m = r['mes']
    if m not in meses_stats:
        meses_stats[m] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0}
    meses_stats[m]['total'] += 1
    meses_stats[m]['valor'] += r['valor']
    if r['status']=='APROVADO':    meses_stats[m]['aprovado']   += 1
    elif r['status']=='REPROVADO': meses_stats[m]['reprovado']  += 1
    else:                          meses_stats[m]['aguardando'] += 1

meses_ord = sorted(meses_stats.keys())
men_labels = [datetime.strptime(m,'%Y-%m').strftime('%b/%y') for m in meses_ord]
men_total  = [meses_stats[m]['total']    for m in meses_ord]
men_aprov  = [meses_stats[m]['aprovado'] for m in meses_ord]
men_aguar  = [meses_stats[m]['aguardando'] for m in meses_ord]
men_reprov = [meses_stats[m]['reprovado'] for m in meses_ord]
men_valor  = [round(meses_stats[m]['valor']/1000) for m in meses_ord]
men_taxa   = [round(meses_stats[m]['aprovado']/meses_stats[m]['total']*100,1) if meses_stats[m]['total'] else 0 for m in meses_ord]

by_band = {}
for r in records:
    b = r['cliente']
    if b not in by_band:
        by_band[b] = {'total':0,'aprovado':0,'valor':0}
    by_band[b]['total'] += 1
    by_band[b]['valor'] += r['valor']
    if r['status']=='APROVADO': by_band[b]['aprovado'] += 1

taxa_geral = round(aprovado_r/total_r*100,1) if total_r else 0
zamp  = by_band.get('ZAMP-BK', {})
botic = by_band.get('Boticário', {})
taxa_zamp  = round(zamp.get('aprovado',0)/zamp.get('total',1)*100,1)  if zamp.get('total')  else 0
taxa_botic = round(botic.get('aprovado',0)/botic.get('total',1)*100,1) if botic.get('total') else 0

hoje = datetime.now().strftime('%d/%m/%Y %H:%M')

payload = {
    'records': records,
    'sup_analysis': sup_analysis,
    'sup_mes_data': sup_mes_data,
    'men_labels': men_labels, 'men_total': men_total,
    'men_aprov': men_aprov, 'men_aguar': men_aguar,
    'men_reprov': men_reprov, 'men_valor': men_valor,
    'men_taxa': men_taxa, 'meses_ord': meses_ord,
    'kpis': {
        'total': total_r, 'aprovado': aprovado_r,
        'aguardando': aguardando_r, 'reprovado': reprovado_r,
        'valor': round(valor_total, 0), 'taxa_geral': taxa_geral,
        'taxa_zamp': taxa_zamp, 'taxa_botic': taxa_botic,
        'aprov_zamp': zamp.get('aprovado',0), 'total_zamp': zamp.get('total',0),
        'aprov_botic': botic.get('aprovado',0), 'total_botic': botic.get('total',0),
        'data_atualizacao': hoje,
    }
}

with open('data.json','w',encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False, default=str)

print(f"data.json gerado: {total_r} registros, {aprovado_r} aprovados, R$ {round(valor_total/1000)}k")
