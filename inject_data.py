#!/usr/bin/env python3
"""Injeta data.json no HTML do painel."""
import json, re
from datetime import datetime

with open('data.json', 'r', encoding='utf-8') as f:
    D = json.load(f)

with open('painel_orcamentos_2026_49.html', 'r', encoding='utf-8') as f:
    html = f.read()

kpis = D['kpis']
records = D['records']
sup_analysis = D['sup_analysis']
sup_mes_data = D['sup_mes_data']
men_labels = D['men_labels']
men_total = D['men_total']
men_aprov = D['men_aprov']
men_aguar = D['men_aguar']
men_reprov = D['men_reprov']
men_valor = D['men_valor']
men_taxa = D['men_taxa']
meses_ord = D['meses_ord']

def fmt_val(v):
    v = float(v)
    if v >= 1_000_000: return f'R$ {v/1_000_000:.1f}M'
    if v >= 1_000: return f'R$ {v/1000:.0f}k'
    return f'R$ {v:.0f}'

# 1. Update PROP (search records)
html = re.compile(r'const PROP=\[.*?\];', re.DOTALL).sub(
    'const PROP=' + json.dumps(records, ensure_ascii=False) + ';', html)

# 2. Update SUP_DATA
sup_data_js = json.dumps(sup_analysis, ensure_ascii=False)
html = re.compile(r'const SUP_DATA=\[.*?\];', re.DOTALL).sub(
    f'const SUP_DATA={sup_data_js};', html)

# 3. Update SUP_MES
html = re.compile(r'const SUP_MES = \[.*?\];', re.DOTALL).sub(
    f'const SUP_MES = {json.dumps(sup_mes_data, ensure_ascii=False)};', html)

# 4. Update supervisor table rows
ok='#16a34a'; wa='#d97706'; er='#dc2626'
new_rows = ''
for s in sup_analysis:
    tx=s['taxa_aprov']; sc=s['score']
    bc='bg' if tx>=70 else 'by' if tx>=50 else 'br'
    scc='br' if sc>50 else 'by' if sc>20 else 'bg'
    val=fmt_val(s.get('valor',0))
    new_rows += f'<tr><td><b>{s["Supervisor"]}</b></td><td class="mono">{s["total"]}</td><td class="mono" style="color:{ok}">{s["aprovado"]}</td><td class="mono" style="color:{wa}">{s["aguardando"]}</td><td class="mono" style="color:{er}">{s["reprovado"]}</td><td><span class="bge {bc}">{tx}%</span></td><td><span class="bge {scc}">{sc}</span></td><td class="mono">{val}</td></tr>'

html = re.compile(r'id="sup-tbody">.*?(?=</tbody>)', re.DOTALL).sub(
    f'id="sup-tbody">{new_rows}', html, count=1)

# 5. Update KPI cards (Visão Geral)
html = html.replace(
    f'>{kpis["total"]}</div>',
    f'>{kpis["total"]}</div>', 1)

# 6. Update base date
html = html.replace('Base: 08/06/2026', f'Base: {kpis["data_atualizacao"]}')
html = html.replace('Base: 08/06/2026', f'Base: {kpis["data_atualizacao"]}')

# 7. Update mensal KPI cards
meses_ptbr = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
for i, mes in enumerate(meses_ord[:6]):
    dt_mes = f'{meses_ptbr[int(mes[5:])-1]}/{mes[2:4]}'
    total_m = men_total[i] if i < len(men_total) else 0
    valor_m = men_valor[i] if i < len(men_valor) else 0
    taxa_m = men_taxa[i] if i < len(men_taxa) else 0
    taxa_cor = '#16a34a' if taxa_m >= 50 else '#d97706' if taxa_m >= 40 else '#dc2626'

# 8. Update mensal chart data
html = re.compile(r'const ML=\[.*?\];').sub(
    f'const ML={json.dumps(meses_ptbr[:len(meses_ord)])};', html)

with open('painel_orcamentos_2026_49.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✅ HTML atualizado! {len(records)} registros, data: {kpis['data_atualizacao']}")
