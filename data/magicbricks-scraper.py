import csv
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

CITY = "Mumbai"

# Each bedroom count is scraped separately so bands stay small enough
# that no single search URL comes close to the actor's 200 result cap.
BEDROOM_GROUPS = ["1", "2", "3", ">5"]

# Budget bands in Lacs/Crores, using the same string format MagicBricks expects.
# If any single band still returns close to 200 for a given bedroom count,
# split that band further (the script prints a warning when this happens).
BUDGET_BANDS = [
    ("20-Lacs", "50-Lacs"),
    ("50-Lacs", "80-Lacs"),
    ("80-Lacs", "1.2-Crores"),
    ("1.2-Crores", "1.8-Crores"),
    ("1.8-Crores", "2.5-Crores"),
    ("2.5-Crores", "3.5-Crores"),
]

RESULTS_LIMIT = 200  # actor's max per search URL
WARN_THRESHOLD = 190  # flag a band that likely got truncated

# Seconds to wait between actor calls, to avoid hammering the actor/site.
SLEEP_BETWEEN_CALLS = 2

# Budget guard. The actor bills per result scraped (per event).
PRICE_PER_EVENT_USD = 0.002
BUDGET_USD = 4.00
SAFETY_BUFFER_USD = 0.20  # stop a bit short of the hard limit
SPENDABLE_USD = BUDGET_USD - SAFETY_BUFFER_USD
MAX_EVENTS = int(SPENDABLE_USD / PRICE_PER_EVENT_USD)  # 1900 events at these defaults

# Bedroom groups and budget bands are both already ordered from
# most useful/likely-common first to least, so if the budget runs out
# midway, what gets skipped is the least important segment, not the most.


def build_search_url(city: str, bedrooms: str, budget_min: str, budget_max: str) -> str:
    return (
        "https://www.magicbricks.com/property-for-sale/residential-real-estate?"
        f"bedroom={bedrooms}&proptype=Multistorey-Apartment,Builder-Floor-Apartment,"
        f"Penthouse,Studio-Apartment,Residential-House,Villa&cityName={city}&"
        f"BudgetMin={budget_min}&BudgetMax={budget_max}"
    )


def get_apify_cmd() -> str:
    apify_cmd = shutil.which("apify")
    if not apify_cmd:
        apify_cmd = str(Path.home() / "AppData" / "Roaming" / "npm" / "apify.ps1")
    return apify_cmd


def run_one_search(search_url: str, base_dir: Path, tag: str, results_limit: int) -> list:
    """Run the actor for a single search URL and return its raw items."""
    input_path = base_dir / f"magicbricks_{tag}.input.json"
    payload = {
        "searchUrls": [search_url],
        "resultsLimit": results_limit,
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    apify_cmd = get_apify_cmd()
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
        raise RuntimeError(f"Apify call failed for {tag}: {stderr_text}")

    output_text = (result.stdout or "").strip()
    if not output_text:
        print(f"⚠️  No dataset output for {tag}, skipping.")
        return []

    try:
        data = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Apify output for {tag} is not valid JSON: {exc}") from exc

    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    else:
        items = [data]

    count = len(items)
    flag = " ⚠️ possibly truncated, consider splitting this band" if count >= WARN_THRESHOLD else ""
    print(f"✅ {tag}: {count} listings{flag}")
    return items


def run_all_bands(city: str) -> list:
    base_dir = Path(__file__).resolve().parent
    base_dir.mkdir(exist_ok=True)

    all_items = []
    total_calls = len(BEDROOM_GROUPS) * len(BUDGET_BANDS)
    call_num = 0
    events_used = 0

    print(f"Budget guard: ${BUDGET_USD:.2f} total, spending up to ${SPENDABLE_USD:.2f} "
          f"({MAX_EVENTS} events) and leaving a ${SAFETY_BUFFER_USD:.2f} buffer.\n")

    for bedrooms in BEDROOM_GROUPS:
        for budget_min, budget_max in BUDGET_BANDS:
            call_num += 1

            remaining_events = MAX_EVENTS - events_used
            if remaining_events <= 0:
                print(f"\n💸 Budget cap reached (${events_used * PRICE_PER_EVENT_USD:.2f} spent). "
                      f"Stopping before call {call_num}/{total_calls}: "
                      f"{bedrooms} BHK, {budget_min} to {budget_max} was skipped.")
                return all_items

            # Never request more than what's left in the budget, or the actor's own cap.
            call_limit = min(RESULTS_LIMIT, remaining_events)

            tag = f"{bedrooms.replace(',', '_').replace('>', 'gt')}_{budget_min}_{budget_max}"
            print(f"[{call_num}/{total_calls}] Scraping {city} | {bedrooms} BHK | {budget_min} to {budget_max} "
                  f"(limit {call_limit}, ${events_used * PRICE_PER_EVENT_USD:.2f} spent so far)")

            search_url = build_search_url(city, bedrooms, budget_min, budget_max)
            try:
                items = run_one_search(search_url, base_dir, tag, call_limit)
            except RuntimeError as exc:
                print(f"❌ {exc}")
                items = []

            events_used += len(items)
            all_items.extend(items)
            time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"\n✅ All bands completed within budget. Estimated spend: "
          f"${events_used * PRICE_PER_EVENT_USD:.2f} ({events_used} events).")
    return all_items


def dedupe_items(items: list) -> list:
    """Drop duplicate listings, keyed by the actor's listing id when present."""
    seen = set()
    deduped = []
    for item in items:
        if not isinstance(item, dict):
            deduped.append(item)
            continue
        key = item.get("id") or item.get("url") or json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def save_json(items: list, city: str) -> Path:
    base_dir = Path(__file__).resolve().parent
    json_dir = base_dir / "json"
    json_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_city = city.lower().replace(" ", "-")
    json_path = json_dir / f"magicbricks_{safe_city}_{timestamp}.json"

    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Combined JSON saved to: {json_path}")
    return json_path


def convert_json_to_csv(json_path: Path) -> Path:
    with json_path.open("r", encoding="utf-8") as file:
        items = json.load(file)

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
    raw_items = run_all_bands(CITY)
    print(f"\nTotal raw listings across all bands: {len(raw_items)}")

    items = dedupe_items(raw_items)
    print(f"Total unique listings after dedupe: {len(items)}\n")

    json_path = save_json(items, CITY)
    convert_json_to_csv(json_path)


if __name__ == "__main__":
    main()