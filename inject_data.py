#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_data.py — Painel de Orcamentos Maneng 2026
Busca dados do Bitrix24 (crm.quote) e injeta no HTML do painel.
Executado via GitHub Actions (2x por dia automaticamente).
"""

import os
import json
import math
import requests
from datetime import datetime, date, timedelta
from collections import defaultdict

# ── Configuracoes ──────────────────────────────────────────────────────────────
WEBHOOK = os.environ.get("BITRIX_WEBHOOK", "https://b24-uh4kmt.bitrix24.com.br/rest/11/omlax01nlmjsovjk/")
HTML_TEMPLATE = "painel_orcamentos_2026_49.html"
HTML_OUTPUT   = "painel_orcamentos_2026_49.html"
MAX_PAGES     = 50   # segurança: maximo de paginas paginadas

# ── Supervisores e orçamentistas ───────────────────────────────────────────────
SUPERVISORES = [
    "Igor Lajusticia",
    "Humberto Cavalcanti",
    "Franckllyn Moreira",
    "Vagner de Brito",
    "Raul Rodrigues",
    "Fernando Melgarejo",
    "Flávio Bezerra",
    "Thiago dos Anjos",
    "Edwilder Costa",
    "Ronie Bandeira",
    "Daniel Brandão",
    "Bruno Lima",
    "Bruno Almeida",
    "André José",
    "Elton Douglas",
    "Pedro Vargas",
    "Felipe Benício",
]

# Orçamentistas: mapeamento de nome → bandeiras atendidas
ORCAMENTISTAS = {
    "Francyne Lima":       ["geral"],
    "Ana Beatriz Araújo":  ["Zamp", "BK", "Burger King"],
    "Adelaide Matos":      ["geral"],
    "Maria Aparecida Silva": ["geral"],
}

# Status finais de aprovacao/recusa do crm.quote
STATUS_APROVADO = {"P", "A", "WON"}          # ajuste conforme seu Bitrix
STATUS_ENVIADO  = {"D", "S", "SENT"}
STATUS_RECUSADO = {"L", "LOST", "N"}
STATUS_PENDENTE = {"NEW", "1", "DRAFT"}       # aguardando envio/aprovacao

# ── Helpers ────────────────────────────────────────────────────────────────────
def safe_float(val):
    try:
        return float(str(val).replace(",", ".").strip()) if val else 0.0
    except (ValueError, TypeError):
        return 0.0

def parse_date(val):
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(str(val)[:19], fmt[:len(fmt)])
            return dt.date() if hasattr(dt, "date") else dt
        except ValueError:
            continue
    return None

def business_days(start, end):
    """Conta dias uteis entre duas datas (sem feriados)."""
    if not start or not end:
        return None
    d, count = start, 0
    while d < end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count

def get_bandeira(title, extra_field=None):
    if extra_field:
        return str(extra_field).strip()
    title = str(title or "").upper()
    if any(x in title for x in ["BURGER KING", "BK", "BURGUER"]):
        return "Burger King"
    if "ZAMP" in title:
        return "Zamp"
    if any(x in title for x in ["MCDO", "MC DONALD", "MCDONALD"]):
        return "McDonald's"
    if any(x in title for x in ["HABIB", "HABIBS"]):
        return "Habib's"
    if any(x in title for x in ["KFC", "KENTUCKY"]):
        return "KFC"
    if "SUBWAY" in title:
        return "Subway"
    if any(x in title for x in ["POPEYES", "POPEYE"]):
        return "Popeyes"
    if "GIRAFFAS" in title:
        return "Giraffas"
    if any(x in title for x in ["PIZZA HUT", "PIZZAHUT"]):
        return "Pizza Hut"
    return "Outros"

def get_status_label(status_id):
    s = str(status_id or "").upper()
    if s in STATUS_APROVADO:
        return "Aprovado"
    if s in STATUS_ENVIADO:
        return "Enviado"
    if s in STATUS_RECUSADO:
        return "Recusado"
    return "Pendente"

# ── Busca Bitrix ───────────────────────────────────────────────────────────────
def fetch_all_quotes():
    """Pagina crm.quote.list ate buscar todos os registros de 2026."""
    url = WEBHOOK.rstrip("/") + "/crm.quote.list.json"
    all_items = []
    start = 0

    fields = [
        "ID", "TITLE", "DATE_CREATE", "DATE_MODIFY",
        "STATUS_ID", "OPPORTUNITY", "CURRENCY_ID",
        "ASSIGNED_BY_ID", "ASSIGNED_BY",
        "CREATED_BY_ID", "CREATED_BY",
        "UF_CRM_QUOTE_BANDEIRA", "UF_CRM_BANDEIRA",
        "BEGINDATE", "CLOSEDATE",
        "CONTACT_ID", "COMPANY_ID",
        "COMMENTS", "LEAD_ID",
    ]

    for _ in range(MAX_PAGES):
        params = {
            "order":  {"DATE_CREATE": "ASC"},
            "filter": {">=DATE_CREATE": "2026-01-01"},
            "select": fields,
            "start":  start,
        }
        try:
            resp = requests.post(url, json=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[ERRO] Falha na requisicao Bitrix (start={start}): {exc}")
            break

        items = data.get("result", [])
        all_items.extend(items)
        print(f"  Pagina start={start}: {len(items)} registros (total ate agora: {len(all_items)})")

        total = int(data.get("total", 0))
        if len(all_items) >= total:
            break
        start += 50

    print(f"Total de quotes buscadas: {len(all_items)}")
    return all_items

# ── Processamento ──────────────────────────────────────────────────────────────
def process_quotes(quotes):
    """
    Processa a lista bruta de quotes e retorna estruturas de dados
    prontas para injecao no HTML.
    """
    hoje = date.today()
    ano_atual = 2026

    # Filtra apenas 2026
    registros = []
    for q in quotes:
        d = parse_date(q.get("DATE_CREATE"))
        if not d or d.year != ano_atual:
            continue
        q["_date"] = d
        registros.append(q)

    # ── Metricas globais ──
    total = len(registros)
    valor_total = sum(safe_float(q.get("OPPORTUNITY")) for q in registros)

    aprovados  = [q for q in registros if get_status_label(q.get("STATUS_ID")) == "Aprovado"]
    enviados   = [q for q in registros if get_status_label(q.get("STATUS_ID")) == "Enviado"]
    recusados  = [q for q in registros if get_status_label(q.get("STATUS_ID")) == "Recusado"]
    pendentes  = [q for q in registros if get_status_label(q.get("STATUS_ID")) == "Pendente"]

    taxa_conv = round(len(aprovados) / total * 100, 1) if total else 0

    # ── SLA (aprovacao supervisao → envio ao cliente) ──
    # Aqui consideramos DATE_CREATE → DATE_MODIFY como proxy ate termos campo especifico
    sla_dentro = sla_fora = 0
    for q in enviados + aprovados:
        dc = parse_date(q.get("DATE_CREATE"))
        dm = parse_date(q.get("DATE_MODIFY"))
        dias = business_days(dc, dm) if dc and dm else None
        if dias is not None:
            if dias <= 3:
                sla_dentro += 1
            else:
                sla_fora += 1

    sla_total = sla_dentro + sla_fora
    sla_pct   = round(sla_dentro / sla_total * 100, 1) if sla_total else 0

    # ── Por mes ──
    por_mes = defaultdict(lambda: {"total": 0, "aprovados": 0, "valor": 0.0})
    meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                   "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    for q in registros:
        m = q["_date"].month
        por_mes[m]["total"]    += 1
        por_mes[m]["valor"]    += safe_float(q.get("OPPORTUNITY"))
        if get_status_label(q.get("STATUS_ID")) == "Aprovado":
            por_mes[m]["aprovados"] += 1

    series_labels   = []
    series_total    = []
    series_aprovado = []
    series_valor    = []
    for m in range(1, 13):
        if por_mes[m]["total"] > 0 or m <= hoje.month:
            series_labels.append(meses_nomes[m - 1])
            series_total.append(por_mes[m]["total"])
            series_aprovado.append(por_mes[m]["aprovados"])
            series_valor.append(round(por_mes[m]["valor"] / 1000, 1))  # em K

    # ── Por supervisor ──
    sup_map = defaultdict(lambda: {
        "nome": "", "total": 0, "aprovados": 0, "enviados": 0,
        "recusados": 0, "pendentes": 0, "valor": 0.0,
        "sla_dentro": 0, "sla_fora": 0,
    })

    for q in registros:
        resp = q.get("ASSIGNED_BY") or q.get("CREATED_BY") or ""
        # Tenta normalizar para supervisor conhecido
        sup_nome = None
        for s in SUPERVISORES:
            partes = s.lower().split()
            if any(p in str(resp).lower() for p in partes if len(p) > 3):
                sup_nome = s
                break
        if not sup_nome:
            sup_nome = str(resp).strip() or "Não atribuído"

        row = sup_map[sup_nome]
        row["nome"]  = sup_nome
        row["total"] += 1
        row["valor"] += safe_float(q.get("OPPORTUNITY"))
        lbl = get_status_label(q.get("STATUS_ID"))
        row[lbl.lower() + "s"] = row.get(lbl.lower() + "s", 0) + 1

        dc = parse_date(q.get("DATE_CREATE"))
        dm = parse_date(q.get("DATE_MODIFY"))
        dias = business_days(dc, dm) if dc and dm else None
        if dias is not None and lbl in ("Aprovado", "Enviado"):
            if dias <= 3:
                row["sla_dentro"] += 1
            else:
                row["sla_fora"]   += 1

    supervisores_data = sorted(sup_map.values(), key=lambda x: x["total"], reverse=True)
    for row in supervisores_data:
        t = row["sla_dentro"] + row["sla_fora"]
        row["sla_pct"] = round(row["sla_dentro"] / t * 100, 1) if t else 0
        row["taxa"]    = round(row["aprovados"] / row["total"] * 100, 1) if row["total"] else 0

    # ── Por orçamentista ──
    orc_map = defaultdict(lambda: {
        "nome": "", "total": 0, "aprovados": 0, "valor": 0.0,
    })
    for q in registros:
        # Tenta mapear via campo responsavel
        resp = q.get("ASSIGNED_BY") or q.get("CREATED_BY") or ""
        orc_nome = None
        for o in ORCAMENTISTAS:
            partes = o.lower().split()
            if any(p in str(resp).lower() for p in partes if len(p) > 3):
                orc_nome = o
                break
        if not orc_nome:
            # Atribuicao por bandeira
            bandeira = get_bandeira(q.get("TITLE", ""), q.get("UF_CRM_QUOTE_BANDEIRA") or q.get("UF_CRM_BANDEIRA"))
            if bandeira in ("Zamp", "BK", "Burger King"):
                orc_nome = "Ana Beatriz Araújo"
            else:
                orc_nome = "Francyne Lima"

        row = orc_map[orc_nome]
        row["nome"]     = orc_nome
        row["total"]   += 1
        row["valor"]   += safe_float(q.get("OPPORTUNITY"))
        if get_status_label(q.get("STATUS_ID")) == "Aprovado":
            row["aprovados"] += 1

    orcamentistas_data = sorted(orc_map.values(), key=lambda x: x["total"], reverse=True)
    for row in orcamentistas_data:
        row["taxa"] = round(row["aprovados"] / row["total"] * 100, 1) if row["total"] else 0

    # ── Por bandeira ──
    band_map = defaultdict(lambda: {"nome": "", "total": 0, "aprovados": 0, "valor": 0.0})
    for q in registros:
        b = get_bandeira(q.get("TITLE", ""), q.get("UF_CRM_QUOTE_BANDEIRA") or q.get("UF_CRM_BANDEIRA"))
        band_map[b]["nome"]     = b
        band_map[b]["total"]   += 1
        band_map[b]["valor"]   += safe_float(q.get("OPPORTUNITY"))
        if get_status_label(q.get("STATUS_ID")) == "Aprovado":
            band_map[b]["aprovados"] += 1

    bandeiras_data = sorted(band_map.values(), key=lambda x: x["total"], reverse=True)
    for row in bandeiras_data:
        row["taxa"] = round(row["aprovados"] / row["total"] * 100, 1) if row["total"] else 0

    # ── Cards recentes (aba Busca) ──
    recentes = sorted(registros, key=lambda x: x["_date"], reverse=True)[:200]
    cards = []
    for q in recentes:
        cards.append({
            "id":         q.get("ID"),
            "titulo":     q.get("TITLE", ""),
            "status":     get_status_label(q.get("STATUS_ID")),
            "status_id":  q.get("STATUS_ID"),
            "valor":      safe_float(q.get("OPPORTUNITY")),
            "data":       q["_date"].strftime("%d/%m/%Y"),
            "bandeira":   get_bandeira(q.get("TITLE", ""), q.get("UF_CRM_QUOTE_BANDEIRA") or q.get("UF_CRM_BANDEIRA")),
            "responsavel": q.get("ASSIGNED_BY") or q.get("CREATED_BY") or "",
        })

    return {
        "gerado_em":        datetime.now().strftime("%d/%m/%Y %H:%M"),
        "data_base":        hoje.strftime("%d/%m/%Y"),
        "total":            total,
        "aprovados":        len(aprovados),
        "enviados":         len(enviados),
        "recusados":        len(recusados),
        "pendentes":        len(pendentes),
        "taxa_conv":        taxa_conv,
        "valor_total":      round(valor_total, 2),
        "sla_pct":          sla_pct,
        "sla_dentro":       sla_dentro,
        "sla_fora":         sla_fora,
        "series_labels":    series_labels,
        "series_total":     series_total,
        "series_aprovado":  series_aprovado,
        "series_valor":     series_valor,
        "supervisores":     supervisores_data,
        "orcamentistas":    orcamentistas_data,
        "bandeiras":        bandeiras_data,
        "cards":            cards,
    }

# ── Injecao no HTML ────────────────────────────────────────────────────────────
def inject_into_html(dados, template_path, output_path):
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Bloco JSON injetado antes de </body>
    json_block = f"""
