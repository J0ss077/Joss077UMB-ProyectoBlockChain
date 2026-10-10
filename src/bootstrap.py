"""Arranque explícito del ledger: asegura el bloque génesis (REQ-14).

El génesis es un dato calculado, no DDL, así que no vive en `db/init.sql`: lo crea
la aplicación con este punto de entrada y de forma idempotente, para que correrlo
dos veces no duplique el eslabón cero (decisión 7).

Uso: `python -m src.bootstrap`.
"""
from src.domain.blockchain import ensure_genesis
from src.persistence.factory import ledger


def main() -> None:
    """Asegura el génesis e informa con qué eslabón quedó la cadena."""
    with ledger() as chain:
        genesis = ensure_genesis(chain)
        print(f"génesis listo: índice {genesis.block_index}, hash {genesis.hash}")


if __name__ == "__main__":
    main()
