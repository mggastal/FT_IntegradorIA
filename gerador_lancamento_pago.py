#!/usr/bin/env python3
"""Gerador Dashboard Lançamento Pago v4"""

import pandas as pd, json, re, hashlib, requests
from datetime import date
from pathlib import Path

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════
SHEET_ID         = "1LfPKehGDjoz9QPue_TJrbyZQ0fzxxmvUMRNZfMPOwhE"
TEMPLATE_FILE    = "dashboard_lancamento_pago.html"
OUTPUT_FILE      = "index.html"
NOME_CLIENTE     = "Integrador IA"
LOGO_LETRA       = "IA"
COR_ACENTO       = "#252F26"
LANCAMENTO_COD   = "CERTIF-IA"      # filtra campanhas pelo código; "" = ver tudo
USAR_PESQUISA    = True            # False = oculta aba Pesquisa no menu e dashboard
USAR_ORIGEM      = True            # pizza Pago vs Orgânico (classificação por código de oferta)
FUNIL_TITULO     = "Análise do Funil Pago (Meta Ads)"
FUNIL_COMPRAS_PAGO = True          # True = etapa "Compras" do funil usa vendas com SCK pago (não o pixel do Meta)
USAR_LOGO        = False           # False = não usa logo.png (sidebar mostra só a letra; sem favicon)
USAR_RODAPE      = False           # False = oculta o rodapé "Desenvolvido por Sobé Estratégias"
PRODUTOS_HOTMART = ["Alta Demanda: Acceso VIP","Alta Demanda: Acceso General"]  # produtos da captação
# ── Classificação Pago vs Orgânico: pelo CÓDIGO DA OFERTA (fonte da verdade) ──
# Vendas nessas ofertas = tráfego pago; todo o resto = orgânico (resolve UTMs vazias do pago)
OFERTAS_PAGO     = ["jiohudh9",   # Landing A · 10 USD
                    "r4rmy0ai",   # Landing A · 29 USD
                    "3znreyg2",   # Landing B · 10 USD
                    "qc4j499r",   # Landing B · 29 USD
                    "rln5ac84"]   # VIP · código adicional (confirmado pago)
# (SCK ainda é lido para as tabelas de UTM, mas NÃO define mais a origem)
SCK_SRC_PAGO     = ["fb","facebook","ig","instagram"]
# Valor por venda: como a Hotmart traz moedas misturadas, cada venda conta um valor FIXO.
# VALOR_FIXO = 10 → cada venda vale US$10 (ignora o preço da planilha). None = usa o preço da planilha.
VALOR_FIXO       = None
# VALOR_POR_PRODUTO: valor FIXO por produto (tem prioridade sobre VALOR_FIXO). None = desligado.
# Ex.: {"Produto A": 29, "Produto B": 10}
VALOR_POR_PRODUTO = {"Alta Demanda: Acceso VIP": 29, "Alta Demanda: Acceso General": 10}
# META_INVEST: meta de investimento do lançamento (mostra % no KPI). None = sem meta.
META_INVEST      = 10000   # meta de investimento do lançamento
MOEDA_SIMBOLO    = "$"             # símbolo exibido no dashboard (ex: "$", "US$", "R$")
FONTE_LABEL      = "Hotmart"       # rótulo sob o KPI de Vendas
NOTA_RECEITA     = "* Receita e ROAS: valor fixo por produto (VIP $29 · General $10)"
USAR_IDIOMAS     = True            # True = botão PT/ES na topbar traduz o relatório
IDIOMA_PADRAO    = "es"            # idioma inicial do relatório: "es" ou "pt"
# Vendas extras (fora do relatório) — injetadas manualmente. Cada uma conta VALOR_FIXO.
# Formato: {"data":"dd/mm/aaaa","qtd":N}. [] = nenhuma.
VENDAS_EXTRAS    = []
EXTRAS_LABEL     = "Fora do relatório"   # rótulo no card Vendas por SCK
EXTRAS_ORIGEM    = "Orgânico"            # Pago | Orgânico (entra no gráfico de origem)
# Produto PRINCIPAL do lançamento (alto ticket) — página própria com atribuição por jornada.
# Vendas dele não têm SCK; origem/destino são herdados da compra do Acceso VIP pelo E-MAIL do
# comprador (cruzamento feito AQUI no gerador — e-mails nunca vão para o HTML público).
PRODUTO_CERT = None   # etapa de captação — sem vendas do produto principal ainda.
# Quando abrir as vendas, configurar assim (nome EXATO do produto na Hotmart):
# PRODUTO_CERT = {"nome":"<nome do produto>","apelido":"Ventas","valor":<preço>}
CERT_INICIO  = "05/08/2026"   # vendas ANTES desta data são teste — ignoradas
# Upsells do lançamento — identificados pelo CÓDIGO DE OFERTA (o produto pode vender por outras ofertas fora do lançamento)
UPSELLS = [   # upsell NÃO entra no CAC (só vendas de captação contam lá); entra no Faturamento Total
    {"oferta":"p3fvhage","nome":"Ebook Más IA Menos Chamba","valor":19},
]

# Comparativo de especialistas/lados — casa tokens no nome da campanha (invest) e nos UTMs (vendas).
# Ordem importa: o primeiro lado que casar vence. [] = painel oculto.
LADOS_COMPARATIVO = []   # sem comparativo de lados neste lançamento

CPA_BOM          = 14
CPA_MEDIO        = 21
ROAS_BOM         = 0.69
ROAS_MEDIO       = 0.5

# Metas do funil — define cores (verde/amarelo/vermelho) nas taxas
# Cada métrica: [valor_bom, valor_medio] — acima do bom = verde, entre = amarelo, abaixo = vermelho
CTR_BOM          = 1.0    # CTR ≥ 1.0% → verde | 0.8-1.0% → amarelo | <0.8% → vermelho
CTR_MEDIO        = 0.8
CR_BOM           = 71.0   # Connect Rate ≥ 71% → verde | 63-71% → amarelo | <63% → vermelho
CR_MEDIO         = 63.0
TX_IC_BOM        = 15.0   # Tx Init Checkout ≥ 15% → verde | 12-15% → amarelo | <12% → vermelho
TX_IC_MEDIO      = 12.0
TX_CK_BOM        = 25.0   # Taxa Checkout ≥ 25% → verde | 20-25% → amarelo | <20% → vermelho
TX_CK_MEDIO      = 20.0
TX_CONV_BOM      = 7.0    # Taxa Conversão LP ≥ 7% → verde | 5-7% → amarelo | <5% → vermelho
TX_CONV_MEDIO    = 5.0

CPM_BOM          = 40.0    # CPM ≤ 7 → verde | 7-12 → amarelo | >12 → vermelho (menor = melhor)
CPM_MEDIO        = 60.0

# ══════════════════════════════════════════════════════
def sheet_url(t): return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={t}"
URL_META = sheet_url("meta-ads")
URL_HOT  = sheet_url("hotmart-AltaDemanda")
URL_PES  = sheet_url("Pesquisa")
URL_GA   = sheet_url("breakdown-gender-age")
URL_PT   = sheet_url("breakdown-platform")
URL_RG   = sheet_url("breakdown-regiao")
URL_CERT = sheet_url("hotmart-CertificacionELF")
URL_CRIAT= sheet_url("Criativos_x_Links")   # aba opcional: colA = nome do criativo, colB = link

# Links fixos dos criativos (FALLBACK embutido — funciona mesmo sem a aba na planilha).
# A aba "Criativos_x_Links" (colA nome, colB link), se existir, COMPLEMENTA/SOBREPÕE esta lista.
CRIATIVOS_LINKS_FIXOS = {}


