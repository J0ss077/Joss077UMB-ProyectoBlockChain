"""Cuentas de usuario: credenciales, modelo, persistencia y servicio.

`credentials` y `model` son reglas puras y `ports` describe lo que el servicio
espera; `postgres` es el adaptador y `service` compone el registro, el ingreso y
el alta moderada (REQ-30 a REQ-33). El paquete no importa Flask ni `src.web`: la
autorización es de la presentación y las cuentas no la conocen (REQ-29).
"""
