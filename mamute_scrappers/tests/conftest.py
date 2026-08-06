"""Configuracao compartilhada de pytest para mamute_scrappers/tests/.

Garante que `mamute_scrappers` seja importavel como pacote.

Sem isto, `pytest mamute_scrappers/tests/` (a forma que o CI usa) falha com
ModuleNotFoundError, enquanto `python -m pytest ...` passa — porque o `-m`
insere o diretorio corrente no sys.path e o comando direto nao. Os testes de
crawler mais antigos nao dependiam disso por carregarem os modulos por caminho
de arquivo, via importlib.

Espelha o que api/tests/conftest.py ja faz do lado da API.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Raiz do repositorio = parent de mamute_scrappers/
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
