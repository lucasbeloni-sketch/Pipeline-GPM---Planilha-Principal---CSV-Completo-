"""
Coloca a raiz do repositório no sys.path para que os testes possam importar
os módulos do pipeline (common, compilador_*, bloco3_*) diretamente.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
