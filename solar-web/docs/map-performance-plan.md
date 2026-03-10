# Map Performance Plan

## Problem
- Dots render gray first because scores are in a separate table (two round trips)
- Limited to 500 homes per query — unusable for 20K+ territories
- Client-side filtering (do-not-contact, tags) reduces visible set after fetch
- Each dot is a DOM element (CircleMarker) — doesn't scale past ~2K

## Architecture Changes

### Phase 1: Kill the gray flash + single query (CURRENT)

**1a. Create `homes_with_scores` view** joining homes + home_scores with hybrid calc.
Eliminates the second query for scores. Every dot arrives pre-colored.

**1b. Create `get_map_points` RPC** returning only lat/lng/scores for all homes.
~400KB for 20K homes. One request, sub-second, all dots colored immediately.

**1b-note.** Map limited to 1000 homes (Supabase PostgREST max rows default).
Cards still load separately at 500 per page for full detail.

**1c. Enable `preferCanvas: true`** on the Leaflet MapContainer.
Renders all CircleMarkers to a single `<canvas>` instead of individual DOM elements.
Gets us to 10-20K points without framework changes.

### Phase 2: Two-tier data loading (NEXT)

Split map data from card data:
- **Map layer**: Load ALL points via lightweight RPC on mount. Always complete.
- **Card layer**: Fetch full home details only for viewport (~20-50 homes).

This means the map is always fully populated. Cards lazy-load on zoom/pan.

### Phase 3: Server-side filtering (LATER)

Move do-not-contact and tag filtering into the RPC as parameters.
No wasted rows. Server returns only displayable homes.

### Phase 4: Scale to 100K+ (WHEN NEEDED)

- deck.gl ScatterplotLayer for WebGL rendering (500K points at 60fps)
- PostGIS spatial index for bounds queries
- Materialized view or localStorage cache for filter dropdown options

## SQL Applied

See `sql/001_map_performance.sql` for the view and RPC definitions.

## Hybrid Score Formula

```
hybrid_score = ROUND(0.6 * model_score + 0.4 * roof_score)
```

Falls back to whichever score exists if only one is present.
Returns NULL if both are NULL.