def to_num(s):
    """Converte série para numérico — detecta formato BR (1.234,56) ou US (1234.56)"""
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0)
    clean = s.astype(str).str.strip().str.replace("R$","",regex=False).str.strip()
    # Formato BR: tem vírgula como decimal (ex: "29,9" ou "1.234,56")
    if clean.str.contains(r"\d,\d", regex=True).any():
        clean = clean.str.replace(".","",regex=False).str.replace(",",".",regex=False)
    # Formato US ou sem separador: usar direto (não remover pontos)
    return pd.to_numeric(clean, errors="coerce").fillna(0)
def safe(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return None
    return round(float(v),2) if float(v)!=0 else None
def download_thumb(url, d):
    if not url or str(url)=="nan": return ""
    try:
        ext=".png" if ".png" in url.lower() else ".jpg"
        fname=hashlib.md5(url.encode()).hexdigest()[:16]+ext
        fp=d/fname
        if not fp.exists():
            r=requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code==200: fp.write_bytes(r.content)
            else: return ""
        return "imgs/"+fname
    except: return ""

# ── País: mapa nome (Hotmart) → código 2 letras (igual ao breakdown-regiao) ──
import unicodedata as _ud
def _norm_pais(s):
    return _ud.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower().strip()
PAIS_2L = {"colombia":"CO","mexico":"MX","estados unidos":"US","estados unidos de america":"US",
    "peru":"PE","ecuador":"EC","chile":"CL","argentina":"AR","costa rica":"CR","portugal":"PT",
    "guatemala":"GT","espana":"ES","republica dominicana":"DO","puerto rico":"PR","canada":"CA",
    "suiza":"CH","honduras":"HN","brasil":"BR","brazil":"BR","bolivia":"BO","uruguay":"UY",
    "paraguay":"PY","venezuela":"VE","panama":"PA","nicaragua":"NI","el salvador":"SV","italia":"IT",
    "francia":"FR","alemania":"DE","reino unido":"GB","australia":"AU","japon":"JP"}
def pais_code(nome):
    n=_norm_pais(nome)
    if not n or n=="nan": return ""
    return PAIS_2L.get(n, str(nome).strip().upper()[:14])

# ══ HOTMART + SCK (carrega primeiro para ter ticket_medio) ══
import html as _html, urllib.parse as _up

def parse_sck(s):
    """Decodifica o SCK (query string com &amp;) e devolve dict com utm_* + origem."""
    if not isinstance(s,str) or s.strip().lower() in ("","nan"):
        return {"source":"","medium":"","campaign":"","content":"","term":"","origem":"Direto"}
    s_limpo = _html.unescape(s).strip()
    # Formato por PONTOS (ex.: "ig.00-MIX-HOT-ALL-MX.CERTIF-IA-SET-26" ou "ig.paid.<id>"):
    # segmento 1 = fonte · 2 = conjunto/medium · 3+ = campanha
    if "=" not in s_limpo and "." in s_limpo:
        partes = [p.strip() for p in s_limpo.split(".")]
        psrc   = (partes[0] or "").lower()
        pmed   = partes[1] if len(partes) >= 2 else ""
        pcamp  = ".".join(partes[2:]) if len(partes) >= 3 else ""
        if psrc in SCK_SRC_PAGO: porig = "Pago"
        elif psrc == "email":    porig = "Orgânico"
        elif psrc == "":         porig = "Direto"
        else:                    porig = "Orgânico"
        return {"source":psrc,"medium":pmed,"campaign":pcamp,"content":"","term":pcamp,"origem":porig}
    q = dict(_up.parse_qsl(s_limpo))
    src = (q.get("utm_source","") or "").strip().lower()
    if src in SCK_SRC_PAGO: origem = "Pago"
    elif src == "email":    origem = "Orgânico"
    elif src == "":         origem = "Direto"
    else:                   origem = "Orgânico"
    return {"source":src,
            "medium":(q.get("utm_medium","")  or "").strip(),
            "campaign":(q.get("utm_campaign","")or "").strip(),
            "content":(q.get("utm_content","") or "").strip(),
            "term":(q.get("utm_term","")    or "").strip(),
            "origem":origem}

def g_on(df, col, name, default=""):
    """Pega a coluna 'Sales History <name>' do df; tolerante a ausência."""
    c = col.get(name)
    return df[c] if c is not None else pd.Series([default]*len(df), index=df.index)

_DF_HOT_ALL = None
def load_hotmart():
    """Lê a aba 'hotmart' (export Hotmart 'Sales History'), filtra produto e classifica origem via SCK."""
    print("  Lendo hotmart...")
    df = pd.read_csv(URL_HOT)
    df.columns = [str(c).strip() for c in df.columns]

    # Mapeia colunas 'Sales History X' → nomes internos
    col = {c.replace("Sales History ","").strip(): c for c in df.columns}

    # ── Status: Hotmart pago = APPROVED ou COMPLETE ──
    st = g_on(df,col,"Transaction Status").astype(str).str.upper().str.strip()
    df = df[st.isin(["APPROVED","COMPLETE","COMPLETED"])].copy()

    # ── Produto: só o(s) configurado(s) ──
    df["Produto"] = g_on(df,col,"Product Name").astype(str)
    df["_email"] = g_on(df,col,"Buyer Email").astype(str).str.strip().str.lower()
    global _DF_HOT_ALL
    _DF_HOT_ALL = df.copy()   # todas as vendas aprovadas (p/ página do produto principal)
    if PRODUTOS_HOTMART and PRODUTOS_HOTMART != ["ALL"]:
        df = df[df["Produto"].isin(PRODUTOS_HOTMART)]
        if len(df)==0:
            print(f"     ⚠ nenhuma venda do produto {PRODUTOS_HOTMART} — confira o nome exato")

    # ── Data ──
    df["date"] = pd.to_datetime(g_on(df,col,"Order Date"), errors="coerce")
    df = df.dropna(subset=["date"])
    df["date"] = df["date"].dt.normalize()

    # ── Valor: fixo por venda (moeda mista na planilha é ignorada) ──
    if VALOR_POR_PRODUTO:
        _fb = float(VALOR_FIXO) if VALOR_FIXO is not None else 0.0
        df["valor"] = df["Produto"].map(lambda p: float(VALOR_POR_PRODUTO.get(str(p).strip(), _fb)))
    elif VALOR_FIXO is not None:
        df["valor"] = float(VALOR_FIXO)
    else:
        df["valor"] = to_num(g_on(df,col,"Price"))

    # ── SCK → labels/UTMs (informativo) ──
    sck = g_on(df,col,"Tracking Source SCK").apply(parse_sck)
    df["src"]      = sck.apply(lambda d:d["source"])
    df["med"]      = sck.apply(lambda d:d["medium"])
    df["camp_sck"] = sck.apply(lambda d:d["campaign"])
    df["u_content"]= sck.apply(lambda d:d["content"])
    df["u_term"]   = sck.apply(lambda d:d["term"])

    # ── ORIGEM pelo código da oferta (fonte da verdade) ──
    pago_set = {c.strip().lower() for c in OFERTAS_PAGO}
    df["oferta"] = g_on(df,col,"Offer Code").astype(str).str.strip().str.lower().replace({"nan":""})
    # País do comprador (coluna "País")
    pais_col = next((c for c in df.columns if _norm_pais(c) in ("pais","country","pais do comprador")), None)
    df["pais"] = df[pais_col].apply(pais_code) if pais_col else ""
    df["origem_sck"] = df["oferta"].isin(pago_set).map({True:"Pago",False:"Orgânico"})
    df["Organico ou Pago"] = df["origem_sck"]
    df["sck_label"] = df.apply(lambda r: (str(r["src"]).upper()+" · "+str(r["med"])) if r["src"] else "Direto / Não rastreado", axis=1)

    # ── Vendas extras manuais (fora do relatório) ──
    val_extra = float(VALOR_FIXO) if VALOR_FIXO is not None else 0.0
    extra_rows = []
    for e in (VENDAS_EXTRAS or []):
        d = pd.to_datetime(e["data"], dayfirst=True, errors="coerce")
        if pd.isna(d):
            print(f"     ⚠ venda extra ignorada (data inválida: {e.get('data')})"); continue
        for _ in range(int(e.get("qtd",0))):
            extra_rows.append({"date":d.normalize(),"valor":val_extra,
                "Produto":(PRODUTOS_HOTMART[0] if PRODUTOS_HOTMART and PRODUTOS_HOTMART!=["ALL"] else "Acceso VIP"),
                "src":"","med":"","camp_sck":"","u_content":"","u_term":"","oferta":"","pais":"",
                "Organico ou Pago":EXTRAS_ORIGEM,"origem_sck":EXTRAS_ORIGEM,"sck_label":EXTRAS_LABEL})
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)
        print(f"     + {len(extra_rows)} vendas extras (fora do relatório) em {', '.join(sorted({e['data'] for e in VENDAS_EXTRAS}))}")

    pago = (df["origem_sck"]=="Pago").sum()
    org  = (df["origem_sck"]=="Orgânico").sum()
    _vinfo = f"US${VALOR_FIXO:g}/venda fixo" if VALOR_FIXO is not None else "valor da planilha"
    print(f"     {len(df)} vendas | {df['valor'].sum():,.2f} ({_vinfo})")
    print(f"     origem por CÓDIGO DE OFERTA → Pago: {pago} | Orgânico: {org}")
    if "oferta" in df.columns:
        print("     por oferta:", dict(df["oferta"].replace({"":"(sem código)"}).value_counts()))
    return df

