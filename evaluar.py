"""Laboratorio local: decisiones sobre alertas ficticias, sin conexión a Zabbix."""
import argparse
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from importlib.metadata import version

BASE = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(BASE / ".cache" / "huggingface"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caso", help="ID de una alerta; por defecto evalúa todas")
    parser.add_argument("--offline", action="store_true", help="Usar solo modelos descargados")
    args = parser.parse_args()
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    cases = json.loads((BASE / "alertas.json").read_text())
    questions = json.loads((BASE / "preguntas.json").read_text())
    if args.caso:
        cases = [c for c in cases if c["id"] == args.caso]
        if not cases:
            parser.error("ID no encontrado en alertas.json")

    import torch
    from laya import Router

    torch.set_num_threads(2)
    router = Router(device="cpu", max_loaded=1)
    print("Cargando modelo multilingüe (la primera vez requiere descarga)...", flush=True)
    started = time.perf_counter()
    router.load("multilingual")
    load_seconds = time.perf_counter() - started
    print(f"Modelo cargado en {load_seconds:.1f} s", flush=True)
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = router.predict(case["state"], questions, model="multilingual")
        elapsed = time.perf_counter() - started
        answers = result["answers"]
        category = answers["categoria"]["choice"]
        probability = float(answers["impacto_confirmado"]["noul"])
        checks = {
            "categoria": category == case["expected"]["categoria"],
            "impacto_confirmado": (probability >= 0.5) == case["expected"]["impacto_confirmado"],
        }
        rows.append({"id": case["id"], "state": case["state"], "expected": case["expected"],
                     "result": result, "seconds": elapsed, "checks": checks})
        print(f"{case['id']:24} categoría={category:16} gravedad={answers['gravedad']['score']:.2f}/3 "
              f"P(impacto)={probability:.3f} tiempo={elapsed:.2f}s aciertos={sum(checks.values())}/2", flush=True)
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
              "versions": {p: version(p) for p in ("laya", "torch", "transformers")},
              "model": "multilingual", "device": "cpu", "threads": 2,
              "load_seconds": load_seconds, "questions": questions,
              "note": "Casos sintéticos exploratorios. Umbral 0.5 ilustrativo, no calibrado para producción. Gravedad no puntuada como acierto.",
              "rows": rows}
    output = BASE / "resultados"
    output.mkdir(exist_ok=True)
    path = output / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"\nAciertos: {sum(sum(r['checks'].values()) for r in rows)}/{len(rows)*2}")
    print(f"Resultados completos: {path}")


if __name__ == "__main__":
    main()
