#!/bin/bash
# RQ5 CIGMA : un job par modèle.
# usage : sbatch --gpus-per-node=<gcd> --export=ALL,MODEL=<id>,TP=<tp> run_rq3.sbatch
#SBATCH --account=project_465003715
#SBATCH --partition=small-g
#SBATCH --job-name=cigma-rq5
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=7
#SBATCH --mem=0
#SBATCH --time=06:00:00
#SBATCH --output=logs/%x-%j.out
set -uo pipefail
source /scratch/project_465003715/provguard/code/slurm/env.sh
export HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0   # téléchargement si absent du cache
cd "$SLURM_SUBMIT_DIR"; mkdir -p logs runs
PORT=$((8000 + SLURM_JOB_ID % 1000)); TAG=$(echo "$MODEL" | tr '/' '_')
singularity exec $BIND $SIF bash -c "
source \$PG_VENV/bin/activate
python -c \"from huggingface_hub import snapshot_download as s; p=s('$MODEL', allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken']); print('SNAPSHOT', p)\" > logs/dl-$TAG-$SLURM_JOB_ID.txt 2>&1
mkdir -p \$MIOPEN_USER_DB_PATH
vllm serve $MODEL --port $PORT --dtype bfloat16 --tensor-parallel-size ${TP:-1} --max-model-len ${MAXLEN:-32768} --seed 20261122 --gpu-memory-utilization 0.90 > logs/vllm-$TAG-$SLURM_JOB_ID.log 2>&1 &
for i in \$(seq 1 180); do curl -s localhost:$PORT/v1/models >/dev/null && break; sleep 10; done
for INPUT in cigma-lab-complete cigma-lab-no-path cigma-lab-injected; do
  for T in 0.0 0.7; do
    python run_rq5.py --model $MODEL --input \$INPUT --temperature \$T --calls 30 --port $PORT
  done
done
python -c \"import json,pathlib,sys; snap=open('logs/dl-$TAG-$SLURM_JOB_ID.txt').read().split('SNAPSHOT')[-1].strip(); json.dump({'model':'$MODEL','snapshot':snap,'revision':pathlib.Path(snap).name,'job':'$SLURM_JOB_ID','sif_sha256':'$SIF_SHA256','tp':${TP:-1}}, open('runs/meta-$TAG.json','w'), indent=1)\"
"
sacct -j "$SLURM_JOB_ID" --format=JobID,Elapsed,NNodes,AllocTRES%60 > logs/sacct-$SLURM_JOB_ID.txt
