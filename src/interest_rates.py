import pandas as pd
from pathlib import Path


def run(config=None):
    """Compute average yearly mortgage interest rates from FRED data.

    Args:
        config: CountyConfig object. If None, uses legacy hardcoded paths.
    """
    if config:
        input_file = config.mortgage_csv
        output_file = str(config.avg_yearly_interest_path)
        year_min = config.year_min
        year_max = config.year_max
        config.ensure_dirs()
    else:
        project_root = Path(__file__).resolve().parent.parent
        input_file = str(project_root / "data" / "raw" / "MORTGAGE30US.csv")
        output_file = str(project_root / "data" / "final" / "avg_yearly_interest.csv")
        year_min = 2012
        year_max = 2026

    df = pd.read_csv(input_file)
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["year"] = df["observation_date"].dt.year
    df["MORTGAGE30US"] = pd.to_numeric(df["MORTGAGE30US"], errors="coerce")

    filtered = df[df["year"].between(year_min, year_max)]

    result = (
        filtered
        .groupby("year", as_index=False)["MORTGAGE30US"]
        .mean()
        .rename(columns={"MORTGAGE30US": "average_rate"})
        .sort_values("year")
    )

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    print(f"Interest rates: {len(result)} years written to {output_file}")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="County config name or path")
    args = parser.parse_args()

    if args.config:
        from pipeline_config import load_config
        run(load_config(args.config))
    else:
        run()