def hotmart_process(df):
    total=df["valor"].sum(); qtd=len(df)
    ticket=round(float(total/qtd),2) if qtd>0 else 0
    orig_col=next((c for c in df.columns if "organico" in c.lower() or "orgânico" in c.lower() or "pago" in c.lower()), "Organico ou Pago")
    pago=df[df[orig_col].str.contains("Pago",na=False,case=False)]
    org =df[df[orig_col].str.contains("Orgân",na=False,case=False)]
    # Vendas por produto (pago vs orgânico)
    por_produto=[]
    prod_col2=next((c for c in df.columns if "produto" in c.lower()), "Produto")
    orig_col2=next((c for c in df.columns if "organico" in c.lower() or "orgânico" in c.lower() or "pago" in c.lower()), "Organico ou Pago")
    for prod, gdf in df.groupby(prod_col2):
        p_pago=gdf[gdf[orig_col2].str.contains("Pago",na=False,case=False)]
        p_org =gdf[gdf[orig_col2].str.contains("Orgân",na=False,case=False)]
        por_produto.append({
            "produto": str(prod),
            "total_qtd": int(len(gdf)),
            "total_val": round(float(gdf["valor"].sum()),2),
            "pago_qtd":  int(len(p_pago)),
            "pago_val":  round(float(p_pago["valor"].sum()),2),
            "org_qtd":   int(len(p_org)),
            "org_val":   round(float(p_org["valor"].sum()),2),
        })
    por_produto.sort(key=lambda x: x["total_val"], reverse=True)

    # Vendas por SCK (top labels)
    por_sck=[]
    if "sck_label" in df.columns:
        for lab, gdf in df.groupby("sck_label"):
            por_sck.append({"sck":str(lab),"qtd":int(len(gdf)),"val":round(float(gdf["valor"].sum()),2),
                            "origem":str(gdf["origem_sck"].iloc[0]) if "origem_sck" in gdf.columns else ""})
        por_sck.sort(key=lambda x:(-x["qtd"],-x["val"]))
    kpis={"total":round(float(total),2),"qtd":int(qtd),"ticket_medio":ticket,
          "pago_qtd":int(len(pago)),"pago_val":round(float(pago["valor"].sum()),2),
          "org_qtd": int(len(org)), "org_val": round(float(org["valor"].sum()),2),
          "por_produto": por_produto, "por_sck": por_sck}
    agg=df.groupby("date").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index().sort_values("date")
    daily={"days":[r["date"].strftime("%d/%m") for _,r in agg.iterrows()],
           "qtd": [int(r["qtd"]) for _,r in agg.iterrows()],
           "valor":[round(float(r["valor"]),2) for _,r in agg.iterrows()]}
    # Raw por linha — para filtro de período e produto correto no JS
    _pc = prod_col2 if 'prod_col2' in vars() else next((c for c in df.columns if "produto" in c.lower()),"Produto")
    _oc = orig_col2 if 'orig_col2' in vars() else next((c for c in df.columns if "organico" in c.lower() or "orgân" in c.lower() or "pago" in c.lower()),"Organico ou Pago")
    raw = []
    for _, r in df.iterrows():
        d = r["date"]
        if pd.isna(d): continue
        raw.append({
            "d": d.strftime("%d/%m"),
            "p": str(r[_pc]),
            "v": round(float(r["valor"]),2),
            "t": str(r[_oc]),
            "sck": str(r["sck_label"]) if "sck_label" in df.columns else "",
            "org": str(r["origem_sck"]) if "origem_sck" in df.columns else "",
            "us": str(r.get("src","")),
            "um": str(r.get("med","")),
            "uc": str(r.get("camp_sck","")),
            "uco": str(r.get("u_content","")),
            "ut": str(r.get("u_term","")),
            "of": str(r.get("oferta","")),
            "ps": str(r.get("pais",""))
        })
    return kpis, daily, raw

# ══ META ADS ══════════════════════════════════════════
def load_meta():
    print("  Lendo meta-ads...")
    df=pd.read_csv(URL_META)
    df=df.rename(columns={"Date":"date","Campaign Name":"campaign","Adset Name":"adset",
        "Ad Name":"ad","Thumbnail URL":"thumb","Status":"status","Spend (Cost, Amount Spent)":"spend",
        "Impressions":"impressions","Action Link Clicks":"link_clicks",
        "Action Landing Page View":"page_view","Action Omni Initiated Checkout":"init_checkout",
        "Action Omni Purchase":"purchase","Action Value Omni Purchase":"revenue_meta"})
    df["date"]=pd.to_datetime(df["date"],errors="coerce")
    for c in ["spend","impressions","link_clicks","page_view","init_checkout","purchase","revenue_meta"]:
        if c in df.columns: df[c]=to_num(df[c])
    if "status" not in df.columns: df["status"]=""
    df["is_lct"]=df["campaign"].str.contains(LANCAMENTO_COD,na=False,case=False) if LANCAMENTO_COD else True
    df=df.dropna(subset=["date"])
    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    return df

def calc_kpis(p, ticket):
    sp=float(p["spend"].sum()); imp=float(p["impressions"].sum())
    lc=float(p["link_clicks"].sum()); pv=float(p["page_view"].sum())
    ic=float(p["init_checkout"].sum()); pur=float(p["purchase"].sum())
    rev=pur*ticket  # receita correta = purchase × ticket_medio
    return {"spend":round(sp,2),"impressions":int(imp),"link_clicks":int(lc),
            "page_view":int(pv),"init_checkout":int(ic),"purchase":int(pur),
            "revenue":round(rev,2),
            "ctr":   round(lc/imp*100,2) if imp>0 else None,
            "connect_rate":round(pv/lc*100,2) if lc>0 else None,
            "tx_ic": round(ic/pv*100,2) if pv>0 else None,
            "tx_checkout":round(pur/ic*100,2) if ic>0 else None,
            "tx_conv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":   round(sp/pur,2) if pur>0 else None,
            "roas":  round(rev/sp,2) if sp>0 else None,
            "cpm":   round(sp/imp*1000,2) if imp>0 else None}

