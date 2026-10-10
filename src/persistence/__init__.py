"""Capa de persistencia: adaptadores PostgreSQL detrás de protocolos (REQ-16, REQ-19).

El dominio no conoce el motor; esta capa traduce entre los objetos del dominio y
las tablas del modelo relacional del eje, y deja subir crudos los errores del
esquema.
"""
