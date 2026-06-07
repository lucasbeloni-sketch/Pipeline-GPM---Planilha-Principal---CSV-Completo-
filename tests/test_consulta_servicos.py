"""Testes das funções puras de compilador_consulta_servicos_GPM."""
import pandas as pd
import pytest

import compilador_consulta_servicos_GPM as cs


# =========================
# to_number_ptbr
# =========================
@pytest.mark.parametrize(
    "entrada, esperado",
    [
        (None, 0.0),
        ("", 0.0),
        ("   ", 0.0),
        ("nan", 0.0),
        ("None", 0.0),
        ("abc", 0.0),
        ("1234", 1234.0),
        ("1.234,56", 1234.56),   # BR: ponto de milhar + vírgula decimal
        ("10", 10.0),
        ("1.234", 1.234),        # sem vírgula => ponto é decimal
        ("1 234,5", 1234.5),     # espaço removido
    ],
)
def test_to_number_ptbr(entrada, esperado):
    assert cs.to_number_ptbr(entrada) == esperado


# =========================
# select_target_columns
# =========================
def _df_com_nomes_alvo():
    dados = {nome: [i] for i, nome in enumerate(cs.TARGET_COLUMNS)}
    dados["extra"] = [999]
    return pd.DataFrame(dados)


def test_select_target_columns_por_nome_padrao():
    df = _df_com_nomes_alvo()
    out = cs.select_target_columns(df)
    assert list(out.columns) == cs.TARGET_COLUMNS
    # valores preservados na ordem de TARGET_COLUMNS
    assert out.iloc[0].tolist() == list(range(len(cs.TARGET_COLUMNS)))


def test_select_target_columns_nome_ausente(monkeypatch):
    monkeypatch.setattr(cs, "KEEP_COLS_BY_NAME", ["nao_existe"] + cs.TARGET_COLUMNS[1:])
    df = _df_com_nomes_alvo()
    with pytest.raises(KeyError):
        cs.select_target_columns(df)


def test_select_target_columns_quantidade_errada(monkeypatch):
    monkeypatch.setattr(cs, "KEEP_COLS_BY_NAME", ["centro_servico"])  # só 1 nome
    df = _df_com_nomes_alvo()
    with pytest.raises(ValueError):
        cs.select_target_columns(df)


def test_select_target_columns_por_posicao(monkeypatch):
    monkeypatch.setattr(cs, "KEEP_COLS_BY_NAME", [])  # força fallback por posição
    monkeypatch.setattr(cs, "KEEP_COL_POS_1BASED", [1, 2, 3, 4, 5, 6, 7])
    df = pd.DataFrame([[10, 20, 30, 40, 50, 60, 70, 80]],
                      columns=[f"c{i}" for i in range(8)])
    out = cs.select_target_columns(df)
    assert list(out.columns) == cs.TARGET_COLUMNS
    assert out.iloc[0].tolist() == [10, 20, 30, 40, 50, 60, 70]


def test_select_target_columns_posicao_fora_do_intervalo(monkeypatch):
    monkeypatch.setattr(cs, "KEEP_COLS_BY_NAME", [])
    monkeypatch.setattr(cs, "KEEP_COL_POS_1BASED", [1, 2, 3, 4, 5, 6, 99])
    df = pd.DataFrame([[1, 2, 3, 4, 5, 6, 7]], columns=[f"c{i}" for i in range(7)])
    with pytest.raises(IndexError):
        cs.select_target_columns(df)


# =========================
# datas
# =========================
def test_extrair_data_string():
    s = pd.Series(["30/06/2026 - terça-feira", "2026-06-30", "lixo"])
    out = cs.extrair_data_string(s)
    assert out.iloc[0] == "30/06/2026"
    assert out.iloc[1] == "2026/06/30"   # ISO normalizado para "/"
    assert pd.isna(out.iloc[2])


@pytest.mark.parametrize(
    "datas, esperado",
    [
        (["25/06/2026", "13/01/2026"], "DMY"),  # 25 e 13 > 12 => dia primeiro
        (["01/15/2026"], "MDY"),                # 15 no 2º campo => mês primeiro
        (["05/06/2026"], "DMY"),                # ambíguo => padrão BR
        ([], "DMY"),
    ],
)
def test_inferir_formato_por_arquivo(datas, esperado):
    serie = cs.extrair_data_string(pd.Series(datas))
    assert cs.inferir_formato_por_arquivo(serie) == esperado


def test_parse_date_por_arquivo_dmy_e_iso():
    df = pd.DataFrame(
        {
            "d": ["25/06/2026", "2026-06-30"],
            "arq": ["f1", "f1"],
        }
    )
    out = cs.parse_date_por_arquivo(df, "d", "arq")
    assert out.notna().all()
    assert out.iloc[0] == pd.Timestamp("2026-06-25")
    assert out.iloc[1] == pd.Timestamp("2026-06-30")


def test_parse_date_por_arquivo_invalida_vira_nat():
    df = pd.DataFrame({"d": ["sem data"], "arq": ["f1"]})
    out = cs.parse_date_por_arquivo(df, "d", "arq")
    assert out.isna().all()
