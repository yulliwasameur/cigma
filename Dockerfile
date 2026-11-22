# CIGMA artifact — reproduces every number of the ICISSP 2027 paper that does not need
# the deployed system (L1) or the LUMI model runs (RQ3).
FROM python:3.11-slim
WORKDIR /cigma
COPY cigma/ /cigma/
RUN pip install --no-cache-dir -e '.[dev]' ortools SALib hypothesis dilithium-py
# default: tests + clean-room campaign + all extension experiments
CMD ["bash", "-lc", "make verify && PYTHONPATH=src python scripts/run_extensions.py --output results/extensions && PYTHONPATH=src python scripts/run_extensions_v2.py --output results/extensions && PYTHONPATH=src python scripts/run_extensions_v3.py --output results/extensions"]