def meta_kpis(df, ticket):
    return {"lct":calc_kpis(df[df["is_lct"]],ticket),"all":calc_kpis(df,ticket)}

def build_daily(p, ticket):
    agg=p.groupby("date").agg(spend=("spend","sum"),impressions=("impressions","sum"),
        link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
        init_checkout=("init_checkout","sum"),purchase=("purchase","sum")
    ).reset_index().sort_values("date")
    out={k:[] for k in ["days","spend","impressions","link_clicks","page_view",
                         "init_checkout","purchase","revenue","ctr","connect_rate",
                         "tx_ic","tx_checkout","tx_conv","cpa","roas","cpm"]}
    for _,r in agg.iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
        rev=pur*ticket
        out["days"].append(r["date"].strftime("%d/%m"))
        out["spend"].append(round(sp,2)); out["impressions"].append(int(imp))
        out["link_clicks"].append(int(lc)); out["page_view"].append(int(pv))
        out["init_checkout"].append(int(ic)); out["purchase"].append(int(pur))
        out["revenue"].append(round(rev,2))
        out["ctr"].append(round(lc/imp*100,2) if imp>0 else None)
        out["connect_rate"].append(round(pv/lc*100,2) if lc>0 else None)
        out["tx_ic"].append(round(ic/pv*100,2) if pv>0 else None)
        out["tx_checkout"].append(round(pur/ic*100,2) if ic>0 else None)
        out["tx_conv"].append(round(pur/pv*100,2) if pv>0 else None)
        out["cpa"].append(round(sp/pur,2) if pur>0 else None)
        out["roas"].append(round(rev/sp,2) if sp>0 else None)
        out["cpm"].append(round(sp/imp*1000,2) if imp>0 else None)
    return out

def meta_daily(df, ticket):
    return {"lct":build_daily(df[df["is_lct"]],ticket),"all":build_daily(df,ticket)}

def meta_daily_camps(df, ticket):
    """Daily por campanha para filtro nas métricas diárias"""
    result={"lct":{},"all":{}}
    for key,subset in [("lct",df[df["is_lct"]]),("all",df)]:
        for camp in subset["campaign"].unique():
            p=subset[subset["campaign"]==camp]
            result[key][camp]=build_daily(p,ticket)
    return result

def meta_raw(df, ticket):
    """Raw agregado por dia+campanha+adset — para filtro de datas livres nas tabelas"""
    rows=[]
    agg=df.groupby(["date","campaign","adset","ad","is_lct"]).agg(
        spend=("spend","sum"), purchase=("purchase","sum"),
        impressions=("impressions","sum"), link_clicks=("link_clicks","sum"),
        page_view=("page_view","sum"), init_checkout=("init_checkout","sum"),
        revenue_meta=("revenue_meta","sum")
    ).reset_index()
    for _,r in agg.iterrows():
        sp=float(r["spend"]); pur=int(r["purchase"]); imp=int(r["impressions"])
        lc=int(r["link_clicks"]); pv=int(r["page_view"]); ic=int(r["init_checkout"])
        rev=pur*ticket  # SEMPRE compras × valor fixo
        rows.append({
            "d": r["date"].strftime("%d/%m"),
            "c": str(r["campaign"]),
            "a": str(r["adset"]),
            "an": str(r["ad"]),
            "lct": bool(r["is_lct"]),
            "sp": round(sp,2), "pur": pur, "imp": imp,
            "lc": lc, "pv": pv, "ic": ic, "rev": round(rev,2)
        })
    return rows

def build_rows(agg, col, ticket):
    rows=[]
    for _,r in agg.sort_values("purchase",ascending=False).iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
        rev=pur*ticket  # SEMPRE compras × valor fixo ($10) — ignora Action Value do Meta
        rows.append({"n":str(r[col]),"st":str(r.get("status","") or ""),"spend":round(sp,2),"imp":int(imp),"lc":int(lc),
            "pv":int(pv),"ic":int(ic),"pur":int(pur),"rev":round(rev,2),
            "ctr":round(lc/imp*100,2) if imp>0 else None,
            "cr": round(pv/lc*100,2)  if lc>0 else None,
            "tx_ic":round(ic/pv*100,2) if pv>0 else None,
            "tx_ck":round(pur/ic*100,2) if ic>0 else None,
            "tx_cv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":round(sp/pur,2) if pur>0 else None,
            "roas":round(rev/sp,2) if sp>0 else None,
            "cpm":round(sp/imp*1000,2) if imp>0 else None})
    return rows

def meta_tables_period(df, p, img_dir, ticket):
    """Calcula tabelas para um subset p do df"""
    def ag(sub,col):
        return sub.sort_values("date").groupby(col).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"),purchase=("purchase","sum"),
            revenue_meta=("revenue_meta","sum"),status=("status","last")).reset_index()
    def make(sub,col): return build_rows(ag(sub,col),col,ticket)
    def make_adsets(sub):
        agg2=sub.sort_values("date").groupby(["campaign","adset"]).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"),purchase=("purchase","sum"),
            revenue_meta=("revenue_meta","sum"),status=("status","last")).reset_index()
        rows=[]
        for _,r in agg2.sort_values("purchase",ascending=False).iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
            pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
            rev=pur*ticket  # SEMPRE compras × valor fixo
            rows.append({"n":str(r["adset"]),"camp":str(r["campaign"]),"st":str(r.get("status","") or ""),"spend":round(sp,2),
                "imp":int(imp),"lc":int(lc),"pv":int(pv),"ic":int(ic),"pur":int(pur),"rev":round(rev,2),
                "ctr":round(lc/imp*100,2) if imp>0 else None,
                "cr": round(pv/lc*100,2)  if lc>0 else None,
                "tx_ic":round(ic/pv*100,2) if pv>0 else None,
                "tx_ck":round(pur/ic*100,2) if ic>0 else None,
                "tx_cv":round(pur/pv*100,2) if pv>0 else None,
                "cpa":round(sp/pur,2) if pur>0 else None,
                "roas":round(rev/sp,2) if sp>0 else None,
                "cpm":round(sp/imp*1000,2) if imp>0 else None})
        return rows
    # Mapa de thumb: ad+adset+camp → url (do df completo, não só do período)
    df_full_thumb=df[df["thumb"].notna()&(df["thumb"].astype(str)!="nan")]
    thumb_map={}
    for _,r in df_full_thumb.iterrows():
        k=(str(r["ad"]),str(r["adset"]),str(r["campaign"]))
        if k not in thumb_map:
            thumb_map[k]=download_thumb(str(r["thumb"]),img_dir)

    def make_ads(sub):
        # Agregar métricas do período, buscar thumb do mapa completo
        agg=sub.groupby(["ad","adset","campaign"]).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False)
        if agg.empty: return []
        ads=[]
        for _,r in agg.iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"]); pur=float(r["purchase"])
            k=(str(r["ad"]),str(r["adset"]),str(r["campaign"]))
            ads.append({"n":str(r["ad"]),"adset":str(r["adset"]),"camp":str(r["campaign"]),
                "thumb":thumb_map.get(k,""),
                "spend":round(sp,2),"pur":int(pur),"imp":int(imp),"lc":int(lc),
                "ctr":round(lc/imp*100,2) if imp>0 else None,
                "cpa":round(sp/pur,2) if pur>0 else None})
        return ads
    return {"camps":make(p,"campaign"),"adsets":make_adsets(p),"ads":make_ads(p)}

