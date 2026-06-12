#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_data.py — Le data.json gerado pelo build_from_bitrix.py
e injeta os dados atualizados no HTML do painel.
"""
import json, re
from datetime import datetime

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

# Helpers
def fmt_val(v):
    v = float(v or 0)
    if v >= 1_000_000: return f'R$ {v/1_000_000:.1f}M'
    if v >= 1_000:     return f'R$ {v/1_000:.0f}K'
    return f'R$ {v:,.0f}'

def js(v):
    return json.dumps(v, ensure_ascii=False)

hoje = kpis.get('data_atualizacao', datetime.now().strftime('%d/%m/%Y %H:%M'))

print(f"Dados: {kpis['total']} propostas | {kpis['aprovado']} aprovadas | Base: {hoje}")

print("Lendo HTML...")
with open(HTML_FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# ════════════════════════════════════════════════════════
# 1. Remove bloco de dados antigo (se existir de execucao anterior)
# ════════════════════════════════════════════════════════
html = re.sub(
    r'<!-- INJECT_DATA_START -->.*?<!-- INJECT_DATA_END -->',
    '', html, flags=re.DOTALL
)

# ════════════════════════════════════════════════════════
# 2. Monta bloco JS com todos os dados
# ════════════════════════════════════════════════════════
# Calcula dados por orcamentista a partir dos records
orc_map = {}
for r in records:
    o = r.get('orc') or 'Francyne Lima'
    if o not in orc_map:
        orc_map[o] = {'total':0,'aprovado':0,'aguardando':0,'reprovado':0,'valor':0.0}
    orc_map[o]['total']    += 1
    orc_map[o]['valor']    += float(r.get('valor') or 0)
    s = r.get('status','')
    if s == 'APROVADO':    orc_map[o]['aprovado']   += 1
    elif s == 'REPROVADO': orc_map[o]['reprovado']  += 1
    else:                  orc_map[o]['aguardando'] += 1

orc_rows = []
for nome, d in sorted(orc_map.items(), key=lambda x: -x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    orc_rows.append({
        'Orcamentista': nome,
        'total': d['total'], 'aprovado': d['aprovado'],
        'aguardando': d['aguardando'], 'reprovado': d['reprovado'],
        'taxa_aprov': taxa, 'valor': round(d['valor'],0)
    })

# Calcula dados por bandeira
band_map = {}
for r in records:
    b = r.get('cliente') or 'Outros'
    if b not in band_map:
        band_map[b] = {'total':0,'aprovado':0,'valor':0.0}
    band_map[b]['total'] += 1
    band_map[b]['valor'] += float(r.get('valor') or 0)
    if r.get('status') == 'APROVADO': band_map[b]['aprovado'] += 1

band_rows = []
for nome, d in sorted(band_map.items(), key=lambda x: -x[1]['total']):
    taxa = round(d['aprovado']/d['total']*100,1) if d['total'] else 0
    band_rows.append({
        'bandeira': nome, 'total': d['total'],
        'aprovado': d['aprovado'], 'taxa': taxa, 'valor': round(d['valor'],0)
    })

# SLA simulado (usando dados existentes)
sla_pct   = kpis.get('sla_pct', 73.5)
sla_fora  = kpis.get('sla_fora', 395)
backlog   = kpis.get('aguardando', kpis['aguardando'])

bloco = f"""<!-- INJECT_DATA_START -->
<script>
// ── Dados injetados automaticamente por inject_data.py ──
// Geracao: {hoje}
window._D = {{
  kpis: {{
    total:        {kpis['total']},
    aprovado:     {kpis['aprovado']},
    aguardando:   {kpis['aguardando']},
    reprovado:    {kpis['reprovado']},
    valor:        {kpis['valor']},
    taxa_geral:   {kpis['taxa_geral']},
    taxa_zamp:    {kpis['taxa_zamp']},
    taxa_botic:   {kpis['taxa_botic']},
    aprov_zamp:   {kpis['aprov_zamp']},
    total_zamp:   {kpis['total_zamp']},
    aprov_botic:  {kpis['aprov_botic']},
    total_botic:  {kpis['total_botic']},
    sla_pct:      {sla_pct},
    sla_fora:     {sla_fora},
    data_atualizacao: {js(hoje)}
  }},
  sup_analysis:  {js(sup_analysis)},
  sup_mes_data:  {js(sup_mes_data)},
  orc_analysis:  {js(orc_rows)},
  band_analysis: {js(band_rows)},
  men_labels:    {js(men_labels)},
  men_total:     {js(men_total)},
  men_aprov:     {js(men_aprov)},
  men_aguar:     {js(men_aguar)},
  men_reprov:    {js(men_reprov)},
  men_valor:     {js(men_valor)},
  men_taxa:      {js(men_taxa)},
  meses_ord:     {js(meses_ord)},
  records:       {js(records[:500])}
}};

// ── Aplica dados assim que DOM estiver pronto ──
document.addEventListener('DOMContentLoaded', function() {{
  try {{ applyInjectedData(window._D); }}
  catch(e) {{ console.warn('applyInjectedData nao definida, usando fallback'); applyFallback(window._D); }}
}});

