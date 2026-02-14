"""
Join image classification results onto test_images_dataset.

- Left join (keep ALL rows from test_images_dataset)
- Join key: original_index
- Brings over columns from image_classification_tests.csv
  (e.g., bbox, marker, image_name)
- Writes a new CSV (does NOT overwrite inputs unless you choose to)

Install:
  pip install pandas
"""

from pathlib import Path
import pandas as pd

# --------------------
# Configuration
# --------------------

TEST_IMAGES_DATASET = "data/working/test_images_dataset.csv"
CLASSIFICATION_RESULTS = "data/working/image_classification_tests.csv"
OUTPUT_PATH = "data/working/test_images_dataset_with_image_classifications.csv"

JOIN_KEY = "original_index"


# --------------------
# Main
# --------------------

def main() -> None:
    project_root = Path(__file__).resolve().parent.parent

    test_path = project_root / TEST_IMAGES_DATASET
    class_path = project_root / CLASSIFICATION_RESULTS
    out_path = project_root / OUTPUT_PATH

    if not test_path.exists():
        raise SystemExit(f"Missing file: {test_path}")
    if not class_path.exists():
        raise SystemExit(f"Missing file: {class_path}")

    df_test = pd.read_csv(test_path)
    df_class = pd.read_csv(class_path)

    if JOIN_KEY not in df_test.columns:
        raise SystemExit(f"'{JOIN_KEY}' not found in {TEST_IMAGES_DATASET}")
    if JOIN_KEY not in df_class.columns:
        raise SystemExit(f"'{JOIN_KEY}' not found in {CLASSIFICATION_RESULTS}")

    # Ensure consistent join key type
    df_test[JOIN_KEY] = pd.to_numeric(df_test[JOIN_KEY], errors="coerce")
    df_class[JOIN_KEY] = pd.to_numeric(df_class[JOIN_KEY], errors="coerce")

    # Drop duplicate classification rows per original_index (keep first)
    df_class = df_class.drop_duplicates(subset=[JOIN_KEY])

    # Left join: keep ALL rows from test_images_dataset
    df_out = df_test.merge(
        df_class,
        on=JOIN_KEY,
        how="left",
        suffixes=("", "_image_classification"),
    )

    df_out.to_csv(out_path, index=False)

    print(
        f"Join complete.\n"
        f"- Input rows: {len(df_test)}\n"
        f"- Output rows: {len(df_out)}\n"
        f"- Saved to: {out_path}"
    )


if __name__ == "__main__":
    main()