def meta_tables(df, img_dir, ticket):
    """Exporta tabelas por período: 1d,7d,14d,30d,all — baseado na data de geração"""
    from datetime import timezone, timedelta
    hoje=pd.Timestamp(date.today())  # data de geração como referência
    result={"lct":{},"all":{}}
    periods={"1":1,"7":7,"14":14,"30":30,"all":0}
    for key,subset in [("lct",df[df["is_lct"]]),("all",df)]:
        for pname,n in periods.items():
            p=subset[subset["date"]>=hoje-pd.Timedelta(days=n-1)] if n>0 else subset
            result[key][pname]=meta_tables_period(df,p,img_dir,ticket)
            print(f"     [{key}][{pname}]: {len(result[key][pname]['camps'])} camps")
    return result

def meta_breakdowns(df):
    print("  Lendo breakdowns...")
    hoje_bd=pd.Timestamp(date.today())  # referência = data de geração
    last=hoje_bd  # usar hoje como limite superior
    AGE_ORDER=["18-24","25-34","35-44","45-54","55-64","65+"]
    def seg(agg,dim):
        agg=agg[agg["spend"]>0].copy()
        agg["cpa"]=(agg["spend"]/agg["purchase"]).where(agg["purchase"]>0).round(2)
        return [{"n":str(r[dim]),"spend":round(float(r["spend"]),2),"pur":int(r["purchase"]),"cpa":safe(r["cpa"])} for _,r in agg.iterrows()]
    try:
        df_ga=pd.read_csv(URL_GA)
        df_ga.columns=[str(c).strip() for c in df_ga.columns]
        df_ga["date"]=pd.to_datetime(df_ga["Date"],errors="coerce")
        df_ga["spend"]=to_num(df_ga["Spend (Cost, Amount Spent)"])
        df_ga["purchase"]=to_num(df_ga["Action Omni Purchase"])
        df_ga["age"]=df_ga["Age (Breakdown)"].astype(str)
        df_ga["gender"]=df_ga["Gender (Breakdown)"].astype(str)
        df_ga=df_ga.dropna(subset=["date"])
    except Exception as e: print(f"  Aviso GA: {e}"); df_ga=pd.DataFrame()
    try:
        df_pt=pd.read_csv(URL_PT)
        df_pt.columns=[str(c).strip() for c in df_pt.columns]
        df_pt["date"]=pd.to_datetime(df_pt["Date"],errors="coerce")
        df_pt["spend"]=to_num(df_pt["Spend (Cost, Amount Spent)"])
        df_pt["purchase"]=to_num(df_pt["Action Omni Purchase"])
        df_pt["platform"]=df_pt["Platform Position (Breakdown)"].astype(str)
        df_pt=df_pt.dropna(subset=["date"])
    except Exception as e: print(f"  Aviso PT: {e}"); df_pt=pd.DataFrame()

    result={}
    for pname,n in [("1",1),("7",7),("14",14),("30",30),("all",0)]:
        if n>0:
            start=hoje_bd-pd.Timedelta(days=n-1)
            pga=df_ga[(df_ga["date"]>=start)&(df_ga["date"]<=hoje_bd)] if len(df_ga)>0 else df_ga
            ppt=df_pt[(df_pt["date"]>=start)&(df_pt["date"]<=hoje_bd)] if len(df_pt)>0 else df_pt
        else:
            pga=df_ga; ppt=df_pt
        if len(pga)>0:
            ag_age=pga[pga["age"].isin(AGE_ORDER)].groupby("age").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index()
            ag_age["_o"]=ag_age["age"].apply(lambda x:AGE_ORDER.index(x) if x in AGE_ORDER else 99)
            age_d=seg(ag_age.sort_values("_o"),"age")
            ag_gen=pga[pga["gender"].isin(["female","male"])].groupby("gender").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False)
            gen_d=seg(ag_gen,"gender")
        else: age_d=[]; gen_d=[]
        if len(ppt)>0:
            ag_pt=ppt.groupby("platform").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False).head(8)
            plat_d=seg(ag_pt,"platform")
        else: plat_d=[]
        result[pname]={"age":age_d,"gender":gen_d,"platform":plat_d}
    # Também exportar raw por dia para filtro de datas livres e por campanha
    # (campanha vira índice 'ci' no array _camps para controlar tamanho do arquivo)
    camps_bd=[]
    def camp_idx(name):
        name=str(name)
        if name not in camps_bd: camps_bd.append(name)
        return camps_bd.index(name)
    def find_camp_col(df):
        for c in df.columns:
            cl=str(c).strip().lower()
            if cl in ("campaign name","campaign","campanha","nome da campanha"): return c
        return None
    cga=find_camp_col(df_ga) if len(df_ga)>0 else None
    cpt=find_camp_col(df_pt) if len(df_pt)>0 else None
    if cga: df_ga["campaign"]=df_ga[cga].astype(str)
    else:   print("  ⚠ breakdown gender/age SEM coluna de campanha — filtro por campanha ficará indisponível nessa aba")
    if cpt: df_pt["campaign"]=df_pt[cpt].astype(str)
    else:   print("  ⚠ breakdown platform SEM coluna de campanha — filtro por campanha ficará indisponível nessa aba")
    raw_ga=[]
    if len(df_ga)>0:
        for _,r in df_ga.iterrows():
            if pd.isna(r['date']): continue
            row={'d':r['date'].strftime('%d/%m'),'age':str(r['age']),'gen':str(r['gender']),
                 'sp':round(float(r['spend']),2),'pur':int(r['purchase'])}
            if "campaign" in df_ga.columns: row['ci']=camp_idx(r['campaign'])
            raw_ga.append(row)
    raw_pt=[]
    if len(df_pt)>0:
        for _,r in df_pt.iterrows():
            if pd.isna(r['date']): continue
            row={'d':r['date'].strftime('%d/%m'),'plat':str(r['platform']),
                 'sp':round(float(r['spend']),2),'pur':int(r['purchase'])}
            if "campaign" in df_pt.columns: row['ci']=camp_idx(r['campaign'])
            raw_pt.append(row)
    result['_raw_ga']=raw_ga
    result['_raw_pt']=raw_pt
    result['_camps']=camps_bd
    return result

# ══ Classificação de origem compartilhada (Cert + Upsells) ══
_JORN_CACHE = None
def _lado_txt(t):
    for l in (LADOS_COMPARATIVO or []):
        if any(tk.upper() in t for tk in l["tokens"]): return l["nome"]
    return ""

_PAGO_SRC = {"ig","fb","an"}
def _class_sck(txt):
    """→ (origem, lado, utms{us,um,uc,uco,ut}) a partir de um SCK/base de origem."""
    VAZIO = {"us":"","um":"","uc":"","uco":"","ut":""}
    t = str(txt or "").strip()
    if not t or t.lower()=="nan": return "", "", dict(VAZIO)
    lado = _lado_txt(t.upper())
    if "=" not in t and "." in t and not t.lower().startswith("meta-ads"):
        # Formato por PONTOS: "fonte.conjunto.campanha" ou "criativo.conjunto.campanha"
        parts = [p.strip() for p in t.split(".")]
        psrc  = (parts[0] or "").lower()
        pmed  = parts[1] if len(parts) >= 2 else ""
        pcamp = ".".join(parts[2:]) if len(parts) >= 3 else ""
        u = {"us":parts[0],"um":pmed,"uc":pcamp,"uco":"","ut":pcamp}
        if psrc in _PAGO_SRC: return "Pago", lado, u
        if LANCAMENTO_COD and LANCAMENTO_COD.lower() in pcamp.lower():
            return "Pago", lado, u      # 1º segmento é o criativo; campanha tem a nomenclatura do lançamento
        if psrc == "email": return "Orgânico", lado, u
        return "", lado, u              # indefinido → cascata decide (jornada / fallback)
    if t.lower().startswith("meta-ads"):    # formato "meta-ads.Funil.Campanha"
        parts = [p.strip() for p in t.split(".") if p.strip()]
        u = {"us":"meta-ads","um":parts[1] if len(parts)>=3 else "",
             "uc":parts[-1] if len(parts)>=2 else "","uco":"","ut":""}
        return "Pago", lado, u
    q = dict(_up.parse_qsl(_html.unescape(t)))
    if q:
        u = {"us":(q.get("utm_source") or "").strip(),
             "um":(q.get("utm_medium") or "").strip(),
             "uc":(q.get("utm_campaign") or "").strip(),
             "uco":(q.get("utm_content") or "").strip(),
             "ut":(q.get("utm_term") or "").strip()}
        srcv = u["us"].lower()
        if srcv in _PAGO_SRC or srcv.startswith("{{"): return "Pago", lado, u
        return "Orgânico", lado, u
    u = dict(VAZIO); u["uc"] = t[:60]
    return "Orgânico", lado, u

