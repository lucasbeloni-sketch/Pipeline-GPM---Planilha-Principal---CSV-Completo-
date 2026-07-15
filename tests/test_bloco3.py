"""Testes das funções puras de bloco3_plan_principal."""
import pytest

import bloco3_plan_principal as b3


# =========================
# helpers básicos
# =========================
def test_is_blank():
    assert b3.is_blank(None) is True
    assert b3.is_blank("") is True
    assert b3.is_blank("x") is False
    assert b3.is_blank(0) is False


def test_as_text():
    assert b3.as_text(None) == ""
    assert b3.as_text(5) == "5"
    assert b3.as_text("abc") == "abc"


def test_pad_row():
    assert b3.pad_row([1, 2], 4) == [1, 2, "", ""]
    assert b3.pad_row([1, 2, 3, 4, 5], 3) == [1, 2, 3]
    assert b3.pad_row(None, 2) == ["", ""]


def test_pad_matrix():
    assert b3.pad_matrix([[1]], 2, 3) == [[1, "", ""], ["", "", ""]]


# =========================
# dimensoes_range
# =========================
@pytest.mark.parametrize(
    "rng, esperado",
    [
        ("B2", (2, 2, 1, 1)),
        ("A1:C3", (1, 1, 3, 3)),
        ("A1:A10", (1, 1, 10, 1)),
    ],
)
def test_dimensoes_range(rng, esperado):
    assert b3.dimensoes_range(rng) == esperado


# =========================
# escape_formula_text
# =========================
def test_escape_formula_text():
    assert b3.escape_formula_text('a"b') == 'a""b'
    assert b3.escape_formula_text("abc") == "abc"
    assert b3.escape_formula_text(None) == ""


# =========================
# construtores de fórmula
# =========================
def test_formula_be():
    assert b3.formula_be(6, "BARREIRAS") == '=IF(B6<>"";"BARREIRAS";"")'


def test_formula_be_escapa_aspas():
    assert b3.formula_be(6, 'X"Y') == '=IF(B6<>"";"X""Y";"")'


def test_formulas_j_l():
    j, k, l = b3.formulas_j_l(6)
    assert j == '=XLOOKUP(H6;Carteira!$C:$C;Carteira!$S:$S;"")'
    assert k == '=XLOOKUP(H6;Carteira!$C:$C;Carteira!$Q:$Q;"")'
    assert l == '=XLOOKUP(H6;Carteira!$C:$C;Carteira!$R:$R;"")'


def test_formulas_derivadas_an_ap_ar():
    an, ap, ar = b3.formulas_derivadas_an_ap_ar(7)
    assert an == '=IF(B7="";"";IFERROR(AL7/AM7;0))'
    assert ap == '=IF(B7="";"";IFERROR(AO7/AL7;0))'
    assert ar == '=IF(B7="";"";IFERROR(AQ7/AM7;0))'


# =========================
# propagação IMPORTRANGE
# =========================
def test_importrange_regex_aspas_duplas_ponto_virgula():
    f = '=IMPORTRANGE("189ABC"; "GUA_SERV!A1:G")'
    m = b3._IMPORTRANGE_RE.search(f)
    assert m.groups() == ("189ABC", "GUA_SERV!A1:G")


def test_importrange_regex_aspas_simples_e_virgula():
    f = "=importrange('ID1', 'BAR_SERV!A1:G')"
    m = b3._IMPORTRANGE_RE.search(f)
    assert m.groups() == ("ID1", "BAR_SERV!A1:G")


def test_importrange_regex_sem_match():
    assert b3._IMPORTRANGE_RE.search('=SUM(A1:A5)') is None


def test_assinatura_ignora_linhas_vazias_finais():
    com_vazias = [["x", "1"], ["y", "2"], ["", ""]]
    sem_vazias = [["x", "1"], ["y", "2"]]
    assert b3.assinatura_valores(com_vazias) == b3.assinatura_valores(sem_vazias)


def test_assinatura_sensivel_ao_conteudo():
    a = [["x", "1"], ["y", "2"]]
    b = [["x", "1"], ["y", "9"]]
    assert b3.assinatura_valores(a) != b3.assinatura_valores(b)


def test_assinatura_vazio():
    n, _ = b3.assinatura_valores([["", ""]])
    assert n == 0
