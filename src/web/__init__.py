"""Presentación del ledger: la aplicación Flask con las cinco rutas del eje.

`app.py` arma la aplicación y `__main__.py` la levanta como punto de entrada
(`python -m src.web`). Este paquete separa las dos cosas justamente para que el
módulo de las rutas no tenga que conocer la capa de persistencia (REQ-29).
"""