def _jornada_acceso():
    """Índice por e-mail das compras do Acceso: {email: {pago:bool, lado:str}} (cacheado)."""
    global _JORN_CACHE
    if _JORN_CACHE is not None: return _JORN_CACHE
    jorn = {}
    if _DF_HOT_ALL is not None:
        df = _DF_HOT_ALL
        colA = {c.replace("Sales History ","").strip(): c for c in df.columns}
        ev = df[df["Produto"].isin(PRODUTOS_HOTMART)].copy()
        ev["oferta"] = g_on(ev,colA,"Offer Code").astype(str).str.strip().str.lower()
        ev["_sck"]  = g_on(ev,colA,"Tracking Source SCK").astype(str)
        pago_set = {o.lower() for o in OFERTAS_PAGO}
        for _,r in ev.iterrows():
            em = r["_email"]
            if not em or em=="nan": continue
            j = jorn.setdefault(em, {"pago":False,"lado":""})
            if r["oferta"] in pago_set: j["pago"] = True
            if not j["lado"]:
                d = parse_sck(r["_sck"])
                j["lado"] = _lado_txt(" ".join(str(v) for v in d.values()).upper())
    _JORN_CACHE = jorn
    return jorn

# ══ PRODUTO PRINCIPAL (Certificación) — atribuição por jornada ══
def load_cert():
    """Vendas do produto principal. Origem/destino: 1º pela coluna de origem preenchida na aba
    dedicada 'hotmart-CertificacionELF' (UTMs da captura); 2º herdada da compra do Acceso VIP
    via e-mail. Exporta apenas agregados — e-mails nunca vão para o HTML."""
    if not PRODUTO_CERT or _DF_HOT_ALL is None: return None, []
    # ── fonte: aba dedicada; fallback aba hotmart ──
    try:
        cert = pd.read_csv(URL_CERT)
        cert.columns = [str(c).strip() for c in cert.columns]
        print(f"  Cert: aba dedicada ({len(cert)} linhas)")
    except Exception as e:
        print(f"  Cert: aba dedicada indisponível — usando aba hotmart")
        cert = _DF_HOT_ALL.copy()
    col = {c.replace("Sales History ","").strip(): c for c in cert.columns}
    st = g_on(cert,col,"Transaction Status").astype(str).str.upper().str.strip()
    cert = cert[st.isin(["APPROVED","COMPLETE","COMPLETED"])].copy()
    cert["Produto"] = g_on(cert,col,"Product Name").astype(str)
    cert = cert[cert["Produto"]==PRODUTO_CERT["nome"]]
    if len(cert)==0:
        print(f"  Cert: nenhuma venda de {PRODUTO_CERT['nome']}"); return None, []
    cert["date"] = pd.to_datetime(g_on(cert,col,"Order Date"), errors="coerce")
    cert = cert.dropna(subset=["date"])
    if CERT_INICIO:
        ini = pd.to_datetime(CERT_INICIO, dayfirst=True)
        antes = int((cert["date"] < ini).sum())
        cert = cert[cert["date"] >= ini]
        if antes: print(f"  Cert: {antes} venda(s) de teste antes de {CERT_INICIO} ignorada(s)")
    cert["_email"] = g_on(cert,col,"Buyer Email").astype(str).str.strip().str.lower()
    pais_col = next((c for c in cert.columns if _norm_pais(c) in ("pais","country","pais do comprador")), None)
    cert["ps"] = cert[pais_col].apply(pais_code) if pais_col else ""
    cert["of"] = g_on(cert,col,"Offer Code").astype(str).str.strip().str.lower()
    # ── colunas do cruzamento manual na aba (cliente): código de origem da captação + Pago/Org/VSL/Não encontrado ──
    col_cod = next((c for c in cert.columns if "code origem" in c.lower()), None)
    col_o4  = next((c for c in cert.columns if "origem paga" in c.lower()), None)
    def _map_o4(v):
        t = str(v or "").strip().lower()
        if not t or t=="nan": return "Não encontrado"
        if t.startswith("pago"): return "Pago"
        if t.startswith("org"):  return "Orgânico"
        if "vsl" in t:           return "VSL"
        return "Não encontrado"
    cert["cod"] = (cert[col_cod].apply(lambda v: "" if str(v).strip().lower() in ("","nan","none") else str(v).strip().lower())
                   if col_cod else "")
    cert["o4"]  = (cert[col_o4].apply(_map_o4) if col_o4 else "Não encontrado")
    # coluna de origem manual = última coluna "...Tracking Source SCK*" (a duplicada vira SCK.1)
    sck_cols = [c for c in cert.columns if c.startswith("Sales History Tracking Source SCK")]
    org_col = sck_cols[-1] if sck_cols else None

    # ── jornada via e-mail (compras do Acceso) — índice compartilhado ──
    jorn = _jornada_acceso()

    rows=[]; n_base=n_jorn=n_sem=0; n_pago=n_org=0
    for _,r in cert.iterrows():
        org,lado,utms = _class_sck(r[org_col]) if org_col else ("","",{"us":"","um":"","uc":"","uco":"","ut":""})
        if org:
            n_base+=1
        else:
            j = jorn.get(r["_email"])
            if j:
                org = "Pago" if j["pago"] else "Orgânico"
                lado = lado or j["lado"]; n_jorn+=1
            else:
                n_sem+=1
        if org=="Pago": n_pago+=1
        elif org=="Orgânico": n_org+=1
        rows.append({"d":r["date"].strftime("%d/%m"),"ps":str(r["ps"] or ""),
                     "of":str(r["of"]),"org":org,"lado":lado,
                     "cod":str(r["cod"] or ""),"o4":str(r["o4"]), **utms})
    info={"nome":PRODUTO_CERT["nome"],"ap":PRODUTO_CERT["apelido"],"valor":float(PRODUTO_CERT["valor"])}
    cob=(n_base+n_jorn)/len(rows)*100 if rows else 0
    info["cobertura"]=round(cob)
    print(f"  Cert: {len(rows)} vendas | Pago {n_pago} · Orgânico {n_org} · sem origem {n_sem}")
    from collections import Counter as _C
    _d4=_C(r["o4"] for r in rows)
    print(f"        cruzamento da aba: " + " · ".join(f"{k} {v}" for k,v in _d4.most_common()))
    print(f"        origem: {n_base} pela base da aba · {n_jorn} pela jornada (e-mail) · cobertura {cob:.0f}%")
    return info, rows

