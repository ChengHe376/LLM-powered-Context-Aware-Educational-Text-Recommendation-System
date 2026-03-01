import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re
from datasets import load_dataset
from config import RAW_DIR, ensure_dirs



DATASET_ID = "izumi-lab/open-text-books"

def safe_dir_name(dataset_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "__", dataset_id)

def main():
    ensure_dirs()

    local_name = safe_dir_name(DATASET_ID)
    save_path = RAW_DIR / f"hf_{local_name}"

    print(f"[1/3] Loading dataset: {DATASET_ID}")
    ds = load_dataset(DATASET_ID)

    print(f"[2/3] Saving to: {save_path}")
    ds.save_to_disk(str(save_path))

    print("[3/3] Done.")
    print(ds)

    for split in ds.keys():
        print(f"Split: {split}, columns: {ds[split].column_names}")

if __name__ == "__main__":
    main()
