# Documentación de dominio

Cómo consumen los skills de ingeniería la documentación de dominio de este repositorio al explorarlo.

## Antes de explorar, leer

- **`CONTEXT.md`** en la raíz del repositorio: el glosario del dominio.
- **`docs/adr/`**: los ADR que toquen el área en la que se va a trabajar.

Este repositorio es single-context: no existe `CONTEXT-MAP.md` ni un `CONTEXT.md` por paquete.

## Estructura de archivos

```
/
├── CONTEXT.md
├── docs/adr/
│   └── NNNN-titulo.md
└── database/
```

## Usar el vocabulario del glosario

Cuando un resultado nombre un concepto del dominio, en el título de un issue, en una propuesta de refactorización, en una hipótesis o en el nombre de un test, hay que usar el término tal como está definido en `CONTEXT.md`, sin derivar a los sinónimos que el glosario descarte.

Si el concepto que se necesita todavía no está en el glosario, eso es una señal: o se está inventando lenguaje que el proyecto no usa, o hay un hueco real que anotar para `/domain-modeling`.

## Señalar conflictos con ADR

Si un resultado contradice un ADR existente, hay que sacarlo a la superficie de forma explícita en lugar de sobrescribirlo en silencio:

> _Contradice el ADR-0002 (PostgreSQL como persistencia), pero vale la pena reabrirlo porque…_
