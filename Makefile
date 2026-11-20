TAG ?= latest
IMAGE := entrepataseturnos/entrepataseturnos-mcp-server

.PHONY: sync lint test run image docker-run deploy

sync:
	uv sync

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy

test:
	uv run pytest

run:
	uv run entrepataseturnos-mcp

image:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm --env-file .env -p 8000:8000 $(IMAGE):$(TAG)

deploy:
	kubectl apply -k deploy/k8s
