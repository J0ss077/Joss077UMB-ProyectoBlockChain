# Firmar transacciones y verificar firmas

Status: ready-for-agent

## Contexto

El esquema guarda una firma por transacción y exige que no esté vacía, pero nada la produce ni la valida. El diseño pide autenticación de origen con ECDSA: la llave privada firma y la llave pública verifica.

La generación de llaves tampoco está implementada. El nodo custodia el material cifrado de todas las llaves privadas, según los límites conocidos de `docs/arquitectura.md`.

## Qué hacer

- Generar el par de llaves al registrar una wallet y guardar la privada cifrada.
- Firmar una transacción con la llave privada del emisor.
- Verificar la firma contra la llave pública antes de admitir la transacción.

Esto suma la dependencia `cryptography`, que hoy no está declarada en `pyproject.toml`.

## Done cuando

Una transacción firmada por su emisor se verifica, y una firmada por otra wallet se rechaza.

## Comments
