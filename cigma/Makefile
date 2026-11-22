PYTHON ?= python
PYTHONPATH := src

.PHONY: install generate test campaign paper-macros figures scaling seal-demo clean verify

install:
	$(PYTHON) -m pip install -e ".[dev]"

generate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m cigma.benchmark data/cigma_lab

test: generate
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q

campaign: generate
	rm -rf results/default
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m cigma.experiment --data data/cigma_lab --config configs/default.yaml --output results/default
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_paper_macros.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/plot_robustness.py

paper-macros:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_paper_macros.py

figures:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/plot_robustness.py

scaling: generate
	rm -rf results/scaling
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/benchmark_scaling.py

seal-demo: generate
	rm -rf results/seal-demo
	mkdir -p results/seal-demo
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m cigma.cli seal --public data/cigma_lab/public --config configs/default.yaml --output results/seal-demo/predictions > results/seal-demo/seal_stdout.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m cigma.cli evaluate-seal --seal-dir results/seal-demo/predictions --public data/cigma_lab/public --oracle data/cigma_lab/oracle --oracle-sha256 "$$(PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c 'from cigma.io import sha256_tree; print(sha256_tree("data/cigma_lab/oracle"))')" --config configs/default.yaml --output results/seal-demo/evaluation > results/seal-demo/evaluation_stdout.json

verify: test campaign seal-demo
	@echo "CIGMA clean-room verification completed."

clean:
	rm -rf .pytest_cache build dist src/*.egg-info results/default results/seal-demo
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
