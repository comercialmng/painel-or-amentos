#!/usr/bin/env python3
"""
Script executado pelo GitHub Actions 2x por dia.
Busca dados do Bitrix24 (crm.quote), processa e gera o HTML atualizado.
"""
import os, json, re, requests, sys
from datetime import datetime

WEBHOOK = os.environ.get('BITRIX_WEBHOOK', '')
if not WEBHOOK:
    print("ERRO: BITRIX_WEBHOOK não definido")
    sys.exit(1)

# ══ REGRAS DE SUPERVISORES ══
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
    if 'FUNDAÇÃO' in c: return 'Fundação'
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
    if any(x in s for x in ['APPROVED','WON','ACEITO','APROV']): return 'APROVADO'
    if any(x in s for x in ['DECLINED','LOSE','RECUS','REPROV','NAO APROV','NÃO APROV']): return 'REPROVADO'
    return 'AGUARDANDO'

# ══ BUSCAR USUÁRIOS ══
print("Buscando usuários...")
users = {}
try:
    r = requests.get(WEBHOOK + 'user.get.json', params={'FILTER[ACTIVE]': 'Y'}, timeout=30)
    for u in r.json().get('result', []):
        users[str(u['ID'])] = (u.get('NAME','') + ' ' + u.get('LAST_NAME','')).strip()
except Exception as e:
    print(f"Aviso: erro ao buscar usuários: {e}")

# ══ BUSCAR ORÇAMENTOS ══
print("Buscando orçamentos do Bitrix...")
all_quotes = []
start = 0
total = 9999
while len(all_quotes) < total:
    params = {
        'filter[>DATE_CREATE]': '2026-01-01',
        'order[DATE_CREATE]': 'DESC',
        'start': start,
    }
    for f in ['ID','TITLE','STATUS_ID','OPPORTUNITY','DATE_CREATE','ASSIGNED_BY_ID',
              'UF_CRM_QUOTE_SUPERVISOR','UF_CRM_QUOTE_NUMERO','UF_CRM_QUOTE_BANDEIRA',
              'UF_CRM_QUOTE_ORCAMENTISTA','UF_CRM_QUOTE_DATA_ENVIO']:
        params[f'select[]'] = f
    try:
        r = requests.get(WEBHOOK + 'crm.quote.list.json', params=params, timeout=30)
        data = r.json()
        batch = data.get('result', [])
        if not batch: break
        all_quotes.extend(batch)
        total = data.get('total', len(all_quotes))
        start += 50
        print(f"  {len(all_quotes)}/{total} orçamentos")
        if len(all_quotes) >= total: break
    except Exception as e:
        print(f"Erro: {e}")
        break

print(f"Total: {len(all_quotes)} orçamentos")

# ══ PROCESSAR ══
records = []
by_sup = {}
by_mes = {}

for q in all_quotes:
    sup_raw = q.get('UF_CRM_QUOTE_SUPERVISOR') or users.get(str(q.get('ASSIGNED_BY_ID','')), '')
    sup = norm_sup(sup_raw)
    if sup is None: continue  # orçamentista, pula
    
    bandeira = get_bandeira(q.get('TITLE',''), q.get('UF_CRM_QUOTE_BANDEIRA',''))
    status = get_status(q.get('STATUS_ID',''))
    valor = float(q.get('OPPORTUNITY') or 0)
    
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
    
    # Acumular por supervisor
    if sup not in by_sup:
        by_sup[sup] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
    by_sup[sup]['total'] += 1
    by_sup[sup]['valor'] += valor
    if status == 'APROVADO': by_sup[sup]['aprovado'] += 1
    elif status == 'REPROVADO': by_sup[sup]['reprovado'] += 1
    else: by_sup[sup]['aguardando'] += 1
    
    # Por mês
    if mes:
        key = (mes, sup)
        if key not in by_mes:
            by_mes[key] = {'mes_str':mes,'Supervisor':sup,'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
        by_mes[key]['total'] += 1
        by_mes[key]['valor'] += valor
        if status == 'APROVADO': by_mes[key]['aprovado'] += 1
        elif status == 'REPROVADO': by_mes[key]['reprovado'] += 1
        else: by_mes[key]['aguardando'] += 1

# ══ ANÁLISE SUPERVISORES ══
sup_analysis = []
for sup, d in sorted(by_sup.items(), key=lambda x: -x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100, 1) if d['total'] else 0
    score = d['total'] - d['aprovado']
    sup_analysis.append({
        'Supervisor': sup, 'total': d['total'], 'aprovado': d['aprovado'],
        'aguardando': d['aguardando'], 'reprovado': d['reprovado'],
        'taxa_aprov': taxa, 'score': score, 'valor': round(d['valor'], 0)
    })

sup_mes_data = sorted(by_mes.values(), key=lambda x: (x['mes_str'], x['Supervisor']))

# ══ ESTATÍSTICAS GERAIS ══
total_r = len(records)
aprovado_r = sum(1 for r in records if r['status']=='APROVADO')
aguardando_r = sum(1 for r in records if r['status']=='AGUARDANDO')
reprovado_r = sum(1 for r in records if r['status']=='REPROVADO')
valor_total = sum(r['valor'] for r in records)

# Por mês geral
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
men_labels = [datetime.strptime(m, '%Y-%m').strftime('%b/%y') for m in meses_ord]
men_total  = [meses_stats[m]['total'] for m in meses_ord]
men_aprov  = [meses_stats[m]['aprovado'] for m in meses_ord]
men_aguar  = [meses_stats[m]['aguardando'] for m in meses_ord]
men_reprov = [meses_stats[m]['reprovado'] for m in meses_ord]
men_valor  = [round(meses_stats[m]['valor']/1000) for m in meses_ord]
men_taxa   = [round(meses_stats[m]['aprovado']/meses_stats[m]['total']*100,1) if meses_stats[m]['total'] else 0 for m in meses_ord]

# Por bandeira
by_band = {}
for r in records:
    b = r['cliente']
    if b not in by_band:
        by_band[b] = {'total':0,'aprovado':0,'valor':0}
    by_band[b]['total'] += 1
    by_band[b]['valor'] += r['valor']
    if r['status']=='APROVADO': by_band[b]['aprovado'] += 1

taxa_geral = round(aprovado_r/total_r*100,1) if total_r else 0
zamp = by_band.get('ZAMP-BK', {})
botic = by_band.get('Boticário', {})
taxa_zamp = round(zamp.get('aprovado',0)/zamp.get('total',1)*100,1) if zamp.get('total') else 0
taxa_botic = round(botic.get('aprovado',0)/botic.get('total',1)*100,1) if botic.get('total') else 0

hoje = datetime.now().strftime('%d/%m/%Y %H:%M')

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
        'data_atualizacao': hoje,
    }
}

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False, default=str)

print(f"✅ data.json gerado: {total_r} registros, {aprovado_r} aprovados, R$ {round(valor_total/1000)}k")
