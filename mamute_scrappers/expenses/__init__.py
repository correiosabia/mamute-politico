"""Logica compartilhada dos gastos da cota parlamentar (CS-57).

Os crawlers de Camara (camara_crawler/expenses.py) e Senado
(senado_crawler/expenses.py) produzem o mesmo payload e persistem pelo mesmo
upsert daqui — a unica diferenca entre as casas e o parse da fonte.
"""