# ══ UPSELLS (por código de oferta) ═══════════════════════
def load_upsells():
    if not UPSELLS or _DF_HOT_ALL is None: return [], []
    df=_DF_HOT_ALL
    col={c.replace("Sales History ","").strip(): c for c in df.columns}
    df=df.copy()
    df["of2"]=g_on(df,col,"Offer Code").astype(str).str.strip().str.lower()
    df["date"]=pd.to_datetime(g_on(df,col,"Order Date"),errors="coerce")
    df["_sck2"]=g_on(df,col,"Tracking Source SCK").astype(str)
    jorn=_jornada_acceso()
    pais_col = next((c for c in df.columns if _norm_pais(c) in ("pais","country","pais do comprador")), None)
    info=[]; rows=[]
    for u in UPSELLS:
        d=df[(df["of2"]==u["oferta"].lower())].dropna(subset=["date"])
        info.append({"nome":u["nome"],"valor":float(u["valor"]),"oferta":u["oferta"]})
        for _,r in d.iterrows():
            org,_,_ = _class_sck(r["_sck2"])          # 1º: SCK da própria venda
            if not org:
                j = jorn.get(r["_email"])              # 2º: jornada (compra do Acceso)
                if j: org = "Pago" if j["pago"] else "Orgânico"
            if not org: org = "Pago"                   # 3º: fallback — considerar tráfego pago
            rows.append({"d":r["date"].strftime("%d/%m"),"p":u["nome"],"v":float(u["valor"]),"org":org,
                         "ps": (pais_code(r[pais_col]) if pais_col is not None else "")})
    for u in UPSELLS:
        rp=[r for r in rows if r["p"]==u["nome"]]
        print(f"  Upsell {u['nome']}: {len(rp)} | Pago {sum(1 for r in rp if r['org']=='Pago')} · Orgânico {sum(1 for r in rp if r['org']=='Orgânico')}")
    return info, rows

# ══ CRIATIVOS × LINKS (aba opcional) ═════════════════════
def load_criativos_links():
    """Links dos criativos: começa pelos FIXOS embutidos no py; a aba
    'Criativos_x_Links' (colA nome, colB link), se existir, complementa/sobrepõe."""
    links = { str(k).strip().lower(): str(v).strip()
              for k, v in (CRIATIVOS_LINKS_FIXOS or {}).items()
              if str(v).strip().lower().startswith("http") }
    n_fixos = len(links)
    n_aba = 0
    try:
        df = pd.read_csv(URL_CRIAT, header=None, dtype=str)
        for _, r in df.iterrows():
            nome = str(r[0]).strip() if pd.notna(r[0]) else ""
            url  = str(r[1]).strip() if len(r) > 1 and pd.notna(r[1]) else ""
            if not nome or not url.lower().startswith("http"): continue
            links[nome.lower()] = url; n_aba += 1
        if n_aba == 0:
            print("  Criativos×Links: aba lida mas SEM links válidos (coluna B precisa ser URL em texto puro)")
    except Exception:
        print("  Criativos×Links: aba indisponível — usando só os fixos do py")
    print(f"  Criativos×Links: {n_fixos} fixos no py + {n_aba} da aba = {len(links)} no total")
    return links or None
# ══ REGIÃO (spend por país) ═══════════════════════════
def load_regiao():
    """Lê breakdown-regiao (país 2L) e exporta raw diário {d, ps, lct, sp, pur}."""
    print("  Lendo breakdown-regiao...")
    try:
        df=pd.read_csv(URL_RG)
        df.columns=[str(c).strip() for c in df.columns]
        df["date"]=pd.to_datetime(df["Date"],errors="coerce")
        df=df.dropna(subset=["date"])
        df["ps"]=df["Country (Breakdown)"].astype(str).str.strip().str.upper()
        df["sp"]=to_num(df["Spend (Cost, Amount Spent)"])
        df["pur"]=to_num(df.get("Action Omni Purchase",0))
        camp_col=next((c for c in df.columns if "campaign" in c.lower()),None)
        df["is_lct"]=df[camp_col].astype(str).str.contains(LANCAMENTO_COD,na=False,case=False) if (camp_col and LANCAMENTO_COD) else True
        agg=df.groupby([df["date"].dt.normalize(),"ps","is_lct"]).agg(sp=("sp","sum"),pur=("pur","sum")).reset_index()
        rows=[{"d":r["date"].strftime("%d/%m"),"ps":str(r["ps"]),"lct":bool(r["is_lct"]),
               "sp":round(float(r["sp"]),2),"pur":int(r["pur"])} for _,r in agg.iterrows()]
        print(f"     {len(rows)} linhas | países: {sorted(set(r['ps'] for r in rows if r['lct']))}")
        return rows
    except Exception as e:
        print(f"  Aviso regiao: {e}"); return []

# ══ PESQUISA ══════════════════════════════════════════
def load_pesquisa():
    print("  Lendo pesquisa..."); return pd.read_csv(URL_PES)

def pesquisa_process(df, hot_qtd):
    # Perguntas dinâmicas: todas as colunas que NÃO são UTM nem de controle
    UTM_COLS=["utm_source","utm_medium","utm_campaign","utm_content"]
    SKIP_COLS=set(UTM_COLS+["Carimbo de data/hora","Timestamp","Email","email",
                             "Nome","nome","ID","id","Unnamed: 0"])
    # Considerar como pergunta qualquer coluna com texto longo (provável questão)
    def _pergunta_valida(c):
        s=df[c]; nn=s.notna().sum(); nu=s.nunique()
        if nu>50: return False                        # muitos valores distintos → não é múltipla escolha
        if nn>=5 and nu/max(nn,1)>=0.8: return False  # respostas quase todas diferentes (nome, email, whatsapp...) → lixo visual
        vals=s.dropna().astype(str)
        if nn>0:
            # padrão e-mail ou telefone na maioria das respostas → dado pessoal, não pergunta
            if (vals.str.contains(r"@.+\.",regex=True).mean()>0.5): return False
            if (vals.str.replace(r"[\s\-\(\)\+]","",regex=True).str.fullmatch(r"\d{8,14}").mean()>0.5): return False
        return True
    PERGUNTAS=[c for c in df.columns
               if c not in SKIP_COLS
               and not c.lower().startswith("unnamed")
               and pd.api.types.is_string_dtype(df[c])  # aceita str e object
               and _pergunta_valida(c)]
    graficos=[]
    for p in PERGUNTAS:
        if p not in df.columns: continue
        vc=df[p].value_counts(); total=vc.sum()
        graficos.append({"pergunta":p,"opcoes":[{"label":str(k),"qtd":int(v),"pct":round(v/total*100,1)} for k,v in vc.items()]})
    filtros={}
    for col in UTM_COLS:
        if col in df.columns:
            filtros[col]=sorted([v for v in df[col].dropna().unique().tolist() if v and str(v)!="nan"])
    rows=[]
    for _,r in df.iterrows():
        row={}
        for p in PERGUNTAS: row[p]=str(r[p]) if p in df.columns and pd.notna(r.get(p)) else None
        for col in UTM_COLS: row[col]=str(r[col]) if col in df.columns and pd.notna(r.get(col)) else None
        rows.append(row)
    return {"total":len(df),"hot_qtd":int(hot_qtd),"graficos":graficos,"filtros":filtros,"rows":rows,"perguntas":PERGUNTAS}

# ══ INJEÇÃO ════════════════════════════════════════════
def replace_js_const(html, name, value):
    pattern=rf"const {name}\s*=\s*(?:null|true|false|-?\d[\d\.]*|'[^']*'|\"[^\"]*\"|\{{[\s\S]*?\}}|\[[\s\S]*?\])\s*;"
    replacement=f"const {name} = {json.dumps(value,ensure_ascii=False)};"
    # Usar lambda para evitar interpretação de \ no replacement
    found=[0]
    def do_replace(m):
        found[0]+=1
        return replacement
    new_html=re.sub(pattern,do_replace,html,count=1)
    if not found[0]: print(f"  AVISO: não encontrou const {name}")
    return new_html

