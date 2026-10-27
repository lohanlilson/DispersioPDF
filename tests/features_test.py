"""Roda o autoteste do programa (o mesmo que o build executa no .exe gerado)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dispersio import selftest

sys.exit(selftest.run())
