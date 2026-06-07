"""Testes das funções puras de compilador_planilha_principal."""
import pytest

import compilador_planilha_principal as cpp


# =========================
# normalize_numeric_string
# =========================
@pytest.mark.parametrize(
    "entrada, esperado",
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        (123, 123),            # não-string volta como está
        (12.5, 12.5),
        ("1234", 1234),
        ("1.234", 1234),       # agrupamento de milhar (ponto)
        ("1.000.000", 1000000),
        ("12.345.678", 12345678),
        ("1.234,56", 1234.56),   # padrão BR
        ("1,234.56", 1234.56),   # padrão US
        ("1.23", 1.23),          # decimal com ponto
        ("1,5", 1.5),            # decimal com vírgula
        ("R$ 1.234,56", 1234.56),
        ("(123)", -123),         # parênteses = negativo
        ("-5", -5),
        ("10%", "10%"),
        ("abc", "abc"),          # não numérico volta original
        ("0123", "0123"),        # zero à esquerda preserva original
        ("1.2.3", "1.2.3"),      # ambíguo volta original
    ],
)
def test_normalize_numeric_string(entrada, esperado):
    assert cpp.normalize_numeric_string(entrada) == esperado


def test_normalize_remove_apostrofo_inicial():
    assert cpp.normalize_numeric_string("'1234") == 1234


# =========================
# is_grouped_thousands
# =========================
@pytest.mark.parametrize(
    "valor, sep, esperado",
    [
        ("1.234", ".", True),
        ("12.345.678", ".", True),
        ("1.23", ".", False),
        ("1.2345", ".", False),
        ("12", ".", False),
        ("1,234", ",", True),
        ("abc", ".", False),
    ],
)
def test_is_grouped_thousands(valor, sep, esperado):
    assert cpp.is_grouped_thousands(valor, sep) is esperado


# =========================
# column_letter_to_number / get_range_width
# =========================
@pytest.mark.parametrize(
    "letra, numero",
    [("A", 1), ("Z", 26), ("AA", 27), ("AK", 37), ("BX", 76)],
)
def test_column_letter_to_number(letra, numero):
    assert cpp.column_letter_to_number(letra) == numero


@pytest.mark.parametrize(
    "rng, largura",
    [("B5:BX", 75), ("A1:A10", 1), ("A:C", 3)],
)
def test_get_range_width(rng, largura):
    assert cpp.get_range_width(rng) == largura


def test_get_range_width_invalido():
    with pytest.raises(ValueError):
        cpp.get_range_width("intervalo-invalido")


# =========================
# pad_rows_to_width
# =========================
def test_pad_rows_to_width_preenche_e_corta():
    assert cpp.pad_rows_to_width([[1, 2]], 4) == [[1, 2, "", ""]]
    assert cpp.pad_rows_to_width([[1, 2, 3, 4, 5]], 3) == [[1, 2, 3]]


# =========================
# helpers de células/linhas
# =========================
def test_cell_has_value():
    assert cpp.cell_has_value("x") is True
    assert cpp.cell_has_value("0") is True
    assert cpp.cell_has_value(None) is False
    assert cpp.cell_has_value("") is False
    assert cpp.cell_has_value("   ") is False


def test_row_has_any_value():
    assert cpp.row_has_any_value([None, "", "x"]) is True
    assert cpp.row_has_any_value([None, "", ""]) is False
    assert cpp.row_has_any_value([]) is False


def test_remove_fully_blank_rows():
    linhas = [["a", ""], ["", ""], [None, None], ["", "b"]]
    assert cpp.remove_fully_blank_rows(linhas) == [["a", ""], ["", "b"]]


def test_filter_rows_where_first_column_has_value():
    linhas = [["", "x"], ["a", "b"], [], ["c", ""]]
    assert cpp.filter_rows_where_first_column_has_value(linhas) == [["a", "b"], ["c", ""]]


# =========================
# format_date_value / format_number_value
# =========================
def test_format_date_value():
    assert cpp.format_date_value("30/06/2026 - terça-feira") == "30/06/2026"
    assert cpp.format_date_value("sem data") == "sem data"
    assert cpp.format_date_value(123) == 123


def test_format_number_value():
    assert cpp.format_number_value(1.5) == "1,5"
    assert cpp.format_number_value(10) == 10
    assert cpp.format_number_value("3.14") == "3,14"
    assert cpp.format_number_value("-2.5") == "-2,5"
    assert cpp.format_number_value("abc") == "abc"


# =========================
# remove_duplicate_rows
# =========================
def test_remove_duplicate_rows_mantem_primeira():
    linhas = [["a", "1"], ["a", "1"], ["b", "2"], ["a", "1"]]
    assert cpp.remove_duplicate_rows(linhas) == [["a", "1"], ["b", "2"]]


# =========================
# merge_csvs / parse_csv_text / normalize_header
# =========================
def test_normalize_header():
    assert cpp.normalize_header(["  Nome ", "VALOR"]) == ["nome", "valor"]


def test_merge_csvs_mesmo_cabecalho():
    c1 = "h1,h2\na,b\nc,d\n"
    c2 = "h1,h2\ne,f\n"
    resultado = cpp.merge_csvs([c1, c2])
    assert resultado[0] == ["h1", "h2"]
    assert ["a", "b"] in resultado
    assert ["e", "f"] in resultado
    # cabeçalho aparece uma única vez (segundo arquivo tem header idêntico)
    assert sum(1 for r in resultado if r == ["h1", "h2"]) == 1


def test_merge_csvs_vazio():
    assert cpp.merge_csvs([]) == []


def test_get_first_csv_row_raw():
    assert cpp.get_first_csv_row_raw("a;b;c\nd;e;f") == "a;b;c"


def test_get_first_csv_row_raw_campo_com_quebra():
    conteudo = 'a;"x\ny";c\nlinha2'
    assert cpp.get_first_csv_row_raw(conteudo) == 'a;"x\ny";c'
