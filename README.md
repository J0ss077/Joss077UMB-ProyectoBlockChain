# Sistema Transaccional Basado en Blockchain

Diseño y prototipo de un sistema transaccional que valida e integra transacciones sin depender de una autoridad central.

## Resumen

Los sistemas transaccionales tradicionales dependen de una entidad central para validar cada operación, lo que crea un punto único de fallo. Este proyecto propone una arquitectura alternativa basada en blockchain: wallets con par de llaves, transacciones firmadas, validación automática y bloques enlazados por hash, todo corriendo en un solo nodo local.

## Qué es

Un prototipo funcional (no una red blockchain de producción) que implementa las operaciones básicas de un sistema transaccional descentralizado:

- Registro de wallets.
- Creación de transacciones entre wallets.
- Validación automática de cada transacción.
- Agrupación de transacciones válidas en bloques.
- Encadenamiento de bloques por hash.
- Verificación de integridad de toda la cadena.
- Consulta de historial de transacciones.

## La idea

En vez de confiar la integridad de los datos a un servidor central, cada bloque guarda el hash del bloque anterior. Si alguien altera una transacción ya confirmada, el hash del bloque deja de coincidir y la cadena queda marcada como inválida. No hay red P2P ni consenso distribuido real: el objetivo es aislar y entender los mecanismos de integridad (hash encadenado, validación automática, inmutabilidad) antes de escalar a un sistema distribuido.

La arquitectura se organiza en capas:

- **UI**: interacción del usuario (crear transacciones, ver historial).
- **Lógica de negocio**: reglas de validación de transacciones.
- **Gestión de datos**: pool de transacciones pendientes y generación de bloques.
- **Persistencia**: almacenamiento de wallets, transacciones y bloques.

## Arquitectura

```
                Usuario
                   │
                   ▼
   ┌───────────────────────────────┐
   │           Aplicación          │
   │  ┌────────┐      ┌──────────┐ │
   │  │   UI   │ ───▶ │ Lógica de│ │
   │  │        │      │ negocio  │ │
   │  └────────┘      └──────────┘ │
   └───────────────┬───────────────┘
                    │
                    ▼
   ┌───────────────────────────────┐
   │          Persistencia         │
   │  ┌────────────┐  ┌──────────┐ │
   │  │ Acceso a   │─▶│ Base de  │ │
   │  │ datos      │  │ datos    │ │
   │  └────────────┘  └──────────┘ │
   └───────────────────────────────┘
```

## Alcance actual

- 1 nodo, ejecución local.
- Sin red P2P ni consenso distribuido.
- Sin validación legal (transacciones simuladas).
- CRUD completo sobre transacciones.

## Stack

- **Lenguaje**: Python 3.11+
- **Hashing**: `hashlib` (SHA-256) para el encadenamiento de bloques
- **Persistencia**: SQLite o JSON (por definir según volumen de datos)
- **Pruebas**: `pytest`

## Requisitos

- Python 3.11 o superior
- pip
- git

## Estructura del proyecto (prototipado)

```
├── src/
│   ├── wallet.py         # generación y gestión de wallets
│   ├── transaction.py    # creación y validación de transacciones
│   ├── block.py          # estructura de bloque y hash encadenado
│   ├── blockchain.py     # cadena, verificación de integridad
│   ├── persistence.py    # almacenamiento (SQLite / JSON)
│   └── main.py           # punto de entrada
├── tests/
├── requirements.txt
└── README.md
```

## Comandos de lanzamiento (prototipado)

Aún no hay código implementado, estos son los comandos previstos para cuando el prototipo esté listo.

```bash
# Clonar el repositorio
git clone <url-del-repo>
cd <repo>

# Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el prototipo
python src/main.py

# Correr pruebas
pytest tests/
```

## Ejemplo de uso (previsto)

```python
from src.wallet import Wallet
from src.blockchain import Blockchain

# Crear wallets
alice = Wallet()
bob = Wallet()

# Iniciar la cadena
chain = Blockchain()

# Crear y registrar una transacción
tx = alice.create_transaction(to=bob.public_key, amount=50)
chain.add_transaction(tx)

# Minar el bloque pendiente
chain.mine_pending_transactions()

# Verificar integridad de toda la cadena
print(chain.is_valid())   # True
```

## Consideraciones de seguridad

- Cada wallet se identifica por un par de llaves pública/privada; la llave privada nunca se comparte ni se persiste en texto plano.
- Cada bloque guarda el hash del bloque anterior, así que modificar una transacción confirmada invalida toda la cadena a partir de ese punto.
- La validación automática rechaza transacciones mal formadas o firmadas incorrectamente antes de que entren al pool de pendientes.
- Este prototipo no reemplaza un sistema de producción: no hay consenso distribuido, por lo que la integridad depende del propio nodo.



## Autores :)

- José Camilo Pérez Daza
- Sebastián Fernando Revelo Meneses
- Tomás Alejandro Santiago Reyes
