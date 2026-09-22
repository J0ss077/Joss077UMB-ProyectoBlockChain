# Operaciones del entorno local del sistema transaccional.
# Cubre la base de datos, el entorno de Python y la comprobación del backend.

SHELL := /bin/bash
COMPOSE ?= docker compose
ENV_FILE := .env
VENV := .venv

ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

PSQL := $(COMPOSE) exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

.DEFAULT_GOAL := help

.PHONY: help up down reset logs psql tables schema counts venv backend

help: ## Muestra los comandos disponibles
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-8s %s\n", $$1, $$2}'

up: ## Levanta PostgreSQL en segundo plano
	$(COMPOSE) up -d

down: ## Detiene el contenedor conservando los datos
	$(COMPOSE) down

reset: ## Destruye el volumen y vuelve a aplicar esquema y seed
	$(COMPOSE) down -v
	$(COMPOSE) up -d

logs: ## Sigue los logs del contenedor de base de datos
	$(COMPOSE) logs -f db

psql: ## Abre una sesión interactiva de psql dentro del contenedor
	$(PSQL)

tables: ## Lista las tablas creadas
	$(PSQL) -c "\dt"

schema: ## Describe las tres tablas del ledger
	$(PSQL) -c "\d wallets"
	$(PSQL) -c "\d blocks"
	$(PSQL) -c "\d transactions"

counts: ## Cuenta las filas de wallets, blocks y transactions
	$(PSQL) -c "SELECT (SELECT count(*) FROM wallets) AS wallets, (SELECT count(*) FROM blocks) AS blocks, (SELECT count(*) FROM transactions) AS transactions;"

venv: ## Crea el entorno virtual e instala las dependencias del backend
	python -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

backend: ## Comprueba la conexión del backend y cuenta las filas
	$(VENV)/bin/python -m src.main
