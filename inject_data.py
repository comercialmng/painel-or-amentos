#!/usr/bin/env python3
"""
inject_data.py v3.1 - DEFINITIVO
Le data.json e injeta todos os dados no HTML do painel.
"""
import json, re, sys, os
from datetime import datetime

HTML_FILE = 'painel_orcamentos_2026_49.html'
DATA_FILE = 'data.json'

for f in [DATA_FILE, HTML_FILE]:
    if not os.path.exists(f):
        print(f"ERRO: {f} nao encontrado"); sys.exit(1)

with open(DATA_FILE, encoding='utf-8') as f:
    data = json.load(f)
with open(HTML_FILE, encoding='utf-8') as f:
    html = f.read()

kpis     = data.get('kpis', {})
records  = data.get('records', [])
temp_niv = data.get('temp_niveis', {})

def js(val):
    return json.dumps(val, ensure_ascii=False)

def inject(html, var, value):
    pattern = rf'(window\.{re.escape(var)}\s*=\s*)([^;]+?)(;)'
    new_html, n = re.subn(pattern, rf'\g<1>{js(value)}\3', html, flags=re.DOTALL)
    if n == 0:
        insert = f'  window.{var} = {js(value)};\n'
        new_html = html.replace('</script>', insert + '</script>', 1)
        if new_html == html:
            new_html = html + f'\n<script>\n  window.{var} = {js(value)};\n</script>\n'
    return new_html

print("Injetando dados no HTML...")
erros = []

variaveis = [
    # KPIs visão geral
    ('totalPropostas',      kpis.get('total', 0)),
    ('valorTotal',          kpis.get('valor', 0)),
    ('totalAprovadas',      kpis.get('aprovado', 0)),
    ('totalRecusadas',      kpis.get('reprovado', 0)),
    ('totalAguardando',     kpis.get('aguardando', 0)),
    ('taxaAprovacao',       kpis.get('taxa_geral', 0)),
    ('taxaZamp',            kpis.get('taxa_zamp', 0)),
    ('taxaBoticario',       kpis.get('taxa_botic', 0)),
    ('aprovZamp',           kpis.get('aprov_zamp', 0)),
    ('totalZamp',           kpis.get('total_zamp', 0)),
    ('aprovBoticario',      kpis.get('aprov_botic', 0)),
    ('totalBoticario',      kpis.get('total_botic', 0)),
    ('dataAtualizacao',     kpis.get('data_atualizacao', '')),
    # Etapas operacionais
    ('etapaMplan',          kpis.get('etapa_mplan', 0)),
    ('etapaAprovSup',       kpis.get('etapa_aprov_sup', 0)),
    ('etapaBacklogGeral',   kpis.get('etapa_backlog_geral', 0)),
    ('etapaBacklogZamp',    kpis.get('etapa_backlog_zamp', 0)),
    ('etapaElaboracao',     kpis.get('etapa_elaboracao', 0)),
    ('etapaValidacao',      kpis.get('etapa_validacao', 0)),
    ('etapaReavaliacao',    kpis.get('etapa_reavaliacao', 0)),
    ('etapaEnviado',        kpis.get('etapa_enviado', 0)),
    ('etapaAceito',         kpis.get('etapa_aceito', 0)),
    ('etapaRecusado',       kpis.get('etapa_recusado', 0)),
    ('etapaNaoAprovadas',   kpis.get('etapa_nao_aprovadas', 0)),
    # SLA
    ('slaBacklog',          kpis.get('sla_backlog', 0)),
    ('slaFallback',         kpis.get('sla_fallback', 0)),
    ('slaSemData',          kpis.get('sla_sem_data', 0)),
    # Temperatura
    ('tempQuente',          temp_niv.get('QUENTE', 0)),
    ('tempMorno',           temp_niv.get('MORNO', 0)),
    ('tempEsfriando',       temp_niv.get('ESFRIANDO', 0)),
    ('tempFrio',            temp_niv.get('FRIO', 0)),
    ('tempSemData',         temp_niv.get('SEM_DATA', 0)),
    # Mensal
    ('mesesLabels',         data.get('men_labels', [])),
    ('mesesTotal',          data.get('men_total', [])),
    ('mesesAprov',          data.get('men_aprov', [])),
    ('mesesAguar',          data.get('men_aguar', [])),
    ('mesesReprov',         data.get('men_reprov', [])),
    ('mesesValor',          data.get('men_valor', [])),
    ('mesesTaxa',           data.get('men_taxa', [])),
    ('mesesOrd',            data.get('meses_ord', [])),
    # Supervisores
    ('supAnalysis',         data.get('sup_analysis', [])),
    ('supMesData',          data.get('sup_mes_data', [])),
    # Orçamentistas
    ('orcAnalysis',         data.get('orc_analysis', [])),
    # Regiões
    ('ufAnalysis',          data.get('uf_analysis', [])),
    # Bandeiras
    ('bandAnalysis',        data.get('band_analysis', [])),
    # Records completos
    ('allRecords',          records),
    # Retrocompatibilidade
    ('junTotal',            kpis.get('jun_total', 0)),
]

for var, valor in variaveis:
    try:
        html = inject(html, var, valor)
    except Exception as e:
        erros.append(f"  ERRO {var}: {e}")

with open(HTML_FILE, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✓ HTML atualizado: {HTML_FILE}")
print(f"\n{'─'*45}")
print(f"  Total propostas:        {kpis.get('total',0)}")
print(f"  Aprovadas (Aceito):     {kpis.get('aprovado',0)}")
print(f"  Recusadas:              {kpis.get('reprovado',0)}")
print(f"  Taxa geral:             {kpis.get('taxa_geral',0)}%")
print(f"  Valor total:            R$ {round(kpis.get('valor',0)/1000)}k")
print(f"{'─'*45}")
print(f"  Solicitação MPLAN:      {kpis.get('etapa_mplan',0)}")
print(f"  Aprovado Supervisor:    {kpis.get('etapa_aprov_sup',0)}")
print(f"  Backlog Geral:          {kpis.get('etapa_backlog_geral',0)}")
print(f"  Backlog ZAMP:           {kpis.get('etapa_backlog_zamp',0)}")
print(f"  Elaboração:             {kpis.get('etapa_elaboracao',0)}")
print(f"  Validação Coord.:       {kpis.get('etapa_validacao',0)}")
print(f"  Reavaliação Sup.:       {kpis.get('etapa_reavaliacao',0)}")
print(f"  Enviado ao Cliente:     {kpis.get('etapa_enviado',0)}")
print(f"  Aceito:                 {kpis.get('etapa_aceito',0)}")
print(f"  Recusado:               {kpis.get('etapa_recusado',0)}")
print(f"{'─'*45}")
print(f"  Temp Quente:            {temp_niv.get('QUENTE',0)}")
print(f"  Temp Morno:             {temp_niv.get('MORNO',0)}")
print(f"  Temp Esfriando:         {temp_niv.get('ESFRIANDO',0)}")
print(f"  Temp Frio:              {temp_niv.get('FRIO',0)}")
print(f"{'─'*45}")
print(f"  Junho 2026:             {kpis.get('jun_total',0)}")

if erros:
    print(f"\nAVISOS:")
    for e in erros: print(e)
else:
    print(f"\n✓ Todas as {len(variaveis)} variáveis injetadas sem erros.")
