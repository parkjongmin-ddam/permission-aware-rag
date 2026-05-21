"""Quick doc inventory for dataset expansion. Throwaway helper."""

from pathlib import Path
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    with open(PROJECT_ROOT / "data" / "documents.yaml", encoding="utf-8") as f:
        docs = yaml.safe_load(f)["documents"]

    for d in docs:
        title = d.get("title", "?")
        sub_type = d.get("sub_type", "?")
        print(f"{d['id']:8s} [{sub_type:22s}] {title[:60]}")

    print(f"\nTotal: {len(docs)} documents")


if __name__ == "__main__":
    main()