#!/usr/bin/env python3
"""
Injeta data.json no HTML do painel.
v3.0 - Correcoes:
  BUG3: regex dinamico (nao mais hardcoded com valores fixos)
  FIX:  substituicao via lambda (sem backreference quebrada em f-string)
"""
import json, re
from datetime import datetime

with open('data.json', 'r', encoding='utf-8') as f:
    D = json.load(f)

with open('painel_orcamentos_2026_49.html', 'r', encoding='utf-8') as f:
    html = f.read()

kpis       = D['kpis']
records    = D['records']
sup_an     = D['sup_analysis']
sup_mes    = D['sup_mes_data']
men_total  = D['men_total']
men_valor  = D['men_valor']
men_taxa   = D['men_taxa']
men_aprov  = D['men_aprov']
men_aguar  = D['men_aguar']
men_reprov = D['men_reprov']
meses_ord  = D['meses_ord']

ok = '#16a34a'; wa = '#d97706'; er = '#dc2626'
MESES_PT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

def fmt_val(v):
    v = float(v or 0)
    if v >= 1_000_000: return 'R$ {:.1f}M'.format(v / 1_000_000)
    if v >= 1_000: return 'R$ {}k'.format(int(round(v / 1000)))
    return 'R$ {}'.format(int(round(v)))

# ── 1. PROP ──
html = re.compile(r'const PROP=\[.*?\];', re.DOTALL).sub(
    'const PROP=' + json.dumps(records, ensure_ascii=False) + ';', html)
print('PROP: {} registros'.format(len(records)))

# ── 2. SUP_DATA ──
html = re.compile(r'const SUP_DATA=\[.*?\];', re.DOTALL).sub(
    'const SUP_DATA=' + json.dumps(sup_an, ensure_ascii=False) + ';', html)

# ── 3. SUP_MES ──
html = re.compile(r'const SUP_MES = \[.*?\];', re.DOTALL).sub(
    'const SUP_MES = ' + json.dumps(sup_mes, ensure_ascii=False) + ';', html)
print('SUP_DATA e SUP_MES: {} supervisores'.format(len(sup_an)))

# ── 4. Tabela supervisores ──
new_rows = ''
for s in sup_an:
    tx = s['taxa_aprov']; sc = s['score']
    bc = 'bg' if tx >= 70 else 'by' if tx >= 50 else 'br'
    scc = 'br' if sc > 50 else 'by' if sc > 20 else 'bg'
    new_rows += (
        '<tr>'
        '<td><b>{}</b></td>'
        '<td class="mono">{}</td>'
        '<td class="mono" style="color:{}">{}</td>'
        '<td class="mono" style="color:{}">{}</td>'
        '<td class="mono" style="color:{}">{}</td>'
        '<td><span class="bge {}">{}</span></td>'
        '<td><span class="bge {}">{}</span></td>'
        '<td class="mono">{}</td>'
        '</tr>'
    ).format(
        s['Supervisor'], s['total'],
        ok, s['aprovado'],
        wa, s['aguardando'],
        er, s['reprovado'],
        bc, str(tx) + '%',
        scc, sc,
        fmt_val(s.get('valor', 0))
    )
html = re.compile(r'id="sup-tbody">.*?(?=</tbody>)', re.DOTALL).sub(
    'id="sup-tbody">' + new_rows, html, count=1)
print('Tabela supervisores: {} linhas'.format(len(sup_an)))

# ── 5. Data base ──
html = re.sub(
    r'Base: [\d/]+(?: \d{2}:\d{2})?',
    'Base: ' + kpis['data_atualizacao'],
    html
)

# ── 6. KPIs Visao Geral ──
total     = kpis['total']
aprovado  = kpis['aprovado']
aguardando = kpis['aguardando']
reprovado = kpis['reprovado']

html = re.sub(r'(?<=>)2\.325(?=<)', str(total), html)
html = re.sub(r'(?<="kv">)955(?=<)', str(aprovado), html)
html = re.sub(r'(?<="kv">)1\.088(?=<)', str(aguardando), html)
html = re.sub(r'(?<="kv">)185(?=<)', str(reprovado), html)
html = re.sub(r'41\.1% conversao', str(kpis['taxa_geral']) + '% conversao', html)
html = re.sub(r'41\.1% convers\xE3o', str(kpis['taxa_geral']) + '% convers\xE3o', html)
html = re.sub(r'43\.1%', str(kpis['taxa_zamp']) + '%', html, count=1)
html = re.sub(r'71\.2%', str(kpis['taxa_botic']) + '%', html, count=1)
print('KPIs visao geral atualizados')

# ── 7. Cards KPI mensais ──
# FIX: usa funcao lambda em vez de string com backreference
# Isso evita o erro "invalid group reference" causado por \g<1>{valor} em f-string

sla_vals = [79.1, 65.1, 82.0, 57.0, 71.6, 97.8]  # SLA da planilha Excel (fixo)

