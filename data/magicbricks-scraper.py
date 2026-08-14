import csv
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

CITY = "Mumbai"
BEDROOMS = "1,2,3"
BUDGET_MIN = "10-Lacs"
BUDGET_MAX = "20-Lacs"
LIMIT = 30


def build_search_url(city: str, bedrooms: str, budget_min: str, budget_max: str) -> str:
    return (
        "https://www.magicbricks.com/property-for-sale/residential-real-estate?"
        f"bedroom={bedrooms}&proptype=Multistorey-Apartment,Builder-Floor-Apartment,"
        f"Penthouse,Studio-Apartment,Residential-House,Villa&cityName={city}&"
        f"BudgetMin={budget_min}&BudgetMax={budget_max}"
    )


def run_magicbricks_scraper(city: str, bedrooms: str, budget_min: str, budget_max: str, limit: int) -> Path:
    base_dir = Path(__file__).resolve().parent
    json_dir = base_dir / "json"
    csv_dir = base_dir / "csv"
    json_dir.mkdir(exist_ok=True)
    csv_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_city = city.lower().replace(" ", "-")

    json_path = json_dir / f"magicbricks_{safe_city}_{timestamp}.json"
    input_path = base_dir / f"magicbricks_{safe_city}_{timestamp}.input.json"

    search_url = build_search_url(city, bedrooms, budget_min, budget_max)
    payload = {"searchUrls": [search_url], "resultsLimit": limit}

    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("🔄 Running Apify scraper...")

    apify_cmd = shutil.which("apify")
    if not apify_cmd:
        apify_cmd = str(Path.home() / "AppData" / "Roaming" / "npm" / "apify.ps1")

    powershell_cmd = (
        f'& "{apify_cmd}" call krazee_kaushik/magicbricks-search-results-scraper '
        f'--silent --output-dataset --input-file "{input_path}"'
    )

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if input_path.exists():
        input_path.unlink()

    if result.returncode != 0:
        stderr_text = (result.stderr or result.stdout or "Unknown Apify error").strip()
        raise RuntimeError(f"Apify call failed: {stderr_text}")

    output_text = (result.stdout or "").strip()
    if not output_text:
        raise RuntimeError("Apify returned no dataset output.")

    try:
        data = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Apify output is not valid JSON: {exc}") from exc

    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Scraper finished. JSON saved to: {json_path}")
    return json_path


def convert_json_to_csv(json_path: Path) -> Path:
    with json_path.open("r", encoding="utf-8") as file:
        raw_data = json.load(file)

    if isinstance(raw_data, dict) and "items" in raw_data:
        items = raw_data["items"]
    elif isinstance(raw_data, list):
        items = raw_data
    else:
        items = [raw_data]

    if not items:
        raise ValueError(f"The JSON file '{json_path}' contains no data entries.")

    all_keys = set()
    for item in items:
        if isinstance(item, dict):
            all_keys.update(item.keys())

    headers = sorted(all_keys)
    csv_dir = json_path.parent.parent / "csv"
    csv_dir.mkdir(exist_ok=True)
    csv_path = csv_dir / f"{json_path.stem}.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(headers)

        for item in items:
            if not isinstance(item, dict):
                writer.writerow([""] * len(headers))
                continue

            row = []
            for field in headers:
                value = item.get(field, "")
                if isinstance(value, (dict, list)):
                    row.append(json.dumps(value, ensure_ascii=False))
                else:
                    row.append(value)
            writer.writerow(row)

    print(f"✅ CSV saved to: {csv_path}")
    return csv_path


def main() -> None:
    json_path = run_magicbricks_scraper(CITY, BEDROOMS, BUDGET_MIN, BUDGET_MAX, LIMIT)
    convert_json_to_csv(json_path)


if __name__ == "__main__":
    main()

