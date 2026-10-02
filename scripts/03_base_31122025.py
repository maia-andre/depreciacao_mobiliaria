"""Reconstrói a base de bens móveis em 31/12/2025.

O sistema não guarda histórico, então a base é montada a partir da posição atual:
  1. planilha de ativos (bens sem data de baixa), sem as aquisições de 2026;
  2. + bens baixados em 2026 (furto, destombamento, inservível) adquiridos até 2025;
  3. + placas do analítico 2025 que não estão em 1 nem 2: bens com data de baixa em 2026
     mas status "em uso" (cadastro inconsistente), que só o analítico 2025 enxerga;
  4. + inservíveis declarados até o corte e ainda não leiloados: a Contabilidade só baixa
     no leilão (destombamento), então seguem no razão. Ficam marcados como fora da visão
     do Patrimônio, que trata o inservível como baixado.

Os relatórios de baixa não trazem UO nem classe: a classe vem do código de material
(classe mais frequente na planilha) e a UO fica vazia.

Saída: dados/processados/base_31122025.parquet
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"
CORTE = pd.Timestamp("2025-12-31")
ANO_SEGUINTE = CORTE.year + 1

COLUNAS = [
    "placa", "origem", "tipo_baixa", "data_baixa", "secretaria", "uo", "uo_desc",
    "classe", "classe_fonte", "material", "material_desc", "data_aquisicao", "valor",
]


def classe_por_material(ativos):
    """Classe mais frequente de cada código de material, e se o código tem mais de uma classe."""
    contagem = ativos.groupby(["material", "classe"]).size().rename("n").reset_index()
    contagem = contagem.sort_values(["material", "n"], ascending=[True, False])
    mapa = contagem.drop_duplicates("material").set_index("material")["classe"]
    ambiguo = contagem.groupby("material").size().gt(1)
    return mapa, ambiguo


def main():
    ativos = pd.read_parquet(PROCESSADOS / "ativos.parquet")
    baixas = pd.read_parquet(PROCESSADOS / "baixas.parquet")
    analitico = pd.read_parquet(PROCESSADOS / "analitico_2025.parquet")
    uos = pd.read_parquet(PROCESSADOS / "uos.parquet")
    nl = pd.read_parquet(PROCESSADOS / "nao_localizados.parquet")
    mapa_classe, material_ambiguo = classe_por_material(ativos)

    # 1. Planilha: sai só o que foi adquirido no ano seguinte ao corte.
    #    Sem data ou com ano absurdo (2029, 2208...) fica, marcado como data inválida.
    adquirido_depois = ativos["data_aquisicao"].dt.year.eq(ANO_SEGUINTE)
    parte1 = ativos[~adquirido_depois].assign(
        origem="planilha", tipo_baixa=None, data_baixa=pd.NaT, classe_fonte="planilha",
    )

    # 2. Baixas posteriores ao corte de bens que já existiam no corte.
    voltam = baixas[(baixas["data_baixa"] > CORTE) & ~(baixas["data_aquisicao"] > CORTE)]
    parte2 = voltam.assign(
        origem="baixa_posterior", secretaria=None, uo=None, uo_desc=None,
        classe=voltam["material"].map(mapa_classe), classe_fonte="material",
    )

    # 3. Analítico 2025: bens com data de baixa posterior mas status "em uso".
    ja = set(parte1["placa"]) | set(parte2["placa"])
    inconsistentes = analitico[~analitico["placa"].isin(ja)]
    parte3 = inconsistentes.assign(
        origem="analitico_2025_baixa_sem_status", tipo_baixa=None, data_baixa=pd.NaT,
        classe=inconsistentes["material"].map(mapa_classe), classe_fonte="material",
    )

    # 4. Inservíveis aguardando leilão no corte.
    aguardando = baixas[(baixas["tipo_baixa"] == "inservivel") & (baixas["data_baixa"] <= CORTE)
                        & ~(baixas["data_aquisicao"] > CORTE)]
    parte4 = aguardando.assign(
        origem="inservivel_aguardando_leilao", secretaria=None, uo=None, uo_desc=None,
        classe=aguardando["material"].map(mapa_classe), classe_fonte="material",
    )

    base = pd.concat([parte1[COLUNAS], parte2[COLUNAS], parte3[COLUNAS], parte4[COLUNAS]], ignore_index=True)
    assert not base["placa"].duplicated().any(), "placa repetida na base reconstruída"

    encerradas = set(uos.loc[uos["data_termino"].notna(), "uo"])
    externas = set(uos.loc[uos["unid_externa"], "uo"])
    base["uo_encerrada"] = base["uo"].isin(encerradas)
    base["unid_externa"] = base["uo"].isin(externas)
    base["sem_data"] = base["data_aquisicao"].isna()
    base["data_invalida"] = base["data_aquisicao"].dt.year.gt(ANO_SEGUINTE)
    # Só importa quando a classe foi deduzida do material (bens baixados e inconsistentes).
    base["classe_incerta"] = base["classe_fonte"].eq("material") & base["material"].map(material_ambiguo).eq(True)
    base["sem_classe"] = base["classe"].isna()
    base["no_analitico_2025"] = base["placa"].isin(analitico["placa"])
    base["nao_localizado_2025"] = base["placa"].isin(nl["placa"])
    base["visao_patrimonio"] = ~base["origem"].eq("inservivel_aguardando_leilao")
    base["posicao"] = CORTE

    base.to_parquet(PROCESSADOS / "base_31122025.parquet", index=False)

    print(f"Base em {CORTE:%d/%m/%Y}: {len(base):,} placas | R$ {base['valor'].sum():,.2f}")
    vp = base[base["visao_patrimonio"]]
    print(f"  visão Patrimônio (sem inservíveis aguardando leilão): {len(vp):,} placas | R$ {vp['valor'].sum():,.2f}")
    print(base.groupby(["origem", "tipo_baixa"], dropna=False)["valor"].agg(["size", "sum"]).to_string())
    print(f"\nAnalítico 2025: {len(analitico):,} placas | R$ {analitico['valor'].sum():,.2f} | "
          f"todas na base: {analitico['placa'].isin(base['placa']).all()}")
    fora = base[~base["no_analitico_2025"]]
    print(f"Na base e fora do analítico: {len(fora):,} placas | R$ {fora['valor'].sum():,.2f}")
    for flag in ["uo_encerrada", "unid_externa", "sem_data", "data_invalida", "sem_classe",
                 "classe_incerta", "nao_localizado_2025"]:
        sel = base[base[flag]]
        print(f"  {flag:<22} {len(sel):>7,} placas | R$ {sel['valor'].sum():>16,.2f}")


if __name__ == "__main__":
    main()