for i in range(min(6, len(meses_ord))):
    mes      = meses_ord[i]
    mes_label = MESES_PT[int(mes[5:]) - 1] + '/' + mes[2:4]
    total_m  = men_total[i] if i < len(men_total) else 0
    valor_m  = men_valor[i] if i < len(men_valor) else 0
    taxa_m   = men_taxa[i]  if i < len(men_taxa)  else 0
    sla_m    = sla_vals[i]  if i < len(sla_vals)  else 0
    taxa_cor = ok if taxa_m >= 50 else wa if taxa_m >= 40 else er

    pat = re.compile(
        r'(<div class="kt">' + re.escape(mes_label) + r'</div>'
        r'<div class="kv">)'
        r'\d+</div>'
        r'<div class="ks">R\$ \d+k \xB7 SLA [\d.]+%</div>'
        r'<div[^>]*>Aprova[^<]*</div></div>'
    )

    # FIX: funcao que recebe o match e monta a string sem backreference
    def make_replacer(pfx_total, vm, sm, tm, tc):
        def replacer(m):
            prefix = m.group(1)
            return (
                prefix +
                str(pfx_total) + '</div>'
                '<div class="ks">R$ ' + str(vm) + 'k \xB7 SLA ' + str(sm) + '%</div>'
                '<div style="font-size:11px;font-weight:600;color:' + tc + ';'
                'margin-top:4px;padding-top:4px;border-top:1px solid var(--bd)">'
                'Aprova\xe7\xe3o: ' + str(tm) + '%</div></div>'
            )
        return replacer

    html = pat.sub(make_replacer(total_m, valor_m, sla_m, taxa_m, taxa_cor), html, count=1)

print('Cards mensais atualizados: {}'.format(meses_ord[:6]))

# ── 8. Graficos mensais — BUG3 FIX: regex dinamico ──
def update_chart_data(html, chart_id, new_data, dataset_index=0):
    """
    Encontra chart por ID e substitui o dataset na posicao especificada.
    Regex dinamico sem valores hardcoded.
    """
    idx = html.find("new Chart('" + chart_id + "'")
    if idx < 0:
        print('  AVISO: chart {} nao encontrado'.format(chart_id))
        return html

    # Encontra o fim do bloco do chart
    end_idx = idx
    depth = 0
    for j, ch in enumerate(html[idx:], idx):
        if ch == '(': depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                end_idx = j + 1
                break

    chunk = html[idx:end_idx]
    data_pattern = re.compile(r'data:\[[\d.,\s-]+\]')
    matches = list(data_pattern.finditer(chunk))

    if dataset_index >= len(matches):
        print('  AVISO: chart {} nao tem dataset {}'.format(chart_id, dataset_index))
        return html

    m = matches[dataset_index]
    new_chunk = chunk[:m.start()] + 'data:' + json.dumps(new_data) + chunk[m.end():]
    return html[:idx] + new_chunk + html[end_idx:]

html = update_chart_data(html, 'cVolMes',    men_total[:6], 0)
html = update_chart_data(html, 'cValorMes',  men_valor[:6], 0)
html = update_chart_data(html, 'cTaxaMensal', men_taxa[:6], 0)
print('Graficos mensais atualizados: {}'.format(men_total[:6]))

# ── 9. SLA cards ──
sla_c = sum(1 for r in records if r.get('sla') == 'CUMPRIU')
sla_n = sum(1 for r in records if r.get('sla') == 'N\xc3O CUMPRIU')
sla_pct = round(sla_c / (sla_c + sla_n) * 100, 1) if (sla_c + sla_n) > 0 else 0

html = re.sub(r'>1\.098<', '>' + str(sla_c) + '<', html)
html = re.sub(r'>417<',    '>' + str(sla_n) + '<', html)
html = re.sub(r'>73,5%<',  '>' + str(sla_pct) + '%<', html)
print('SLA: {} cumpriu | {} nao cumpriu | {}%'.format(sla_c, sla_n, sla_pct))

# ── 10. ML labels ──
html = re.sub(
    r'const ML=\[.*?\];',
    'const ML=' + json.dumps(MESES_PT[:len(meses_ord)]) + ';',
    html
)

# ── 11. Salva ──
with open('painel_orcamentos_2026_49.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('')
print('HTML atualizado com sucesso!')
print('  Total: {} | Aprov: {} | Aguard: {} | Reprov: {}'.format(
    total, aprovado, aguardando, reprovado))
print('  Valor: {} | Taxa: {}%'.format(fmt_val(kpis['valor']), kpis['taxa_geral']))
print('  SLA: {} cumpriu | {} fora prazo | {}%'.format(sla_c, sla_n, sla_pct))
print('  Junho: {} propostas'.format(kpis.get('jun_total', '?')))
print('  Data: {}'.format(kpis['data_atualizacao']))