def inject_all(tpl, meta_k, meta_d, meta_dc, meta_raw_c, meta_t, meta_bd, hot_k, hot_d, hot_raw, regiao_raw, cert_info, cert_raw, ups_info, ups_raw, criat_links, pes, ticket):
    html=Path(tpl).read_text(encoding="utf-8")
    html=replace_js_const(html,"META_KPIS",    meta_k)
    html=replace_js_const(html,"META_DAILY",       meta_d)
    html=replace_js_const(html,"META_DAILY_CAMPS", meta_dc)
    html=replace_js_const(html,"META_RAW_CAMP",    meta_raw_c)
    html=replace_js_const(html,"META_TABLES",      meta_t)
    html=replace_js_const(html,"META_BD",      meta_bd)
    html=replace_js_const(html,"HOT_KPIS",     hot_k)
    html=replace_js_const(html,"HOT_DAILY",    hot_d)
    html=replace_js_const(html,"HOT_RAW",      hot_raw)
    html=replace_js_const(html,"REGIAO_RAW",   regiao_raw)
    html=replace_js_const(html,"LADOS",        LADOS_COMPARATIVO if LADOS_COMPARATIVO else None)
    html=replace_js_const(html,"CERT",         cert_info)
    html=replace_js_const(html,"CERT_RAW",     cert_raw)
    html=replace_js_const(html,"UPSELLS_INFO", ups_info if ups_info else None)
    html=replace_js_const(html,"PRODUTO_CAPTACAO", PRODUTOS_HOTMART[0] if PRODUTOS_HOTMART and PRODUTOS_HOTMART!=["ALL"] else None)
    html=replace_js_const(html,"CRIAT_LINKS",  criat_links)
    html=replace_js_const(html,"META_INVEST",  META_INVEST)
    html=replace_js_const(html,"UPSELLS_RAW",  ups_raw)
    html=replace_js_const(html,"PESQUISA", pes if USAR_PESQUISA else False)
    html=replace_js_const(html,"TICKET_MEDIO", ticket)
    # Data de geração em Brasília (UTC-3) para o filtro de período correto
    from datetime import timezone, timedelta
    brt = timezone(timedelta(hours=-3))
    hoje_brt = date.today()  # data local do servidor (GitHub Actions = UTC, mas usamos a data atual)
    html=replace_js_const(html,"DATA_GERACAO", hoje_brt.strftime("%Y-%m-%d"))
    for k,v in [("LANCAMENTO_COD",f"'{LANCAMENTO_COD}'"),("NOME_CLIENTE",f"'{NOME_CLIENTE}'"),
                ("USAR_ORIGEM","true" if USAR_ORIGEM else "false"),
                ("USAR_LOGO","true" if USAR_LOGO else "false"),
                ("USAR_RODAPE","true" if USAR_RODAPE else "false"),
                ("MOEDA",f"'{MOEDA_SIMBOLO}'"),
                ("FUNIL_TITULO",f"'{FUNIL_TITULO}'"),
                ("FUNIL_COMPRAS_PAGO","true" if FUNIL_COMPRAS_PAGO else "false"),
                ("FONTE_LABEL",f"'{FONTE_LABEL}'"),
                ("NOTA_RECEITA",f"'{NOTA_RECEITA}'"),
                ("USAR_IDIOMAS","true" if USAR_IDIOMAS else "false"),
                ("LANG_DEFAULT",f"'{IDIOMA_PADRAO}'"),
                ("LOGO_LETRA",f"'{LOGO_LETRA}'"),("COR_ACENTO",f"'{COR_ACENTO}'"),
                ("CPA_BOM",str(CPA_BOM)),("CPA_MEDIO",str(CPA_MEDIO)),
                ("ROAS_BOM",str(ROAS_BOM)),("ROAS_MEDIO",str(ROAS_MEDIO)),
                ("CTR_BOM",str(CTR_BOM)),("CTR_MEDIO",str(CTR_MEDIO)),
                ("CR_BOM",str(CR_BOM)),("CR_MEDIO",str(CR_MEDIO)),
                ("TX_IC_BOM",str(TX_IC_BOM)),("TX_IC_MEDIO",str(TX_IC_MEDIO)),
                ("TX_CK_BOM",str(TX_CK_BOM)),("TX_CK_MEDIO",str(TX_CK_MEDIO)),
                ("TX_CONV_BOM",str(TX_CONV_BOM)),("TX_CONV_MEDIO",str(TX_CONV_MEDIO)),
                ("CPM_BOM",str(CPM_BOM)),("CPM_MEDIO",str(CPM_MEDIO))]:
        html=re.sub(rf"const {k}\s*=\s*[^;]+;",f"const {k}={v};",html,count=1)
    html=re.sub(r"\d{2}/\d{2}/\d{4} · via planilha",date.today().strftime("%d/%m/%Y")+" · via planilha",html)
    return html

# ══ MAIN ═══════════════════════════════════════════════
def main():
    print("="*60)
    print(f"Dashboard Lançamento — {NOME_CLIENTE} / {LANCAMENTO_COD or 'Todos'}")
    print("="*60)
    img_dir=Path("imgs"); img_dir.mkdir(exist_ok=True)

    print("\n[HOTMART]")
    df_hot=load_hotmart()
    hot_k,hot_d,h_raw=hotmart_process(df_hot)
    ticket=hot_k["ticket_medio"]
    print(f"  ✓ {hot_k['qtd']} vendas | R$ {hot_k['total']:,.2f} | ticket R$ {ticket:.2f}")

    print("\n[META ADS]")
    df_meta=load_meta()
    m_k=meta_kpis(df_meta,ticket)
    m_d=meta_daily(df_meta,ticket)
    m_dc=meta_daily_camps(df_meta,ticket)
    m_raw=meta_raw(df_meta,ticket)
    m_t=meta_tables(df_meta,img_dir,ticket)
    m_bd=meta_breakdowns(df_meta)
    print(f"  ✓ {len(m_t['lct']['all']['camps'])} camps | {len(m_t['lct']['all']['adsets'])} adsets | {len(m_t['lct']['all']['ads'])} ads")

    print("\n[PESQUISA]")
    df_pes=load_pesquisa()
    pes=pesquisa_process(df_pes, hot_k["qtd"])
    print(f"  ✓ {pes['total']} respostas")

    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado"); return
    regiao_raw=load_regiao()
    cert_info,cert_raw=load_cert()
    ups_info,ups_raw=load_upsells()
    criat_links=load_criativos_links()
    html=inject_all(TEMPLATE_FILE,m_k,m_d,m_dc,m_raw,m_t,m_bd,hot_k,hot_d,h_raw,regiao_raw,cert_info,cert_raw,ups_info,ups_raw,criat_links,pes,ticket)
    Path(OUTPUT_FILE).write_text(html,encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} ({len(html)//1024}KB)")

    data_json={"cliente":NOME_CLIENTE,"cor":COR_ACENTO,"letra":LOGO_LETRA,
               "lancamento":LANCAMENTO_COD,"atualizado":date.today().strftime("%d/%m/%Y"),
               "kpis":{"spend":m_k["lct"].get("spend"),"vendas":hot_k.get("qtd"),
                       "faturamento":hot_k.get("total"),"cpa":m_k["lct"].get("cpa")}}
    Path("data.json").write_text(json.dumps(data_json,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"  ✓ data.json\n{'='*60}")

if __name__=="__main__":
    main()
