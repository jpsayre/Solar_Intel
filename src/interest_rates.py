import pandas as pd

# === FILE PATHS ===
input_file = "/Users/jeffs/Projects/SolarProject/data/raw/MORTGAGE30US.csv"          # <-- replace with your file path
output_file = "/Users/jeffs/Projects/SolarProject/data/final/avg_yearly_interest.csv"

# ==========================
# LOAD DATA
# ==========================

df = pd.read_csv(input_file)

# ==========================
# PARSE DATE COLUMN
# ==========================

# Your file uses: observation_date
df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")

# Extract year from date
df["year"] = df["observation_date"].dt.year

# ==========================
# CLEAN RATE COLUMN
# ==========================

# Your rate column is: MORTGAGE30US
df["MORTGAGE30US"] = pd.to_numeric(df["MORTGAGE30US"], errors="coerce")

# ==========================
# FILTER YEARS 2012–2016
# ==========================

filtered = df[df["year"].between(2012, 2026)]

# ==========================
# CALCULATE YEARLY AVERAGE
# ==========================

result = (
    filtered
    .groupby("year", as_index=False)["MORTGAGE30US"]
    .mean()
    .rename(columns={"MORTGAGE30US": "average_rate"})
    .sort_values("year")
)

# ==========================
# SAVE OUTPUT
# ==========================

result.to_csv(output_file, index=False)

print("Finished.")
print(result)