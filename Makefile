.PHONY: up reset test seed-report profiles evaluate

up:
	docker compose up --build

reset:
	docker compose run --rm api python -m app.reset

test:
	docker compose run --rm api pytest

seed-report:
	docker compose run --rm api python -m app.import_seed

evaluate:
	docker compose run --rm api python -m app.evaluate

profiles:
	cd api && python -m app.generate_profiles --seed-dir ../data/seed
