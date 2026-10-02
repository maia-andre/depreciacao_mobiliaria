"""Lê os arquivos de dados/brutos, padroniza e grava as bases em dados/processados.

Não faz análise: só carrega, normaliza tipos e confere a consistência entre arquivos.
A coluna INVENTARIANTE da planilha de não localizados (CPF e nome) nunca é lida.
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos"
PROCESSADOS = RAIZ / "dados" / "processados"

# Data de posição de cada analítico. 2026 é parcial.
ANALITICOS = {
    2015: "2015-12-31",
    2025: "2025-12-31",
    2026: "2026-09-30",
}
SINTETICOS = [2015, 2025]
# Planilha de todos os patrimônios (inclui bens que o analítico não traz). Exportada em 02/10/2026 de manhã.
POSICAO_ATIVOS = "2026-10-01"

COLUNAS_ATIVOS = {
    "Placa Patr.": "placa",
    "Class. do Bem": "classe",
    "Secretaria": "secretaria_origem",
    "Unid.Orç": "uo",
    "UO Desc": "uo_desc",
    "Cod.Item": "material",
    "Descrição Item": "material_desc",
    "Data Aquisição": "data_aquisicao",
    "Valor do Bem": "valor",
    "Num AF": "num_af",
    "Ano AF": "ano_af",
    "Obs": "obs",
    "Região": "regiao",
    "Bairro": "bairro",
    "Logradouro": "logradouro",
    "Logr_Observacao": "logradouro_obs",
    "CEP": "cep",
}

COLUNAS_ANALITICO = {
    "Secr.": "secretaria",
    "Descrição Secr.": "secretaria_desc",
    "Unid.Orç.": "uo",
    "Descrição Unid.Orç.": "uo_desc",
    "Nº Placa": "placa",
    "Material": "material",
    "Descrição Material": "material_desc",
    "Unid.": "unidade",
    "Data Aquisição": "data_aquisicao",
    "Valor Bem": "valor",
}


def ler_csv(caminho):
    return pd.read_csv(caminho, sep=";", encoding="latin1", dtype=str, keep_default_na=False)


def numero_br(serie):
    """'1.234,56' -> 1234.56; vazio -> NaN."""
    return pd.to_numeric(
        serie.str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def padronizar_placa(serie):
    placa = serie.astype(str).str.strip().str.lstrip("0")
    assert placa.str.fullmatch(r"\d+").all(), "placa com caractere não numérico"
    return placa


def carregar_analitico(ano, posicao):
    df = ler_csv(BRUTOS / f"Analítico {ano}.csv").rename(columns=COLUNAS_ANALITICO)
    df = df[list(COLUNAS_ANALITICO.values())]
    for col in df.columns:
        df[col] = df[col].str.strip()
    df["placa"] = padronizar_placa(df["placa"])
    df["data_aquisicao"] = pd.to_datetime(df["data_aquisicao"], format="%d/%m/%Y")
    df["valor"] = numero_br(df["valor"])
    df["posicao"] = pd.Timestamp(posicao)
    assert not df["placa"].duplicated().any(), f"placa duplicada no analítico {ano}"
    return df


def carregar_sintetico(ano):
    df = ler_csv(BRUTOS / f"Sintético {ano}.csv")
    df.columns = ["secretaria", "secretaria_desc", "valor"]
    df["secretaria"] = df["secretaria"].str.strip()
    df["valor"] = numero_br(df["valor"])
    return df


def carregar_nao_localizados():
    df = pd.read_excel(
        BRUTOS / "não localizados.xlsx",
        sheet_name="Plan1",
        dtype=str,
        usecols=["INVENTARIO", "PLACA", "DESCRICAO", "UO_ORIGEM", "OBSERVACAO"],
    )
    df.columns = ["inventario", "placa", "descricao", "uo_origem", "observacao"]
    df["inventario"] = df["inventario"].str.strip()
    df["placa"] = padronizar_placa(df["placa"])
    uo = df["uo_origem"].str.split(" - ", n=1, expand=True)
    df["uo"] = uo[0].str.strip()
    df["uo_desc"] = uo[1].str.strip()
    df["observacao"] = df["observacao"].str.strip()
    assert not df["placa"].duplicated().any(), "placa duplicada nos não localizados"
    return df.drop(columns="uo_origem")


def carregar_ativos():
    df = pd.read_excel(BRUTOS / "ativos todas secs.xlsx", sheet_name="PATRIMÔNIO", dtype=str)
    df = df.rename(columns=COLUNAS_ATIVOS)[list(COLUNAS_ATIVOS.values())]
    for col in df.columns:
        df[col] = df[col].str.strip()
    df["placa"] = padronizar_placa(df["placa"])
    secr = df.pop("secretaria_origem").str.split(" - ", n=1, expand=True)
    df.insert(1, "secretaria", secr[0].str.strip())
    df.insert(2, "secretaria_desc", secr[1].str.strip())
    # Vazias viram NaT; datas absurdas (ex.: ano 2208) são mantidas e tratadas na etapa de qualidade.
    df["data_aquisicao"] = pd.to_datetime(df["data_aquisicao"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"])
    df["posicao"] = pd.Timestamp(POSICAO_ATIVOS)
    assert not df["placa"].duplicated().any(), "placa duplicada na planilha de ativos"
    return df


def carregar_uos():
    # A coluna Observação não é lida (cita nomes de servidores).
    # "Perm. Rec. Patr. Físico" é campo novo, ainda não confiável como filtro.
    df = ler_csv(BRUTOS / "Lista Unidades Orçamentárias.csv")
    df = df.rename(columns={
        "Identificação": "uo",
        "Descrição": "uo_desc",
        "Secretaria": "secretaria_origem",
        "Departamento": "departamento",
        "Divisão": "divisao",
        "Setor/Superv.": "setor",
        "Data Término": "data_termino",
        "Região": "regiao",
        "Local de Entrega": "local_entrega",
        "Unid.Externa": "unid_externa",
        "Perm. Rec. Patr. Físico": "recebe_patrimonio",
    }).drop(columns="Observação")
    for col in df.columns:
        df[col] = df[col].str.strip()
    secr = df.pop("secretaria_origem").str.split(" - ", n=1, expand=True)
    df.insert(2, "secretaria", secr[0].str.strip())
    df.insert(3, "secretaria_desc", secr[1].str.strip())
    df["data_termino"] = pd.to_datetime(df["data_termino"], format="%d/%m/%Y", errors="coerce")
    df["unid_externa"] = df["unid_externa"].eq("S")
    assert not df["uo"].duplicated().any(), "UO duplicada na lista"
    return df


def data_mista(serie):
    """Excel mistura células de data ('2021-05-02 00:00:00') e texto ('30/03/1981')."""
    iso = pd.to_datetime(serie, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    br = pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(br)


# Relatórios de baixa do sistema: mesmo layout, um arquivo por tipo e período.
# A data de baixa é a da mudança de status (o filtro do relatório usa essa data).
BAIXAS = [
    ("furto", "furtados 01011970 a 30092026.xlsx"),
    ("destombado", "destombados 01012025 a 31122025.xlsx"),
    ("destombado", "destombados 01012026 a 30092026.xlsx"),
    ("inservivel", "inservivel 01012025 a 31122025.xlsx"),
    ("inservivel", "inservivel 01012026 a 30092026.xlsx"),
]


def carregar_baixas():
    # CNPJ/CPF do fornecedor não é lido (pode ser pessoa física). O motivo pode ter nome de pessoa.
    partes = []
    for tipo, arquivo in BAIXAS:
        df = pd.read_excel(
            BRUTOS / arquivo,
            sheet_name="Plan1",
            dtype=str,
            usecols=[
                "Nº PLACA", "DATA BAIXA", "MOTIVO DA BAIXA", "VALOR", "COD.MATERIAL",
                "DESCRIÇÃO DO MATERIAL", "NUM.AF", "ANO AF", "NOTA FISCAL", "RAZÃO SOCIAL", "DATA AQUISIÇÃO",
            ],
        )
        df.columns = [
            "placa", "data_baixa", "motivo", "valor", "material",
            "material_desc", "num_af", "ano_af", "nota_fiscal", "fornecedor", "data_aquisicao",
        ]
        for col in df.columns:
            df[col] = df[col].str.strip()
        df.insert(1, "tipo_baixa", tipo)
        df["arquivo"] = arquivo
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    df["placa"] = padronizar_placa(df["placa"])
    df["data_baixa"] = data_mista(df["data_baixa"])
    df["data_aquisicao"] = data_mista(df["data_aquisicao"])
    df["valor"] = pd.to_numeric(df["valor"])
    assert not df["placa"].duplicated().any(), "placa repetida entre os relatórios de baixa"
    return df


def main():
    PROCESSADOS.mkdir(parents=True, exist_ok=True)

    analiticos = {}
    for ano, posicao in ANALITICOS.items():
        df = carregar_analitico(ano, posicao)
        df.to_parquet(PROCESSADOS / f"analitico_{ano}.parquet", index=False)
        analiticos[ano] = df
        futuras = (df["data_aquisicao"] > df["posicao"]).sum()
        print(
            f"analítico {ano} (posição {posicao}): {len(df):>7,} placas | "
            f"R$ {df['valor'].sum():>16,.2f} | sem valor: {df['valor'].isna().sum()} | "
            f"data após a posição: {futuras}"
        )

    for ano in SINTETICOS:
        sint = carregar_sintetico(ano)
        sint.to_parquet(PROCESSADOS / f"sintetico_{ano}.parquet", index=False)
        soma = analiticos[ano].groupby("secretaria")["valor"].sum()
        dif = (sint.set_index("secretaria")["valor"] - soma).abs()
        print(
            f"sintético {ano}: R$ {sint['valor'].sum():,.2f} | "
            f"maior diferença por secretaria contra o analítico: R$ {dif.max():,.2f}"
        )

    ativos = carregar_ativos()
    ativos.to_parquet(PROCESSADOS / "ativos.parquet", index=False)
    no_analitico = ativos["placa"].isin(analiticos[2026]["placa"])
    print(
        f"planilha de ativos (posição {POSICAO_ATIVOS}): {len(ativos):,} placas | "
        f"R$ {ativos['valor'].sum():,.2f} | sem data: {ativos['data_aquisicao'].isna().sum()} | "
        f"no analítico 2026: {no_analitico.sum():,} | só na planilha: {(~no_analitico).sum():,} | "
        f"analítico 2026 fora da planilha: {(~analiticos[2026]['placa'].isin(ativos['placa'])).sum()}"
    )

    uos = carregar_uos()
    uos.to_parquet(PROCESSADOS / "uos.parquet", index=False)
    encerrada = ativos["uo"].isin(uos.loc[uos["data_termino"].notna(), "uo"])
    print(
        f"UOs: {len(uos):,} | com data de término: {uos['data_termino'].notna().sum():,} | "
        f"UOs da planilha fora da lista: {(~ativos['uo'].isin(uos['uo'])).sum()} | "
        f"bens em UO encerrada: {encerrada.sum():,} (R$ {ativos.loc[encerrada, 'valor'].sum():,.2f})"
    )

    baixas = carregar_baixas()
    baixas.to_parquet(PROCESSADOS / "baixas.parquet", index=False)
    for tipo, grupo in baixas.groupby("tipo_baixa", sort=False):
        print(
            f"baixas ({tipo}): {len(grupo):,} placas | R$ {grupo['valor'].sum():,.2f} | "
            f"de {grupo['data_baixa'].min():%d/%m/%Y} a {grupo['data_baixa'].max():%d/%m/%Y} | "
            f"ainda na planilha de ativos: {grupo['placa'].isin(ativos['placa']).sum()}"
        )

    nl = carregar_nao_localizados()
    nl.to_parquet(PROCESSADOS / "nao_localizados.parquet", index=False)
    em_algum = pd.concat([a["placa"] for a in analiticos.values()]).unique()
    fora = ~nl["placa"].isin(em_algum)
    print(
        f"não localizados: {len(nl):,} placas | inventários: {sorted(nl['inventario'].unique())} | "
        f"fora de todos os analíticos: {fora.sum():,}"
    )


if __name__ == "__main__":
    main()