<script id="__painel_data__" type="application/json">
{json.dumps(dados, ensure_ascii=False, indent=2)}
</script>
<script>
// Injeta dados automaticamente assim que o DOM carrega
(function() {{
  try {{
    var raw  = document.getElementById('__painel_data__').textContent;
    var data = JSON.parse(raw);
    if (typeof window.PAINEL_DATA === 'undefined') window.PAINEL_DATA = {{}};
    Object.assign(window.PAINEL_DATA, data);
    // Dispara evento para o painel reagir
    document.dispatchEvent(new CustomEvent('painelDataReady', {{ detail: data }}));
  }} catch(e) {{ console.error('inject_data: parse error', e); }}
}})();
</script>
"""

    # Remove bloco anterior se existir (reexecucao)
    import re
    html = re.sub(
        r'<script id="__painel_data__".*?</script>\s*<script>.*?</script>',
        "",
        html,
        flags=re.DOTALL,
    )

    # Injeta e atualiza data de base no cabecalho
    html = html.replace("</body>", json_block + "\n</body>")
    html = re.sub(
        r'(Base:|Atualizado em:|Gerado em:)\s*[\d/]+ [\d:]+',
        f'Base: {dados["data_base"]}',
        html,
    )
    html = re.sub(
        r'(Base:|Atualizado em:)\s*[\d/]+',
        f'Base: {dados["data_base"]}',
        html,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = len(html.encode("utf-8")) // 1024
    print(f"HTML gravado: {output_path}  ({size_kb} KB)")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"inject_data.py — Painel Orcamentos Maneng 2026")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not WEBHOOK:
        raise RuntimeError("Variavel BITRIX_WEBHOOK nao definida!")

    print("\n[1/3] Buscando quotes do Bitrix24...")
    quotes = fetch_all_quotes()

    print(f"\n[2/3] Processando {len(quotes)} registros...")
    dados = process_quotes(quotes)

    print("\n[3/3] Injetando dados no HTML...")
    inject_into_html(dados, HTML_TEMPLATE, HTML_OUTPUT)

    print("\nResumo:")
    print(f"  Total 2026 ......... {dados['total']}")
    print(f"  Aprovados .......... {dados['aprovados']}")
    print(f"  Taxa conversao ..... {dados['taxa_conv']}%")
    print(f"  Valor total ........ R$ {dados['valor_total']:,.2f}")
    print(f"  SLA cumprido ....... {dados['sla_pct']}%")
    print(f"  Data base .......... {dados['data_base']}")
    print("\nConcluido!")

if __name__ == "__main__":
    main()
