# How the offline map is put together

A guide for anyone who wants to improve the map: add a kind of place, show one that is already in the data, or extend
coverage. It says which files the app reads, what builds each one, and where the gaps are. Everything here was read from
the code and from one installed state map, without running the app; where something could not be found in this
repository, it says so.

The map follows the same rules as the rest of Lastbook (see [CONTRIBUTING.md](../CONTRIBUTING.md)). The app draws only
from files on the computer and never asks the network for a tile, a place or an address. The build tools in `tools/` are
different: they run on a build machine, and several of them download public data. They are never part of the app.

## What the app reads

A map set lives in the data folder. `map-set.json` at its top lists the files and their sizes.

| File | Tables | What it holds | Read by |
|---|---|---|---|
| `derived/geo/national.sqlite` | `feat`, `feat_idx`, `poi`, `meta` | Roads, water and land shapes, and the place pins | `server.py` (`national_mapdb`) |
| `derived/geo/map.sqlite` | the same four | The original detailed street map of Southern California; it had no rows in the state map checked | `server.py` (`mapdb`) |
| `derived/geo/water.sqlite` | `resource`, `spatial`, `feat`, `feat_idx` | Dams, reservoirs, lakes and ponds | `server.py` |
| `derived/geo/crops.sqlite` | `resource`, `spatial`, `tile` | Orchards, vineyards and berries | `server.py` |
| `derived/geo/terrain.sqlite` | `tile` | Elevation tiles for relief, contours and the 3D view | `server.py` |
| `derived/geo/buildings.sqlite` | `bldg` | Building outlines | `server.py` |
| `derived/geo/places.sqlite` | `place`, `place_fts` | The place finder: towns, ZIP codes, counties, named places | `server.py` (`/api/places`) |
| `library-data/geography/resources/atlas.sqlite` | `resource`, `spatial` | Natural resource records. The state map checked held minerals only; the fish, boating and well layers are labelled California in `web/map.js` | `server.py` |
| `derived/geo/addresses/` | one index per state | Street addresses for address search | `engine/address_search.py` |

Two kinds of table carry the things a person can tap:

- `poi(id, cls, name, lon, lat)`: a point with a class, such as `hospital` or `fuel`.
- `resource(id, source_id, kind, name, lat, lon, detail, source, origin)` with its `spatial` index: a record with a kind,
  a line of detail and the name of its source.

## Opening a locally built map on Windows

The setup picker lists published maps. To preview a map you built, keep it in its own writable folder with
`map-set.json` at the top and the map files under `derived/geo/`. The desktop app also requires a
`library-data/catalog.json` in that folder. For a new map-only folder, the commands below create an empty
catalog without a byte order mark. Keep any existing catalog intact.

Open PowerShell and replace `C:\path\to\LastbookData` with your map folder. This example uses the default
location of the installed Windows app.

```powershell
$map = "C:\path\to\LastbookData"
$library = Join-Path $map "library-data"
$catalog = Join-Path $library "catalog.json"
if (-not (Test-Path -LiteralPath $catalog)) {
    New-Item -ItemType Directory -Path $library -Force | Out-Null
    Set-Content -LiteralPath $catalog -Value '[]' -Encoding ASCII
}
& "$env:LOCALAPPDATA\Programs\Lastbook\Lastbook.exe" --data $map
```

Select **Map** in Lastbook and look up a place within the map's coverage to check that the detail loads.

## How a place gets onto the map

1. A row with a class (`poi.cls`) or a kind (`resource.kind`) is in one of the files above.
2. The class is named in a layer in `web/map.js` (`LAYERS`: id, label, symbol, colour, classes, group).
3. The engine reports which classes a map set really holds (`map_contents` in `server.py`), and the app offers only the
   layers that have something to show.

A class that is in the data but in no layer has no entry in the Layers panel, so it cannot be switched on. The engine
already has a plain name for several of them (`HELP` in `server.py`: School, Dentist, Vet, Care home, Post office).

