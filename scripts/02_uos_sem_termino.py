"""Relação dos bens em UOs sem data de término que mesmo assim ficam fora do analítico.

Saída: saidas/uos_sem_termino_fora_do_analitico.xlsx (abas Resumo e Bens).
A coluna Obs da planilha de ativos não vai para a saída (pode ter nome de pessoa).
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"
SAIDA = RAIZ / "saidas" / "uos_sem_termino_fora_do_analitico.xlsx"


def main():
    ativos = pd.read_parquet(PROCESSADOS / "ativos.parquet")
    uos = pd.read_parquet(PROCESSADOS / "uos.parquet")
    nl = pd.read_parquet(PROCESSADOS / "nao_localizados.parquet")
    uos_relatorio = set()
    for ano in (2015, 2025, 2026):
        uos_relatorio |= set(pd.read_parquet(PROCESSADOS / f"analitico_{ano}.parquet", columns=["uo"])["uo"])

    alvo = uos[uos["data_termino"].isna() & ~uos["uo"].isin(uos_relatorio)]
    bens = ativos[ativos["uo"].isin(alvo["uo"])].copy()
    alvo = alvo[alvo["uo"].isin(bens["uo"])]
    bens["nao_localizado_2025"] = bens["placa"].isin(nl["placa"]).map({True: "sim", False: "não"})

    resumo = (
        bens.groupby("uo")
        .agg(bens=("placa", "size"), valor=("valor", "sum"),
             nao_localizados=("nao_localizado_2025", lambda s: (s == "sim").sum()))
        .reset_index()
        .merge(alvo[["uo", "uo_desc", "secretaria", "secretaria_desc", "unid_externa", "regiao", "local_entrega"]], on="uo")
        .sort_values("bens", ascending=False)
    )
    resumo["unid_externa"] = resumo["unid_externa"].map({True: "sim", False: "não"})
    resumo = resumo[["uo", "uo_desc", "secretaria", "secretaria_desc", "unid_externa", "regiao",
                     "local_entrega", "bens", "valor", "nao_localizados"]]

    bens = bens.sort_values(["uo", "placa"])[[
        "uo", "uo_desc", "secretaria", "placa", "classe", "material", "material_desc",
        "data_aquisicao", "valor", "num_af", "ano_af", "regiao", "bairro", "logradouro", "nao_localizado_2025",
    ]]

    SAIDA.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(SAIDA, engine="openpyxl") as xl:
        resumo.to_excel(xl, sheet_name="Resumo", index=False)
        bens.to_excel(xl, sheet_name="Bens", index=False)
        for aba, df in (("Resumo", resumo), ("Bens", bens)):
            ws = xl.sheets[aba]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(df.columns, start=1):
                largura = min(max(len(str(col)), df[col].astype(str).str.len().max()) + 2, 60)
                ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
            for cel in ws[ws.cell(1, df.columns.get_loc("valor") + 1).column_letter][1:]:
                cel.number_format = "#,##0.00"
            if "data_aquisicao" in df.columns:
                for cel in ws[ws.cell(1, df.columns.get_loc("data_aquisicao") + 1).column_letter][1:]:
                    cel.number_format = "dd/mm/yyyy"

    print(resumo.to_string(index=False))
    print(f"\n{len(bens)} bens, R$ {bens['valor'].sum():,.2f} -> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
