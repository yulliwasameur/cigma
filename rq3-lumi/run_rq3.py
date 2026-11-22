#!/usr/bin/env python3
"""RQ3 étendu : interroge un modèle servi par vLLM (API compatible OpenAI) avec le prompt et le schéma FIGÉS,
écrit chaque sortie brute, puis la fait valider par le validateur déterministe de CIGMA.
Le modèle ne touche jamais au graphe principal (graph_mutated=false), comme dans l'étude d'origine."""
import argparse, hashlib, json, pathlib, time, urllib.request, urllib.error

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--input", required=True)
ap.add_argument("--temperature", type=float, required=True); ap.add_argument("--calls", type=int, default=30)
ap.add_argument("--seed-base", type=int, default=20261122); ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--out", default="runs")
a = ap.parse_args()

prompt = pathlib.Path("frozen/prompt.txt").read_text()                 # prompt de l'étude d'origine (à verser tel quel)
schema = json.loads(pathlib.Path("frozen/candidate_schema.json").read_text())
payload_in = pathlib.Path(f"frozen/inputs/{a.input}.json").read_text()  # observations publiques + IDs + vocabulaire fermé
out = pathlib.Path(a.out) / a.model.replace("/", "__") / a.input / f"T{a.temperature}"
out.mkdir(parents=True, exist_ok=True)

base = f"http://127.0.0.1:{a.port}"
def post(path, obj):
    r = urllib.request.Request(base + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=1200).read())
msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": payload_in}]
ctx = json.loads(urllib.request.urlopen(base + "/v1/models").read())["data"][0].get("max_model_len", 16384)
n_in = post("/tokenize", {"model": a.model, "messages": msgs}).get("count")
max_tokens = max(256, min(8000, ctx - n_in - 64))   # la réponse tient toujours dans la fenêtre du modèle
(out / "context.json").write_text(json.dumps({"max_model_len": ctx, "prompt_tokens": n_in, "max_tokens": max_tokens}))
for i in range(a.calls):
    body = {"model": a.model, "temperature": a.temperature, "seed": a.seed_base + i, "max_tokens": max_tokens,
            "messages": msgs,
            "response_format": {"type": "json_schema", "json_schema": {"name": "cigma_candidates", "schema": schema}}}
    req = urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=1200).read())
    except urllib.error.HTTPError as e:            # erreur serveur conservée comme sortie invalide, pas d'arrêt
        resp = {"http_error": e.code, "body": e.read().decode(errors="replace")[:2000]}
    dt = time.time() - t0
    rec = {"call": i, "seed": a.seed_base + i, "latency_s": round(dt, 3), "request": body, "response": resp}
    raw = json.dumps(rec, sort_keys=True)
    (out / f"call-{i:02d}.json").write_text(raw)
    with open(out / "MANIFEST.sha256", "a") as m:
        m.write(f"{hashlib.sha256(raw.encode()).hexdigest()}  call-{i:02d}.json\n")
print(f"{a.calls} appels écrits dans {out}")
# Validation : python -m cigma.validate_candidates --runs <out> --input <a.input>  (module du code CIGMA d'origine)
