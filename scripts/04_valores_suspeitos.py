"""Panorama de valores suspeitos (exorbitantes), com hipótese de correção e rastreio pela AF.

Universo: planilha de ativos + relatórios de baixa (furto, destombado, inservível).
Referência de cada código de material: mediana dos bens do mesmo código adquiridos a partir
de 01/07/1994 (Plano Real), sem o lote de 26/10/1994 e sem valores abaixo de R$ 1.

Tipos de suspeita:
  A. fora do padrão do material: valor >= 20x a mediana do código (3+ bens de referência)
     e excesso >= R$ 1.000;
  B. lote de 1994 com valor >= R$ 1.000 (o lote é de centavos);
  S. serviço ou contrato cadastrado como bem (pela descrição), valor >= R$ 10.000.
Fora do panorama, em aba separada: bens >= R$ 100.000 sem referência (conferência manual).

Hipótese e valor provável, nesta ordem:
  1. vírgula deslocada: valor / 1.000 ou / 100 cai entre 0,5x e 2x a referência
     (a referência é a mediana dos itens da mesma AF e material, se houver, senão a do material);
  2. diverge da própria AF: outros bens do mesmo material na mesma AF têm valor normal;
  3. verificar AF: sem hipótese (valor provável = mediana do material, só indicativo).
Confiança: alta = vírgula deslocada confirmada pelos itens da mesma AF, ou razão >= 500;
média = uma das duas evidências; baixa = verificar AF.

Saída: saidas/valores_suspeitos.xlsx. Observação e motivo não vão para a saída (nomes de pessoas).
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"
SAIDA = RAIZ / "saidas" / "valores_suspeitos.xlsx"

PLANO_REAL = pd.Timestamp("1994-07-01")
LOTE_1994 = pd.Timestamp("1994-10-26")
RAZAO_MINIMA = 20
RAZAO_ALTA = 500
EXCESSO_MINIMO = 1_000
REF_MINIMA = 3
VALOR_ALTO = 100_000
VALOR_SERVICO = 10_000
FAIXA = (0.5, 2.0)
SERVICO = r"PRESTACAO DE SERVICO|CONTRATACAO DE EMPRESA|FORNECIMENTO E INSTALACAO|^INSTALACAO DE|COM OPERADOR"
GENERICO = r"PATRIMONIO DOADO|CODIGO INVALIDO|POUCO ?ESPECIFICADO|FAVOR NAO UTILIZAR"

COLUNAS_SAIDA = [
    "tipo", "hipotese", "confianca", "situacao", "placa", "secretaria", "uo_desc", "classe", "material",
    "material_desc", "data_aquisicao", "valor", "valor_provavel", "ajuste", "mediana_material", "n_referencia",
    "razao", "af", "af_placas", "af_valor_total", "af_pares", "af_mediana_pares", "nota_fiscal", "fornecedor",
    "data_baixa", "nao_localizado_2025", "codigo_generico",
]
MOEDA = {"valor", "valor_provavel", "ajuste", "mediana_material", "af_valor_total", "af_mediana_pares",
         "valor_suspeito", "valor_provavel_total"}


def carregar_universo():
    ativos = pd.read_parquet(PROCESSADOS / "ativos.parquet")
    baixas = pd.read_parquet(PROCESSADOS / "baixas.parquet")
    nl = pd.read_parquet(PROCESSADOS / "nao_localizados.parquet")
    colunas = ["placa", "situacao", "secretaria", "uo", "uo_desc", "classe", "material", "material_desc",
               "data_aquisicao", "valor", "num_af", "ano_af", "nota_fiscal", "fornecedor", "data_baixa"]
    a = ativos.assign(situacao="ativo", nota_fiscal=None, fornecedor=None, data_baixa=pd.NaT)
    b = baixas.assign(situacao=baixas["tipo_baixa"], secretaria=None, uo=None, uo_desc=None, classe=None)
    u = pd.concat([a[colunas], b[colunas]], ignore_index=True)
    u["af"] = (u["num_af"].fillna("") + "/" + u["ano_af"].fillna("")).where(u["num_af"].notna())
    u["nao_localizado_2025"] = u["placa"].isin(nl["placa"])
    u["lote_1994"] = u["data_aquisicao"].eq(LOTE_1994)
    u["codigo_generico"] = u["material_desc"].str.contains(GENERICO, regex=True, na=False)
    return u


def pares_na_af(u, alvo):
    """Quantidade e mediana dos outros bens do mesmo material na mesma AF, para as linhas de `alvo`."""
    grupos = {k: g for k, g in u[u["af"].notna()].groupby(["af", "material"])["valor"]}
    n, med = [], []
    for i, linha in alvo.iterrows():
        g = grupos.get((linha["af"], linha["material"]))
        outros = g.drop(i) if g is not None else pd.Series(dtype=float)
        n.append(len(outros))
        med.append(outros.median() if len(outros) else None)
    return pd.Series(n, index=alvo.index), pd.Series(med, index=alvo.index, dtype=float)


def classificar(linha):
    ref = linha["af_mediana_pares"] if pd.notna(linha["af_mediana_pares"]) else linha["mediana_material"]
    if pd.notna(ref) and ref > 0:
        for divisor in (1_000, 100):
            if FAIXA[0] <= linha["valor"] / divisor / ref <= FAIXA[1]:
                confirmada = pd.notna(linha["af_mediana_pares"]) or linha["razao"] >= RAZAO_ALTA
                return (f"vírgula deslocada (÷{divisor:,})".replace(",", "."), round(linha["valor"] / divisor, 2),
                        "alta" if confirmada else "média")
    if pd.notna(linha["af_mediana_pares"]) and linha["valor"] >= RAZAO_MINIMA * linha["af_mediana_pares"]:
        return "diverge dos itens da mesma AF", linha["af_mediana_pares"], "média"
    return "verificar AF", linha["mediana_material"], "baixa"


def gravar(caminho, abas):
    caminho.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(caminho, engine="openpyxl") as xl:
        for nome, df in abas.items():
            df.to_excel(xl, sheet_name=nome, index=False)
            ws = xl.sheets[nome]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(df.columns, start=1):
                letra = ws.cell(1, i).column_letter
                ws.column_dimensions[letra].width = min(max(len(str(col)), df[col].astype(str).str.len().max()) + 2, 50)
                formato = ("dd/mm/yyyy" if col.startswith("data") else "#,##0.00" if col in MOEDA
                           else "0.0" if col == "razao" else None)
                if formato:
                    for cel in ws[letra][1:]:
                        cel.number_format = formato


def main():
    u = carregar_universo()

    ref = u[(u["data_aquisicao"] >= PLANO_REAL) & ~u["lote_1994"] & (u["valor"] >= 1) & ~u["codigo_generico"]]
    estat = ref.groupby("material")["valor"].agg(n_referencia="size", mediana_material="median")
    u = u.join(estat, on="material")
    u["n_referencia"] = u["n_referencia"].fillna(0).astype(int)
    u["razao"] = u["valor"] / u["mediana_material"]
    u["excesso"] = u["valor"] - u["mediana_material"]
    u["af_placas"] = u.groupby("af")["placa"].transform("size")
    u["af_valor_total"] = u.groupby("af")["valor"].transform("sum")

    servico = u["material_desc"].str.contains(SERVICO, regex=True, na=False) & (u["valor"] >= VALOR_SERVICO)
    crit_a = ((u["n_referencia"] >= REF_MINIMA) & (u["razao"] >= RAZAO_MINIMA)
              & (u["excesso"] >= EXCESSO_MINIMO) & ~u["codigo_generico"])
    crit_b = u["lote_1994"] & (u["valor"] >= 1_000)
    u["tipo"] = None
    u.loc[servico, "tipo"] = "S. serviço ou contrato como bem"
    u.loc[crit_b, "tipo"] = "B. lote 1994 com valor"
    u.loc[crit_a, "tipo"] = "A. fora do padrão do material"
    alto = u[u["tipo"].isna() & (u["n_referencia"] < REF_MINIMA) & (u["valor"] >= VALOR_ALTO)].copy()

    s = u[u["tipo"].notna()].copy()
    s["af_pares"], s["af_mediana_pares"] = pares_na_af(u, s)
    alto["af_pares"], alto["af_mediana_pares"] = pares_na_af(u, alto)
    s[["hipotese", "valor_provavel", "confianca"]] = s.apply(classificar, axis=1, result_type="expand")
    eh_servico = s["tipo"].str.startswith("S")
    s.loc[eh_servico, ["hipotese", "valor_provavel", "confianca"]] = [
        "valor do contrato no bem; avaliar se é bem ou despesa", None, "baixa"]
    s["ajuste"] = s["valor_provavel"] - s["valor"]
    s = s.sort_values(["tipo", "excesso"], ascending=[True, False], na_position="last")
    suspeitos = s[COLUNAS_SAIDA]

    resumo = (suspeitos.groupby(["tipo", "hipotese", "confianca", "situacao"], dropna=False)
              .agg(placas=("placa", "size"), valor=("valor", "sum"), valor_provavel=("valor_provavel", "sum"),
                   ajuste=("ajuste", "sum"))
              .reset_index())
    por_af = (suspeitos[suspeitos["af"].notna()]
              .groupby("af")
              .agg(placas_suspeitas=("placa", "size"), placas_na_af=("af_placas", "first"),
                   valor_suspeito=("valor", "sum"), valor_provavel_total=("valor_provavel", "sum"),
                   confianca=("confianca", lambda x: ", ".join(sorted(set(x)))),
                   materiais=("material_desc", lambda x: "; ".join(sorted(set(x.str[:40])))[:200]))
              .sort_values("valor_suspeito", ascending=False)
              .reset_index())
    alto = alto.sort_values("valor", ascending=False).assign(
        tipo="alto valor sem referência", hipotese="conferência manual", confianca=None,
        valor_provavel=None, ajuste=None)[COLUNAS_SAIDA]

    gravar(SAIDA, {"Resumo": resumo, "Suspeitos": suspeitos, "Por AF": por_af, "Alto valor (conferir)": alto})

    pd.set_option("display.width", 220)
    print(resumo.to_string(index=False))
    for rotulo, g in suspeitos.groupby(suspeitos["situacao"].eq("ativo").map({True: "no patrimônio", False: "já baixados"})):
        print(f"{rotulo}: {len(g)} placas | valor R$ {g['valor'].sum():,.2f} | ajuste estimado R$ {g['ajuste'].sum():,.2f}")
    print(f"AFs com suspeitos: {len(por_af)} | alto valor sem referência: {len(alto)} | -> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
