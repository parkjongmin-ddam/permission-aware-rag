from pathlib import Path
import yaml
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
with open(PROJECT_ROOT / "data" / "documents.yaml", encoding="utf-8") as f:
    docs = yaml.safe_load(f)["documents"]

target_ids = ["DOC-044", "DOC-016", "DOC-008", "DOC-034"]
for d in docs:
    if d["id"] in target_ids:
        printable = {k: v for k, v in d.items() if k != "body"}
        print(json.dumps(printable, indent=2, ensure_ascii=False))
        print()