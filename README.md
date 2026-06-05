# Mapping Bench

A single self-contained HTML page that assigns an `outlet_format` code to every row of a places CSV based on its `place_type`, using a taxonomy you provide. It runs **entirely in the browser** — no backend, no network calls, no external libraries or CDNs. Open it offline by double-clicking; nothing you load ever leaves the page.

## What it does

You upload two files:

1. **Places CSV** — must contain a `place_type` column. All other columns are preserved in their original order.
2. **Taxonomy JSON** — the list of valid `outlet_format` codes and what each one means.

For every row, the page assigns the best-matching `outlet_format` to its `place_type` — but **only when the place is an actual point of sale**. Service or institutional places are left blank. It then lets you review and override the result and export an augmented copy of your original CSV.

## How it works

### 1. Point-of-sale gate (runs first)

Before any matching, each unique `place_type` is classified as POS or not-POS using two editable keyword lists:

- **Include** — retail outlets (store, mart, kirana, grocery, pharmacy/chemist, apparel, jewellery, hardware, etc.), eateries (restaurant, cafe, dhaba, bar, food stall), and grooming (salon, spa, barber, parlour). These get a format assigned.
- **Exclude** — clinics, hospitals, banks/ATMs, schools, offices, government, places of worship, transport/stations, and other services or institutions. These are always left blank.

Exclude is checked first and wins over include. A `place_type` that matches no include keyword is also left blank ("not recognised as a point of sale"). Both lists are editable in the UI, so you can tune them and re-run instantly.

### 2. Matching (only for POS place_types)

The taxonomy is parsed defensively — it may be an object of `code → meaning`, or an array of objects with fields like `code` / `format` / `label` / `name` / `description` / `examples`. Key names are not assumed.

Each POS `place_type` is scored against every format by case-insensitive keyword overlap between the `place_type` text and the format's meaning/examples. The highest-scoring format wins. If nothing scores above the (configurable) threshold, the row is left blank. Matching is deterministic: identical `place_type` values always map the same way.

Every decision gets a short plain-English `mapping_reason`, e.g. `matched 'medical store' → CHEMIST` or `not a point of sale (matched exclude "bank")`.

### 3. Review & override

A table keyed by **unique** `place_type` shows the assigned `outlet_format`, the reason, and how many rows have that type. Blanks are highlighted. The table is sortable and filterable. Each row has a dropdown to override the assignment — pick a different code, force it blank, or revert to auto. Overrides always beat the automatic mapping. A summary bar reports total rows, unique place_types, number mapped, number blank, and number overridden.

### 4. Export

**Download CSV** writes your original file unchanged — all original columns, original order, original row count — with two columns appended:

- `outlet_format` — the assigned code (or blank)
- `mapping_reason` — the explanation

The mapping (and any overrides) is applied to every matching row. Fields containing commas, quotes, or newlines are properly quoted and escaped. The file is named `<original-filename>_mapped.csv`.

## Usage

1. Open `mapping-bench.html` in any modern browser (double-click works; no server needed).
2. Choose your places CSV and taxonomy JSON.
3. Optionally adjust the include/exclude keyword lists and match threshold.
4. Click **Run mapping**.
5. Review the table; override any assignments as needed.
6. Click **Download CSV**.

## Input formats

### Places CSV

Any CSV with a `place_type` column. The parser handles quoted fields, commas and newlines inside quotes, escaped double-quotes, a leading BOM, blank lines, and trailing newlines (CRLF or LF).

```csv
id,name,place_type,city
1,"Sharma Medical Store",medical store,Pune
2,"Axis Bank ATM",atm,Pune
```

### Taxonomy JSON

Either an object mapping codes to meanings:

```json
{
  "CHEMIST": "pharmacy, medical store, chemist, druggist",
  "GROCERY": "kirana, grocery, provision, general store, supermarket"
}
```

…or an array of objects (field names are flexible):

```json
[
  { "code": "CAFE", "label": "Cafe", "examples": ["coffee", "tea", "restaurant"] },
  { "format": "APPAREL", "description": "clothing, garment, footwear, textile" }
]
```

## Output

The exported `<original-filename>_mapped.csv` is identical to your input plus the appended `outlet_format` and `mapping_reason` columns:

```csv
id,name,place_type,city,outlet_format,mapping_reason
1,"Sharma Medical Store",medical store,Pune,CHEMIST,matched 'medical store' → CHEMIST
2,"Axis Bank ATM",atm,Pune,,"not a point of sale (matched exclude ""atm"")"
```

## Design notes

All logic is client-side and deterministic. Matching is case-insensitive and whitespace-tolerant, and empty or missing `place_type` values are handled gracefully (left blank with a reason). There are no dependencies to install and nothing to configure — the entire tool is contained in one HTML file.
