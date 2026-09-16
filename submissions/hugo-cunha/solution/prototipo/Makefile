.PHONY: setup data train run test check-tracked clean
PY=uv run python

setup:
	uv sync --group dev
	$(MAKE) data

data:
	@test -f data/customer_support_tickets.csv || unzip -o -q data/ds1.zip -d data
	@test -f data/all_tickets_processed_improved_v3.csv || unzip -o -q data/ds2.zip -d data
	@cd data && shasum -a 256 -c SHA256SUMS

train: data
	$(PY) scripts/train.py
	$(PY) scripts/diagnostico_ds1.py

run: data
	@test -f models/index.pkl || $(PY) scripts/train.py
	uv run uvicorn app.api:app --host 0.0.0.0 --port 8010

test:
	uv run pytest -q

check-tracked:
	@n=$$(git ls-files . | wc -l | tr -d " "); echo "tracked files: $$n"; test $$n -gt 0

clean:
	rm -rf models/*.pkl data/*.csv board.db
