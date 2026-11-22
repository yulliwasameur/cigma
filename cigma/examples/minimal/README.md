# Minimal end-to-end example

This example deliberately splits one real endpoint across CMDB and TLS records.
CIGMA resolves both observations using `endpoint_uri`, validates the direct
`HOSTS`, `PRESENTS`, and `USES` claims, then derives
`service USES algorithm` through `HOSTS o PRESENTS o USES`.

Regenerate the example input and output:

```bash
PYTHONPATH=src python examples/minimal/generate.py
PYTHONPATH=src python -m cigma.cli run \
  --config configs/default.yaml \
  --public examples/minimal/public \
  --output examples/minimal/output \
  --methods cigma
```