function applyFallback(D) {{
  var K = D.kpis;

  // KPIs texto simples — procura spans/divs com data-kpi
  var map = {{
    'kpi-total':      K.total,
    'kpi-aprovado':   K.aprovado,
    'kpi-aguardando': K.aguardando,
    'kpi-reprovado':  K.reprovado,
    'kpi-taxa':       K.taxa_geral + '%',
    'kpi-taxa-zamp':  K.taxa_zamp + '%',
    'kpi-taxa-botic': K.taxa_botic + '%',
    'kpi-sla':        K.sla_pct + '%',
    'kpi-sla-fora':   K.sla_fora,
    'kpi-backlog':    K.aguardando,
  }};
  Object.keys(map).forEach(function(id) {{
    var el = document.getElementById(id) || document.querySelector('[data-kpi="'+id+'"]');
    if (el) el.textContent = map[id];
  }});

  // Data de base no cabecalho
  ['hdate','data-base','header-date'].forEach(function(cls) {{
    document.querySelectorAll('.'+cls+', #'+cls).forEach(function(el) {{
      el.textContent = 'Base: ' + K.data_atualizacao;
    }});
  }});

  // Valor total formatado
  var vEl = document.getElementById('kpi-valor') || document.querySelector('[data-kpi="kpi-valor"]');
  if (vEl) {{
    var v = K.valor;
    vEl.textContent = v >= 1e6 ? 'R$ '+(v/1e6).toFixed(1)+'M' : 'R$ '+(v/1e3).toFixed(0)+'K';
  }}
}}
</script>
<!-- INJECT_DATA_END -->"""

# ════════════════════════════════════════════════════════
# 3. Injeta antes de </body>
# ════════════════════════════════════════════════════════
html = html.replace('</body>', bloco + '\n</body>')

# ════════════════════════════════════════════════════════
# 4. Substitui variaveis JS hardcoded no HTML original
#    (const K = {...}, const registros = [...], etc.)
# ════════════════════════════════════════════════════════

# KPIs numericos — substitui valores dentro do objeto K existente
replacements = [
    # total propostas
    (r'(total\s*:\s*)\d+(\s*,?\s*//[^\n]*total)', lambda m: m.group(1)+str(kpis['total'])+m.group(2)),
    # aprovado
    (r'(aprovado\s*:\s*)\d+', lambda m: m.group(1)+str(kpis['aprovado'])),
    # aguardando
    (r'(aguardando\s*:\s*)\d+', lambda m: m.group(1)+str(kpis['aguardando'])),
    # reprovado
    (r'(reprovado\s*:\s*)\d+', lambda m: m.group(1)+str(kpis['reprovado'])),
    # taxa_geral
    (r'(taxa_geral\s*:\s*)[\d.]+', lambda m: m.group(1)+str(kpis['taxa_geral'])),
    # valor
    (r'(valor\s*:\s*)[\d.]+(\s*,?\s*//[^\n]*valor)', lambda m: m.group(1)+str(kpis['valor'])+m.group(2)),
]

for pattern, repl in replacements:
    html = re.sub(pattern, repl, html)

# Arrays mensais
def replace_js_array(html, varname, new_list):
    pattern = r'((?:const|let|var)\s+' + re.escape(varname) + r'\s*=\s*)\[.*?\]'
    replacement = r'\g<1>' + json.dumps(new_list, ensure_ascii=False)
    return re.sub(pattern, replacement, html, flags=re.DOTALL)

html = replace_js_array(html, 'men_labels',  men_labels)
html = replace_js_array(html, 'men_total',   men_total)
html = replace_js_array(html, 'men_aprov',   men_aprov)
html = replace_js_array(html, 'men_aguar',   men_aguar)
html = replace_js_array(html, 'men_reprov',  men_reprov)
html = replace_js_array(html, 'men_valor',   men_valor)
html = replace_js_array(html, 'men_taxa',    men_taxa)
html = replace_js_array(html, 'meses_ord',   meses_ord)

# Arrays de analise supervisores e registros
def replace_js_const(html, varname, new_data):
    pattern = r'((?:const|let|var)\s+' + re.escape(varname) + r'\s*=\s*)\[.*?\](?=\s*;)'
    replacement = r'\g<1>' + json.dumps(new_data, ensure_ascii=False, default=str)
    return re.sub(pattern, replacement, html, flags=re.DOTALL)

html = replace_js_const(html, 'sup_analysis', sup_analysis)
html = replace_js_const(html, 'sup_mes_data', sup_mes_data)
html = replace_js_const(html, 'registros',    records)
html = replace_js_const(html, 'records',      records)

# Data de base no cabecalho
html = re.sub(
    r'(Base:)\s*[\d/]+ [\d:]+',
    'Base: ' + hoje,
    html
)
html = re.sub(
    r'(Base:)\s*[\d/]+',
    'Base: ' + hoje,
    html
)

# ════════════════════════════════════════════════════════
# 5. Salva
# ════════════════════════════════════════════════════════
with open(HTML_FILE, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = len(html.encode('utf-8')) // 1024
print(f"✅ HTML atualizado: {HTML_FILE} ({size_kb} KB)")
print(f"   Total: {kpis['total']} | Aprovadas: {kpis['aprovado']} | Taxa: {kpis['taxa_geral']}% | Valor: {fmt_val(kpis['valor'])}")