### Places that are in the data and not shown

The data holds more classes than `web/map.js` has layers for (`tools/build_map.py` lists the ones it keeps as
`POI_KEEP`). In one state map checked on 15 November 2026 (77,356 pins), these classes had rows and no layer:

| Class | Rows |
|---|---|
| `school` | 13,862 |
| `fountain` | 4,971 |
| `post_office` | 2,224 |
| `car_repair` | 1,444 |
| `park` | 1,102 |
| `veterinary` | 1,102 |
| `college` | 468 |
| `university` | 362 |
| `garden_centre` | 176 |
| `nursing_home` | 49 |
| `water_works` | 3 |

Showing one of these needs no new data: add a layer line in `web/map.js` and say in the pull request why the kind helps
someone in an emergency. The comment in `map.js` about retired layers shows that some kinds were left out on purpose,
so ask before adding many.

## What builds each file

| File | Built by | From |
|---|---|---|
| `map.sqlite` | `tools/build_map.py`, then `tools/build_coast.py` for the ocean | An OpenStreetMap regional extract (ODbL) |
| `water.sqlite` | `tools/build_water.py` (`nid`, then `nhd`) | USACE National Inventory of Dams, USGS National Hydrography Dataset |
| `crops.sqlite` | `tools/build_crops.py` | USDA Cropland Data Layer |
| `terrain.sqlite` | `tools/build_terrain.py` | USGS 3DEP elevation |
| `buildings.sqlite` | `tools/build_buildings.py`, `tools/build_osm_heights.py` | Microsoft building footprints (ODbL), OpenStreetMap heights |
| `places.sqlite` | `tools/build_places.py` | USGS GNIS, Census gazetteers, named OpenStreetMap places |
| address indexes | `tools/build_addresses.py`, then `packaging/address_indexes.py` | Overture Maps addresses |
| a state map | `packaging/build_packs.py map <ST>`, published by `packaging/state_maps.py` | The base map, then every row inside the state's box |

Each tool's header says what it reads, what it writes and the licence of its source. Read it before you run one: some
expect source files that are hundreds of gigabytes.

### Not in this repository

- **The builder for `national.sqlite`.** The pack tools copy from an existing `national.sqlite` and `server.py` reads it,
  but no tool here makes it from OpenStreetMap data.
- **The builder for `atlas.sqlite`.**
- **A reader for seven place files.** `tools/build_places_civic.py`, `_usgs.py`, `_overture.py`, `_atp.py`, `_fsq.py`,
  `_fuel.py` and `_snap.py` each write a `derived/geo/places-*.sqlite` and say it is merged by `game/serve.py`. That file
  is not here, and nothing in this repository reads those seven files, so the extra records they hold are not used by
  the app directly. This is an unused data source, not a missing kind of place: the map already shows shelters,
  libraries, community centres and food shops from the data it does read. A class that has records and no layer is the
  separate case described above.

## What is tied to the United States

- Every detailed source above is a US dataset, or a worldwide one filtered to the US.
- `server.py` treats a box around Southern California as the area `map.sqlite` covers (`_poi_sources`, `socal_classes`).
- Detailed maps are cut and installed one US state at a time (`docs/SETUP-API.md`, "State maps").
- Address search knows US state names and US street words (`engine/address_search.py`, `tools/build_addresses.py`).
- The base map of the world is drawn from `web/world-context.json` and `web/geographic-context.json`.

Coverage outside the US needs a decision on each of these first: which open source replaces each federal list, under
what licence, what a "state" is elsewhere, and how addresses are written. That is a design discussion to have in an
issue before any code.

