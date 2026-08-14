# ==========================================
# ⚙️ CHANGE YOUR SCRAPING VARIABLES HERE
# ==========================================
$CITY = "Navi-Mumbai"
$BEDROOMS = "2,3"
$BUDGET_MIN = "10-Lacs"
$BUDGET_MAX = "20-Lacs"
$LIMIT = 10

# Generates a clean timestamp like: 20260814_153100 (YYYYMMDD_HHMMSS)
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

# Dynamic output file name (converts city name to lowercase automatically)
$OUTPUT_DIR = $PSScriptRoot
$OUTPUT_FILE = Join-Path $OUTPUT_DIR "magicbricks_$($CITY.ToLower())_$TIMESTAMP.json"
$INPUT_FILE = Join-Path $OUTPUT_DIR "magicbricks_$($CITY.ToLower())_$TIMESTAMP.input.json"

# ==========================================
# 🚀 AUTOMATICALLY BUILD AND RUN CLOUD ACTOR
# ==========================================

# 1. Build the dynamic MagicBricks search URL using your variables above
$URL = "https://www.magicbricks.com/property-for-sale/residential-real-estate?bedroom=$BEDROOMS&proptype=Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment,Residential-House,Villa&cityName=$CITY&BudgetMin=$BUDGET_MIN&BudgetMax=$BUDGET_MAX"

Write-Host " Initializing Apify Actor..." -ForegroundColor Cyan
Write-Host " Target City: $CITY"
Write-Host " Bedrooms: $BEDROOMS"
Write-Host " Limit: $LIMIT properties"
Write-Host " Scraping in progress..." -ForegroundColor Yellow

# 2. Build a valid JSON payload for the actor input and write it as UTF-8 without BOM
$INPUT_JSON = @{
    searchUrls = @($URL)
    resultsLimit = [int]$LIMIT
} | ConvertTo-Json -Depth 6

[System.IO.File]::WriteAllText($INPUT_FILE, $INPUT_JSON, [System.Text.UTF8Encoding]::new($false))

# 3. Run the Apify actor with the documented file-based input format and save the dataset output
$RESULT = & apify call krazee_kaushik/magicbricks-search-results-scraper --silent --output-dataset --input-file $INPUT_FILE 2>&1

if ($LASTEXITCODE -ne 0) {
    $RESULT | Write-Error
    Remove-Item $INPUT_FILE -Force -ErrorAction SilentlyContinue
    throw "Apify call failed. Check the actor name, authentication, and the search URL."
}

[System.IO.File]::WriteAllText($OUTPUT_FILE, ($RESULT | Out-String), [System.Text.UTF8Encoding]::new($false))
Remove-Item $INPUT_FILE -Force -ErrorAction SilentlyContinue

Write-Host " Scraping complete! Data saved to: $OUTPUT_FILE" -ForegroundColor Green
