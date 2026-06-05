"""Esquema do event log padrão que o núcleo entende.

Toda fonte de dados, após passar por um conector, deve produzir um
DataFrame pandas com pelo menos as três colunas obrigatórias abaixo.
"""

CASE_ID = "case_id"
ACTIVITY = "activity"
TIMESTAMP = "timestamp"
RESOURCE = "resource"

REQUIRED_COLUMNS = [CASE_ID, ACTIVITY, TIMESTAMP]
