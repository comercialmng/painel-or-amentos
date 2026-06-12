#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_data.py — Le data.json gerado pelo build_from_bitrix.py
e injeta os dados atualizados no HTML do painel.

MAPEAMENTO CORRETO (variáveis reais do HTML):
  records        → const PROP=[...]
  sup_analysis   → const SUP_DATA=[...]
  sup_mes_data   → const SUP_MES = []
  diário         → const dailyD, dailyQ, dailyBotic, dailyZamp, etc.
  orcamentistas  → const ORC_DETAIL, orcMesData, orcNames
  supervisores   → const supN, scV, txV
"""
import json, re
from datetime import datetime
from collections import defaultdict

# ── Arquivos ──
DATA_FILE = 'data.json'
HTML_FILE = 'painel_orcamentos_2026_49.html'

print("Lendo data.json...")
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    D = json.load(f)

kpis         = D['kpis']
records      = D['records']
sup_analysis = D['sup_analysis']
sup_mes_data = D['sup_mes_data']
men_labels   = D['men_labels']
men_total    = D['men_total']
men_aprov    = D['men_aprov']
men_aguar    = D['men_aguar']
men_reprov   = D['men_reprov']
men_valor    = D['men_valor']
men_taxa     = D['men_taxa']
meses_ord    = D['meses_ord']

hoje = kpis.get('data_atualizacao', datetime.now().strftime('%d/%m/%Y %H:%M'))
print(f"Dados: {kpis['total']} propostas | {kpis['aprovado']} aprovadas | Base: {hoje}")

# ════════════════════════════════════════════════════════
# Calcular dados diários a partir dos records
# ════════════════════════════════════════════════════════
BANDEIRAS_DAILY = {
    'Boticário':     'dailyBotic',
    'ZAMP-BK':       'dailyZamp',
    'Leroy Merlin':  'dailyLeroy',
    'Fundação':      'dailyFund',
    'Carrefour/Grupo': 'dailyCarr',
    'Sams':          'dailySams',
    'Obramax':       'dailyObr',
}

daily_map = defaultdict(lambda: defaultdict(int))
for r in records:
    if not r.get('envio') or r['envio'] == '-':
        continue
    try:
        dt = datetime.strptime(r['envio'], '%d/%m/%Y')
        dia = dt.strftime('%d/%m')
    except:
        continue
    daily_map[dia]['total'] += 1
    band = r.get('cliente', '')
    for b, var in BANDEIRAS_DAILY.items():
        if band == b:
            daily_map[dia][var] += 1

# Ordena datas
def sort_key(d):
    try:
        return datetime.strptime(d + '/2026', '%d/%m/%Y')
    except:
        return datetime.max

dias_sorted = sorted(daily_map.keys(), key=sort_key)
# Mantém apenas últimos 45 dias úteis no máximo
dias_sorted = dias_sorted[-45:]

dailyD    = dias_sorted
dailyQ    = [daily_map[d]['total']    for d in dias_sorted]
dailyBotic = [daily_map[d]['dailyBotic'] for d in dias_sorted]
dailyZamp  = [daily_map[d]['dailyZamp']  for d in dias_sorted]
dailyLeroy = [daily_map[d]['dailyLeroy'] for d in dias_sorted]
dailyFund  = [daily_map[d]['dailyFund']  for d in dias_sorted]
dailyCarr  = [daily_map[d]['dailyCarr']  for d in dias_sorted]
dailySams  = [daily_map[d]['dailySams']  for d in dias_sorted]
dailyObr   = [daily_map[d]['dailyObr']   for d in dias_sorted]

# ════════════════════════════════════════════════════════
# Calcular ORC_DETAIL, orcMesData, orcNames
# ════════════════════════════════════════════════════════
orc_map = defaultdict(lambda: {
    'total': 0, 'aprovado': 0, 'aguardando': 0, 'reprovado': 0,
    'valor': 0.0, 'sla_c': 0, 'sla_n': 0, 'by_month': defaultdict(lambda: {
        'total': 0, 'aprovado': 0, 'aguardando': 0, 'reprovado': 0,
        'sla_c': 0, 'sla_n': 0, 'valor': 0.0
    })
})

for r in records:
    o = r.get('orc') or 'Francyne Lima'
    mes = r.get('mes', '')
    status = r.get('status', '')
    valor = float(r.get('valor') or 0)
    sla = str(r.get('sla', '-'))

    orc_map[o]['total'] += 1
    orc_map[o]['valor'] += valor

    if status == 'APROVADO':    orc_map[o]['aprovado']   += 1
    elif status == 'REPROVADO': orc_map[o]['reprovado']  += 1
    else:                       orc_map[o]['aguardando'] += 1

    if sla == 'OK':   orc_map[o]['sla_c'] += 1
    elif sla != '-':  orc_map[o]['sla_n'] += 1

    if mes:
        orc_map[o]['by_month'][mes]['total'] += 1
        orc_map[o]['by_month'][mes]['valor'] += valor
        if status == 'APROVADO':    orc_map[o]['by_month'][mes]['aprovado']   += 1
        elif status == 'REPROVADO': orc_map[o]['by_month'][mes]['reprovado']  += 1
        else:                       orc_map[o]['by_month'][mes]['aguardando'] += 1
        if sla == 'OK':  orc_map[o]['by_month'][mes]['sla_c'] += 1
        elif sla != '-': orc_map[o]['by_month'][mes]['sla_n'] += 1

# Monta ORC_DETAIL
orc_detail = {}
for nome, d in sorted(orc_map.items(), key=lambda x: -x[1]['total']):
    pct_aprov = round(d['aprovado'] / d['total'] * 100, 1) if d['total'] else 0
    sla_total = d['sla_c'] + d['sla_n']
    pct_sla   = round(d['sla_c'] / sla_total * 100, 1) if sla_total else 0
    by_month  = []
    for mes_str in sorted(d['by_month'].keys()):
        m = d['by_month'][mes_str]
        by_month.append({
            'mes_str': mes_str,
            'total': m['total'], 'aprovado': m['aprovado'],
            'aguardando': m['aguardando'], 'reprovado': m['reprovado'],
            'sla_c': m['sla_c'], 'sla_n': m['sla_n'],
            'valor': round(m['valor'], 2)
        })
    orc_detail[nome] = {
        'total': d['total'], 'aprovado': d['aprovado'],
        'aguardando': d['aguardando'], 'reprovado': d['reprovado'],
        'pct_aprov': pct_aprov, 'valor': round(d['valor'], 2),
        'sla_c': d['sla_c'], 'sla_n': d['sla_n'],
        'pct_sla': pct_sla, 'by_month': by_month
    }

# orcNames: nomes ordenados por total
orc_names = [nome for nome, _ in sorted(orc_map.items(), key=lambda x: -x[1]['total'])]

# orcMesData: {nome: [qtd por mes]}
orc_mes_data = {}
for nome in orc_names:
    orc_mes_data[nome] = [
        orc_map[nome]['by_month'].get(m, {}).get('total', 0)
        for m in meses_ord
    ]

# ════════════════════════════════════════════════════════
# Calcular supN, scV, txV
# ════════════════════════════════════════════════════════
sup_names  = [s['Supervisor'] for s in sup_analysis]
sc_values  = [s.get('score', s['total'] - s['aprovado']) for s in sup_analysis[:12]]
tx_values  = [s['taxa_aprov'] for s in sup_analysis]

# ════════════════════════════════════════════════════════
# SUP_MES — lista de objetos por supervisor/mes
# ════════════════════════════════════════════════════════
sup_mes_list = []
for item in sup_mes_data:
    sup_mes_list.append({
        'mes_str':   item.get('mes_str', ''),
        'Supervisor': item.get('Supervisor', ''),
        'total':     item.get('total', 0),
        'aprovado':  item.get('aprovado', 0),
        'aguardando': item.get('aguardando', 0),
        'reprovado': item.get('reprovado', 0),
        'valor':     item.get('valor', 0)
    })

# ════════════════════════════════════════════════════════
# Lê HTML
# ════════════════════════════════════════════════════════
print("Lendo HTML...")
with open(HTML_FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# Helper
def js(v):
    return json.dumps(v, ensure_ascii=False)

def replace_js_var(html, varname, new_value, is_object=False):
    """Substitui const VARNAME = [...] ou const VARNAME = {...}"""
    if is_object:
        pattern = r'(const\s+' + re.escape(varname) + r'\s*=\s*)\{.*?\}(?=\s*;)'
    else:
        pattern = r'(const\s+' + re.escape(varname) + r'\s*=\s*)\[.*?\](?=\s*;)'
    replacement = r'\g<1>' + js(new_value)
    new_html, n = re.subn(pattern, replacement, html, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  Variável '{varname}' não encontrada no HTML")
    else:
        print(f"  ✅ {varname} atualizado")
    return new_html

# ════════════════════════════════════════════════════════
# Substitui variáveis no HTML com nomes corretos
# ════════════════════════════════════════════════════════
print("Injetando dados...")

# Arrays de propostas (principal)
html = replace_js_var(html, 'PROP', records)

# Supervisores
html = replace_js_var(html, 'SUP_DATA', sup_analysis)
html = replace_js_var(html, 'SUP_MES', sup_mes_list)
html = replace_js_var(html, 'supN', sup_names)
html = replace_js_var(html, 'scV', sc_values)
html = replace_js_var(html, 'txV', tx_values)

# Orçamentistas
html = replace_js_var(html, 'ORC_DETAIL', orc_detail, is_object=True)
html = replace_js_var(html, 'orcMesData', orc_mes_data, is_object=True)
html = replace_js_var(html, 'orcNames', orc_names)

# Diário
html = replace_js_var(html, 'dailyD', dailyD)
html = replace_js_var(html, 'dailyQ', dailyQ)
html = replace_js_var(html, 'dailyBotic', dailyBotic)
html = replace_js_var(html, 'dailyZamp', dailyZamp)
html = replace_js_var(html, 'dailyLeroy', dailyLeroy)
html = replace_js_var(html, 'dailyFund', dailyFund)
html = replace_js_var(html, 'dailyCarr', dailyCarr)
html = replace_js_var(html, 'dailySams', dailySams)
html = replace_js_var(html, 'dailyObr', dailyObr)

# Data de base no cabeçalho
html = re.sub(
    r'(Base:\s*)[\d/]+ [\d:]+',
    r'\g<1>' + hoje,
    html
)
html = re.sub(
    r'(Base:\s*)[\d/]+(?!\s*\d{2}:)',
    r'\g<1>' + hoje,
    html
)

# ════════════════════════════════════════════════════════
# Salva
# ════════════════════════════════════════════════════════
with open(HTML_FILE, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = len(html.encode('utf-8')) // 1024
print(f"\n✅ HTML atualizado: {HTML_FILE} ({size_kb} KB)")
print(f"   Total: {kpis['total']} | Aprovadas: {kpis['aprovado']} | Taxa: {kpis['taxa_geral']}% | Base: {hoje}")
