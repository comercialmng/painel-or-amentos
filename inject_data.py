#!/usr/bin/env python3
"""
Injeta data.json no HTML do painel.
v2.0 - Correcoes:
  BUG3: regex dinamico (nao mais hardcoded com valores fixos)
  NOVO: atualiza todos os KPIs, graficos e tabelas dinamicamente
"""
import json, re
from datetime import datetime

with open('data.json','r',encoding='utf-8') as f:
    D = json.load(f)

with open('painel_orcamentos_2026_49.html','r',encoding='utf-8') as f:
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
ok='#16a34a'; wa='#d97706'; er='#dc2626'
MESES_PT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

def fmt_val(v):
    v = float(v or 0)
    if v >= 1_000_000: return f'R$ {v/1_000_000:.1f}M'
    if v >= 1_000: return f'R$ {v/1000:.0f}k'
    return f'R$ {v:.0f}'

# ── 1. PROP (busca) ──
html = re.compile(r'const PROP=\[.*?\];', re.DOTALL).sub(
    'const PROP=' + json.dumps(records, ensure_ascii=False) + ';', html)
print(f"PROP: {len(records)} registros")

# ── 2. SUP_DATA ──
html = re.compile(r'const SUP_DATA=\[.*?\];', re.DOTALL).sub(
    'const SUP_DATA=' + json.dumps(sup_an, ensure_ascii=False) + ';', html)

# ── 3. SUP_MES ──
html = re.compile(r'const SUP_MES = \[.*?\];', re.DOTALL).sub(
    'const SUP_MES = ' + json.dumps(sup_mes, ensure_ascii=False) + ';', html)

# ── 4. Tabela supervisores ──
new_rows = ''
for s in sup_an:
    tx=s['taxa_aprov']; sc=s['score']
    bc='bg' if tx>=70 else 'by' if tx>=50 else 'br'
    scc='br' if sc>50 else 'by' if sc>20 else 'bg'
    new_rows += (
        f'<tr><td><b>{s["Supervisor"]}</b></td>'
        f'<td class="mono">{s["total"]}</td>'
        f'<td class="mono" style="color:{ok}">{s["aprovado"]}</td>'
        f'<td class="mono" style="color:{wa}">{s["aguardando"]}</td>'
        f'<td class="mono" style="color:{er}">{s["reprovado"]}</td>'
        f'<td><span class="bge {bc}">{tx}%</span></td>'
        f'<td><span class="bge {scc}">{sc}</span></td>'
        f'<td class="mono">{fmt_val(s.get("valor",0))}</td></tr>'
    )
html = re.compile(r'id="sup-tbody">.*?(?=</tbody>)', re.DOTALL).sub(
    f'id="sup-tbody">{new_rows}', html, count=1)

# ── 5. Data base ──
html = re.sub(r'Base: [\d/]+(?: \d{2}:\d{2})?',
              f'Base: {kpis["data_atualizacao"]}', html)

# ── 6. KPIs Visão Geral ──
total = kpis['total']; aprovado = kpis['aprovado']
aguardando = kpis['aguardando']; reprovado = kpis['reprovado']

def replace_kv(html, old_val, new_val):
    """Replace a KPI value inside a kv div."""
    pattern = rf'(<div class="kv"[^>]*>)\s*{re.escape(str(old_val))}\s*(</div>)'
    return re.sub(pattern, rf'\g<1>{new_val}\2', html, count=1)

# Total propostas
html = re.sub(r'(?<=>)2\.325(?=<)', f'{total:,}'.replace(',','.'), html)
# Aprovadas
html = re.sub(r'(?<="kv">)955(?=<)', str(aprovado), html)
# Aguardando
html = re.sub(r'(?<="kv">)1\.088(?=<)', str(aguardando), html)
# Reprovadas
html = re.sub(r'(?<="kv">)185(?=<)', str(reprovado), html)
# Taxa geral
html = re.sub(r'41\.1% conversão', f'{kpis["taxa_geral"]}% conversão', html)
# Taxas bandeiras
html = re.sub(r'43\.1%', f'{kpis["taxa_zamp"]}%', html, count=1)
html = re.sub(r'71\.2%', f'{kpis["taxa_botic"]}%', html, count=1)