[REGIONS.md](REGIONS.md) proposes answers for Ontario, British Columbia and Guyana, as a starting point for that issue.
[REGIONS-AR.md](REGIONS-AR.md) does the same for Argentina's provinces and the Autonomous City of Buenos Aires.
[REGIONS-LK.md](REGIONS-LK.md) does the same for Sri Lanka as one island-wide region.
[REGIONS-TH.md](REGIONS-TH.md) does the same for Thailand's provinces and Bangkok.
[REGIONS-DE.md](REGIONS-DE.md) does the same for Germany's 16 states.
[REGIONS-PY.md](REGIONS-PY.md) does the same for Paraguay as one country-wide region.
[REGIONS-IE.md](REGIONS-IE.md) does the same for the island of Ireland, including Northern Ireland, as one region.
[REGIONS-GB-LONDON.md](REGIONS-GB-LONDON.md) does the same for Greater London as one region.
[REGIONS-ES.md](REGIONS-ES.md) does the same for Spain's 17 autonomous communities and its two autonomous cities.
[REGIONS-FR.md](REGIONS-FR.md) does the same for France's 18 regions, with figures from a trial build.
[REGIONS-CL.md](REGIONS-CL.md) does the same for Chile's 16 regions.
[REGIONS-CL-DPA2023.md](REGIONS-CL-DPA2023.md) adds a DPA 2023 companion study and paired Spanish text for Chile.
[REGIONS-AE.md](REGIONS-AE.md) does the same for the United Arab Emirates, proposed as one map for all seven emirates.
[REGIONS-IN.md](REGIONS-IN.md) does the same for India's 28 states and 8 union territories.
[REGIONS-PK.md](REGIONS-PK.md) does the same for Pakistan's provinces and territories, with Islamabad and Rawalpindi
as one map.
[REGIONS-MB.md](REGIONS-MB.md) does the same for the Canadian province of Manitoba.
[REGIONS-DK.md](REGIONS-DK.md) does the same for Denmark's 5 regions.
[REGIONS-AT.md](REGIONS-AT.md) does the same for Austria's nine states.

[REGIONS-MX.md](REGIONS-MX.md) does the same for Mexico's 32 states (entidades federativas).

[REGIONS-BR.md](REGIONS-BR.md) does the same for Brazil's 26 states and the Federal District (Distrito Federal), 27 in all.

### To do: maps for every place on Earth

The goal is a detailed map for any place a person lives.

- [ ] **Region ids.** The manifest already accepts map ids such as `DE-BE` and `CA-ON`. Address-index ids in
  `engine/setup/manifest.py` and the address-index filenames carried over by `engine/setup/install.py` still use
  two capital letters. The map builders in `packaging/state_maps.py` and `packaging/build_packs.py` use US regions.
  Most proposals above use ISO 3166-2 ids to avoid reusing US state codes such as `DE` and `CA`.
- [ ] **Sources.** Pick an open replacement for each US dataset, region by region, with its licence. The region
  proposals above do this.
- [ ] **No Southern California box.** `server.py` assumes `map.sqlite` covers Southern California (`_poi_sources`,
  `socal_classes`).
- [ ] **Setup.** First run asks for a US state map (#267). Installing several maps or a locally built map through
  Setup is #53. A hand-built library already opens with [`--data`](#opening-a-locally-built-map-on-windows).
- [ ] **Address search.** It knows US state names and US street words. Other countries write the number after the
  street, fold accents, or have no postcode.
- [ ] **Units.** The map shows distances in miles above 1.6 km and contour lines in feet (`web/map.js`).
- [ ] **Emergency number** for the person's country (#261).

The design discussion is in #23, #25, #31 and #95.

## Checking a map change

- A change to a layer in `web/map.js` is a change you can see: include screenshots in light and dark mode.
- A change to a pack or map tool: `packaging/test_pack_tools.py` and `packaging/scan_pack.py` check what a map set may
  hold, and `scan_pack.py` lists the allowed files under `derived/geo/` (`GEO_FILES`).
- Nothing a contributor adds may make the app open a connection. New data comes in through a build tool and ships as a
  file.
