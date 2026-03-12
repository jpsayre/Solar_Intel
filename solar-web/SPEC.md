# Solar Web — UI Specification

This document defines all user-facing behaviors. All code changes must be verified against this spec before pushing.

---

## Explorer Page (`/homes`)

### Filters Panel
- County, city, subdivision dropdowns populated from `homes` table
- Address search (free text, applied on Enter/blur)
- Min model score, min roof score (numeric inputs)
- Sort by: hybrid (default), model_score, roof_score
- "Include homes with solar" checkbox (default: unchecked)
- Tag filter, exclude tag filter (prefix match, client-side)
- "Exclude do not contact" checkbox (default: checked, client-side)
- Min solar interest, min battery interest dropdowns (client-side)
- "X homes match" shows **total matching filters, excluding map bounds**
- "Clear all filters" resets all filters

### Map
- Color-coded dots: 10-color gradient blue→red based on selected sort score
- Homes with solar: dark gray dots (`#111827`)
- No-score homes: gray dots (`#9ca3af`)
- Clustering at zoom < 12
- **Hover tooltip**: address + city, ranking score, roof score
- **Click dot**: navigates to `/homes/{index}?from=explorer`
- Bounds debounce: 0ms first load, 400ms on pan/zoom
- Map position persists in URL params (`lat`, `lng`, `zoom`) — restored on return
- Max 1000 dots loaded at once

### Below Map
- "Showing X homes." where X = number of dots on map
- If dots >= 1000: append "Zoom in to load more."
- Horizontal rule
- Centered italic disclaimer: "Satellite imagery may not match the current condition of the home."

### Home Cards
- Satellite image (left) + details (right) on desktop; stacked on mobile
- Image from Supabase storage: `{index}.png`, loaded via `getPublicUrl()`
- Fallback image: `/window.svg`
- **Detail rows**: Ranking Score, Roof Score, Owner Name, Sale Price, Sale Date, Build Year, Square Footage
- Owner: "Owner1 & Owner2" if both, single name if one, "Available in full report" if none
- "Has Solar" amber badge if `has_solar` is true
- Follow toggle (top right)
- Click card → `/homes/{index}?from=explorer`
- Pagination: "Load more" button loads next page

---

## Home Detail Page (`/homes/[index]`)

### Header
- "← Back to explorer/following/alerts" button (left)
- "Report an issue" link (right) — opens modal

### Listing Card
- Same as explorer card but with `priority` image loading
- Follow toggle

### Report Issue Modal
- Categories: Permit issue, Solar status, Image issue, Home info, Other
- Optional description text
- Submits to `home_issues` table

### Permit History
- Collapsible section with count badge
- Each permit: type badge (colored), description, date, valuation
- Permit type colors: solar=amber, roof=sky, battery=violet, ev_charger=emerald, electrical=blue, heat_pump=orange, hvac=cyan, water_heater=teal, construction=stone, remodel=pink, generator=red, other=gray

### Home Info (org-specific, auto-saved)
- Roof condition dropdown: Excellent, Good, Fair, Poor
- Roofing material dropdown: Asphalt Shingles, Metal, Ceramic Tile, Concrete Tile, Slate, Wood Shakes, Flat/Membrane, Other
- Electricity bill (kWh) numeric input
- Solar interest: Unknown, Cold, Cool, Warm, Hot
- Battery interest: same
- EV ownership: Unknown, Doesn't Want, Interested, Owns an EV, Owns 2+ EVs

### Notes
- Threaded comments with author and timestamp
- "Add a note" input at bottom

### Contacts
- Editable list: preferred name, phone, email
- "Add contact" button
- Auto-saved

### Action Items
- Checklist with checkbox, text, completed timestamp
- "Add action item" button
- Auto-saved

### Tags
- Comma-separated, editable
- "Do not contact" toggle
- Auto-saved

---

## Following Page (`/following`)

### Filters
- Search: address, owner, comments, tags (free text)
- Tag filter (prefix match)
- Exclude tag filter (prefix match)
- Exclude do not contact checkbox (default: checked)

### Cards
- Stacked layout (labels above values)
- Shows: owner, contacts, open action items (bulleted), latest comment, tags
- Follow toggle
- "Has Solar" badge
- **Images**: signed URLs (30-min expiry) — TODO: should use `getPublicUrl()` like explorer
- Click → `/homes/{index}?from=following`

---

## Alerts Page (`/alerts`)

### Filters
- Permit type pills: Solar, Roof, Battery, EV Charger (toggle on/off)
- Default: Solar selected

### Alert Cards
- Permit type badge (colored, matches detail page colors)
- Address, city
- "X days ago" relative date
- Valuation (formatted as currency)
- Description
- Click → `/homes/{index}?from=alerts`

---

## Data Contracts

### MapPoint (passed to HomeMap)
| Field | Type | Source | Content |
|-------|------|--------|---------|
| lat | number | homes.latitude | Latitude |
| lng | number | homes.longitude | Longitude |
| index | string | homes.index | e.g. "BOULDER_CO_1014" |
| address | string | homes.address + city | "1234 MAIN ST, BOULDER" |
| score | number \| null | Varies by sort | Color indicator |
| roofScore | number \| null | home_scores.roof_score | |
| modelScore | number \| null | home_scores.model_score | |
| hasSolar | boolean | homes.has_solar | Dark dot if true |

### ListingCard DetailRows (explorer)
| Order | Label | Value |
|-------|-------|-------|
| 1 | RANKING SCORE | model_score or "—" |
| 2 | ROOF SCORE | roof_score or "—" |
| 3 | OWNER NAME | Formatted owner(s) |
| 4 | SALE PRICE | Formatted currency or "—" |
| 5 | SALE DATE | Formatted date or "—" |
| 6 | BUILD YEAR | Year or "—" |
| 7 | SQUARE FOOTAGE | Formatted number or "—" |

### URL Search Params (explorer)
| Param | State | Notes |
|-------|-------|-------|
| county | county filter | |
| city | city filter | |
| subdivision | subdivision filter | |
| address | address search | |
| lat | map center latitude | 5 decimal places |
| lng | map center longitude | 5 decimal places |
| zoom | map zoom level | integer |
| sort | sort by | omitted if "hybrid" |
| minModel | min model score | |
| minRoof | min roof score | |
| minSolar | min solar interest | |
| minBattery | min battery interest | |
| tag | tag filter | |
| excludeTag | exclude tag filter | |
| dnc | exclude do not contact | "0" if unchecked |
| solar | include solar homes | "1" if checked |

### Image Loading
| Page | Method | Notes |
|------|--------|-------|
| Explorer | `getPublicUrl()` | Permanent public URLs |
| Home Detail | `getPublicUrl()` | Permanent public URLs |
| Following | `createSignedUrl()` | **Should be `getPublicUrl()`** |
| Follows | `createSignedUrl()` | **Should be `getPublicUrl()`** |
