# CIGMA — artefact ICISSP 2027. Chaque cible régénère une partie des résultats.
PY ?= python3
L1 = l1-deployed

.PHONY: cigma-lab extensions l1-up l1-collect l1-predict l1-seal l1-evaluate l1-down paper
cigma-lab:            ## banc contrôlé CIGMA-Lab : 61 tests, campagne complète, scellement (reconstruction clean-room v0.1.0)
	cd cigma && $(MAKE) verify && rm -rf ../results/cigma-lab && cp -r results/default ../results/cigma-lab
extensions:           ## idées ICISSP : fiabilités apprises, multi-outils, ordre sans casse, deux horloges, Merkle, vérification ciblée
	cd cigma && PYTHONPATH=src $(PY) scripts/run_extensions.py --output ../results/extensions && PYTHONPATH=src $(PY) scripts/run_extensions_v2.py --output ../results/extensions

l1-up:                ## système déployé : kind + Istio mTLS + Online Boutique
	cd $(L1) && ./cluster_up.sh
l1-collect:           ## collecte des six familles de sources (après 15 min de trafic)
	cd $(L1) && ./collect/collect_all.sh
l1-predict:           ## prédictions de toutes les méthodes sur les seules entrées publiques
	cd cigma && PYTHONPATH=src $(PY) -m cigma.cli seal --public ../$(L1)/out/public --config configs/default.yaml --output ../$(L1)/out/predictions
l1-seal:              ## scellement AVANT l'oracle
	cd $(L1) && $(PY) seal/seal.py out/predictions out/public ../configs/frozen.yaml
l1-evaluate:          ## refuse de tourner si le scellement est rompu
	cd $(L1) && $(PY) seal/verify_seal.py out/predictions out/public && \
	$(PY) -m cigma.evaluate --predictions out/predictions --oracle out/oracle --out ../results/l1
l1-down:
	cd $(L1) && ./cluster_down.sh
paper:                ## compile le papier
	cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main

extensions-v3:
	cd cigma && PYTHONPATH=src python scripts/run_extensions_v3.py --output ../results/extensions

figures:
	cd cigma && PYTHONPATH=src python scripts/make_figures.py

check-paper:
	cd cigma && PYTHONPATH=src python scripts/check_paper_numbers.py

zk:
	cd cigma/zk && bash setup.sh && bash prove.sh