# ── 7. Cards KPI mensais ──
sla_vals = [79.1, 65.1, 82.0, 57.0, 71.6, 97.8]  # SLA da planilha Excel (fixo)
for i in range(min(6, len(meses_ord))):
    mes = meses_ord[i]
    mes_label = MESES_PT[int(mes[5:])-1] + '/' + mes[2:4]
    total_m = men_total[i] if i < len(men_total) else 0
    valor_m = men_valor[i] if i < len(men_valor) else 0
    taxa_m  = men_taxa[i]  if i < len(men_taxa)  else 0
    sla_m   = sla_vals[i]  if i < len(sla_vals)  else 0
    taxa_cor = ok if taxa_m >= 50 else wa if taxa_m >= 40 else er

    # Substitui kv (total) do card desse mês
    pat = re.compile(
        rf'(<div class="kt">{re.escape(mes_label)}</div>'
        rf'<div class="kv">)\d+(</div>'
        rf'<div class="ks">R\$ )\d+(k · SLA [\d.]+%</div>'
        rf'<div style="[^"]*">Aprovação: )[\d.]+(%</div></div>)'
    )
    rep = rf'\g<1>{total_m}\2{valor_m}\3{taxa_m}\4{taxa_cor}\5'
    # Adjust replacement to also update color
    def make_rep(tm, vm, tam, tc):
        def inner(m):
            return (m.group(1) + str(tm) + m.group(2) + str(vm) +
                    m.group(3) + str(tam) +
                    f'</div><div style="font-size:11px;font-weight:600;color:{tc};'
                    f'margin-top:4px;padding-top:4px;border-top:1px solid var(--bd)">'
                    f'Aprovação: {tam}%</div></div>')
        return inner

    pat2 = re.compile(
        rf'(<div class="kt">{re.escape(mes_label)}</div>'
        rf'<div class="kv">)\d+(</div>'
        rf'<div class="ks">R\$ )\d+k · SLA [\d.]+%</div>'
        rf'<div[^>]*>Aprovação: [\d.]+%</div></div>'
    )
    replacement = (
        rf'\g<1>{total_m}\2{valor_m}k · SLA {sla_m}%</div>'
        rf'<div style="font-size:11px;font-weight:600;color:{taxa_cor};'
        rf'margin-top:4px;padding-top:4px;border-top:1px solid var(--bd)">'
        rf'Aprovação: {taxa_m}%</div></div>'
    )
    html = pat2.sub(replacement, html, count=1)

# ── 8. Gráficos mensais — BUG3 FIX: regex dinâmico ──
# Identifica os 4 datasets do mensal por posicao contextual
# (nao mais por valores hardcoded)

# Padrão: dentro do chart cVolMes
def update_chart_data(html, chart_id, new_data, dataset_index=0):
    """
    Encontra chart por ID e substitui o dataset na posição especificada.
    Regex dinâmico — não depende dos valores antigos.
    """
    # Encontra o bloco do chart
    idx = html.find(f"new Chart('{chart_id}'")
    if idx < 0:
        print(f"  AVISO: chart '{chart_id}' não encontrado")
        return html

    # Encontra o fim do chart
    end_idx = html.find(');', idx)
    chunk = html[idx:end_idx+2]

    # Substitui o n-ésimo dataset.data
    data_pattern = re.compile(r'data:\[[\d.,\s-]+\]')
    matches = list(data_pattern.finditer(chunk))

    if dataset_index >= len(matches):
        print(f"  AVISO: chart '{chart_id}' não tem dataset {dataset_index}")
        return html

    m = matches[dataset_index]
    new_chunk = chunk[:m.start()] + f'data:{json.dumps(new_data)}' + chunk[m.end():]
    return html[:idx] + new_chunk + html[end_idx+2:]

html = update_chart_data(html, 'cVolMes',   men_total[:6], 0)
html = update_chart_data(html, 'cValorMes', men_valor[:6], 0)
html = update_chart_data(html, 'cTaxaMensal', men_taxa[:6], 0)
print(f"Gráficos mensais atualizados: {men_total[:6]}")

# ── 9. SLA cards (Cumpriu / Fora prazo / %) ──
sla_c = sum(1 for r in records if r.get('sla') == 'CUMPRIU')
sla_n = sum(1 for r in records if r.get('sla') == 'NÃO CUMPRIU')
sla_pct = round(sla_c/(sla_c+sla_n)*100, 1) if (sla_c+sla_n) > 0 else 0

html = re.sub(r'>1\.098<', f'>{sla_c}<', html)
html = re.sub(r'>417<', f'>{sla_n}<', html)
html = re.sub(r'>73,5%<', f'>{sla_pct}%<', html)

# ── 10. ML labels ──
html = re.sub(r"const ML=\[.*?\];",
    f"const ML={json.dumps(MESES_PT[:len(meses_ord)])};", html)

# ── 11. Salva ──
with open('painel_orcamentos_2026_49.html','w',encoding='utf-8') as f:
    f.write(html)

print(f"\n✅ HTML atualizado!")
print(f"   Total: {total} | Aprov: {aprovado} | Aguard: {aguardando} | Reprov: {reprovado}")
print(f"   Valor: {fmt_val(kpis['valor'])} | Taxa: {kpis['taxa_geral']}%")
print(f"   SLA: {sla_c} cumpriu | {sla_n} fora prazo | {sla_pct}%")
print(f"   Junho: {kpis.get('jun_total','?')} propostas")
print(f"   Data: {kpis['data_atualizacao']}")
