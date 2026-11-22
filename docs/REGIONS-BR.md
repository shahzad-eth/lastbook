# Detailed maps for Brazil: a proposal

This is a proposal for discussion, not a decision. It answers, for Brazil, the questions [MAPS.md](MAPS.md) asks before
coverage can go beyond the United States: which open source replaces each federal list, under what licence, what a
"state" is there, and how addresses are written. It follows the shape of [REGIONS-MX.md](REGIONS-MX.md) and
[REGIONS-AR.md](REGIONS-AR.md) and is meant to feed the same design discussion (issues #23, #25, #31 and #54). The
machine-readable version is [regions-br-proposed.json](regions-br-proposed.json), and a Portuguese translation is
[REGIONS-BR.pt.md](REGIONS-BR.pt.md).

Nothing here changes the app, the engine or a build. No code reads the JSON, and nothing here ships: builds package
`web/` and `content/` only.

**How things were checked.** Research was done on 20 November 2026. Each source carries one of three marks:

- **opened**: the dataset or licence page itself was opened and read;
- **search only**: the fact was seen in a search result or a search snippet, but the page itself was not opened;
- **not checked**: the page could not be reached or read, or it was not looked at in this proposal; the row says what
  is missing.

The state boxes were computed from IBGE's own state polygons, read through IBGE's public malhas API (opened). The
licence of those polygons is **not** settled (see "Licence notes"), so the boxes are a proposal until that is.

## Why Brazil is a useful case

Brazil has its own national scheme for emergency numbers (190, 192, 193 and 199, see "Help points"), and seven of its states use
two-letter codes that collide with US codes in this repository. Brazil has no open postal-code
(CEP) area layer that was checked for this proposal. Two things are different from the US and worth deciding once,
because other Portuguese- and Spanish-speaking countries will raise them too:

- **Two-letter codes collide with US codes.** Seven Brazilian codes are also US state codes in `STATE_CODES`
  (`engine/address_search.py`). This is the main reason for hyphenated codes below.
- **No checked CEP-to-state table.** The eight-digit CEP (*Código de Endereçamento Postal*) on an address is what address
  search needs, but no official CEP-to-state table was checked, so addresses cannot be split by state yet.

## What a region is

Brazil has 26 states (*estados*) and the Federal District (*Distrito Federal*, DF). The proposal is one region per
unit, 27 in all, the same level as a US state. DF is a federal unit with its own government, so it is kept as its own
region here; see the note on DF and Goiás below.

### Codes

ISO 3166-2:BR gives each unit the prefix `BR-` and two letters: `BR-SP` São Paulo, `BR-RJ` Rio de Janeiro, `BR-DF`
Distrito Federal, and so on (the 27 codes were read from the Wikipedia article "ISO 3166-2:BR", which lists the names as
in ISO 3166-2 from the ISO 3166/MA; the ISO Online Browsing Platform itself was not opened).

- **Seven two-letter codes collide with US codes.** The two-letter Brazilian codes `AL` (Alagoas), `MA` (Maranhão),
  `MS` (Mato Grosso do Sul), `MT` (Mato Grosso), `PA` (Pará), `PR` (Paraná) and `SC` (Santa Catarina) are also codes in
  `STATE_CODES` (`engine/address_search.py`) for Alabama, Massachusetts, Mississippi, Montana, Pennsylvania, Puerto
  Rico and South Carolina. A bare `PA` already means Pennsylvania in address search. A Brazilian `PA` would be read the
  same way, so the Brazilian codes cannot be used bare.
- **The hyphenated code is needed for the file name too.** `carry_over()` in `engine/setup/install.py` keeps only
  address indexes named `[A-Z]{2}.sqlite` or `.json` (line 335). An index named `BR-SP.sqlite` would be left behind in
  the old library without a message, as REGIONS-MX.md also notes for `MX-AGU`. The change to `carry_over` would be a
  maintainer's decision.

### Boxes

The boxes were computed from IBGE's state polygons (malhas territoriais, state layer, "malha estadual"), read through
IBGE's public malhas API at maximum quality (`qualidade=maxima`) on 20 November 2026 (opened). The API returns one
feature per unit: 27 features, with 1 to 17 polygons each (Pará has 17, and Rio de Janeiro 15). Every vertex of every
polygon was read; the bounding box was then widened by 0.15° and rounded outward to 0.01°, the same margin
`map_sets.state` uses for US states.

As a check, the outer edges match Brazil's known extreme points as recalled from memory (not checked against a published
list in this pass): the northern tip of Roraima (about 5.27° N), the southern tip of Rio Grande do Sul (about 33.75° S),
the eastern tip of Paraíba (about 34.79° W) and the western edge of Acre (about 73.99° W). Those four edges are set by
those states, and the table matches them.

| Code | IBGE | Name | Box (west, south, east, north) | Box with 0.15° margin |
|---|---|---|---|---|
| `BR-RO` | 11 | Rondônia | -66.8103, -13.6937, -59.7744, -7.9759 | -66.97, -13.85, -59.62, -7.82 |
| `BR-AC` | 12 | Acre | -73.9904, -11.1456, -66.6239, -7.1118 | -74.15, -11.30, -66.47, -6.96 |
| `BR-AM` | 13 | Amazonas | -73.8016, -9.8180, -56.0976, 2.2466 | -73.96, -9.97, -55.94, 2.40 |
| `BR-RR` | 14 | Roraima | -64.8253, -1.5806, -58.8869, 5.2718 | -64.98, -1.74, -58.73, 5.43 |
| `BR-PA` | 15 | Pará | -58.8983, -9.8412, -46.0618, 2.5910 | -59.05, -10.00, -45.91, 2.75 |
| `BR-AP` | 16 | Amapá | -54.8763, -1.2362, -49.8758, 4.5088 | -55.03, -1.39, -49.72, 4.66 |
| `BR-TO` | 17 | Tocantins | -50.7421, -13.4682, -45.6993, -5.1684 | -50.90, -13.62, -45.54, -5.01 |
| `BR-MA` | 21 | Maranhão | -48.7552, -10.2596, -41.7967, -1.0495 | -48.91, -10.41, -41.64, -0.89 |
| `BR-PI` | 22 | Piauí | -46.0282, -10.9288, -40.3705, -2.7499 | -46.18, -11.08, -40.22, -2.59 |
| `BR-CE` | 23 | Ceará | -41.4233, -7.8576, -37.2527, -2.7843 | -41.58, -8.01, -37.10, -2.63 |
| `BR-RN` | 24 | Rio Grande do Norte | -38.5821, -6.9827, -34.9685, -4.8314 | -38.74, -7.14, -34.81, -4.68 |
| `BR-PB` | 25 | Paraíba | -38.7652, -8.3030, -34.7932, -6.0259 | -38.92, -8.46, -34.64, -5.87 |
| `BR-PE` | 26 | Pernambuco | -41.3583, -9.4829, -32.3971, -3.8358 | -41.51, -9.64, -32.24, -3.68 |
| `BR-AL` | 27 | Alagoas | -38.2376, -10.4986, -35.1527, -8.8161 | -38.39, -10.65, -35.00, -8.66 |
| `BR-SE` | 28 | Sergipe | -38.2450, -11.5685, -36.3959, -9.5150 | -38.40, -11.72, -36.24, -9.36 |
| `BR-BA` | 29 | Bahia | -46.5768, -18.3372, -37.3411, -8.5328 | -46.73, -18.49, -37.19, -8.38 |
| `BR-MG` | 31 | Minas Gerais | -51.0461, -22.9228, -39.8568, -14.2333 | -51.20, -23.08, -39.70, -14.08 |
| `BR-ES` | 32 | Espírito Santo | -41.8796, -21.3011, -39.6678, -17.8919 | -42.03, -21.46, -39.51, -17.74 |
| `BR-RJ` | 33 | Rio de Janeiro | -44.8893, -23.3676, -40.9579, -20.7632 | -45.04, -23.52, -40.80, -20.61 |
| `BR-SP` | 35 | São Paulo | -53.1101, -25.3089, -44.1614, -19.7799 | -53.27, -25.46, -44.01, -19.62 |
| `BR-PR` | 41 | Paraná | -54.6199, -26.7171, -48.0235, -22.5163 | -54.77, -26.87, -47.87, -22.36 |
| `BR-SC` | 42 | Santa Catarina | -53.8371, -29.3551, -48.3585, -25.9558 | -53.99, -29.51, -48.20, -25.80 |
| `BR-RS` | 43 | Rio Grande do Sul | -57.6497, -33.7508, -49.6914, -27.0823 | -57.80, -33.91, -49.54, -26.93 |
| `BR-MS` | 50 | Mato Grosso do Sul | -58.1686, -24.0682, -50.9242, -17.1663 | -58.32, -24.22, -50.77, -17.01 |
| `BR-MT` | 51 | Mato Grosso | -61.6334, -18.0416, -50.2248, -7.3490 | -61.79, -18.20, -50.07, -7.19 |
| `BR-GO` | 52 | Goiás | -53.2485, -19.4981, -45.9072, -12.3954 | -53.40, -19.65, -45.75, -12.24 |
| `BR-DF` | 53 | Distrito Federal | -48.2857, -16.0500, -47.3085, -15.5018 | -48.44, -16.20, -47.15, -15.35 |

Notes:

- **DF inside Goiás.** The DF box lies entirely inside the `BR-GO` box, the same case as CABA inside Buenos Aires in
  REGIONS-AR.md. The Brasília metropolitan area crosses the DF and Goiás border, so a person there who installs only one
  of the two maps misses part of their area. Options: keep the two maps separate (simple), or let the `BR-GO` map include
  `BR-DF` (matches how people move in the area, as REGIONS-AR.md suggests for CABA). This proposal does not decide it.
- **Large boxes.** Amazonas, Pará and Mato Grosso are the largest boxes. Their maps will be large, and the
  size of the download has not been estimated for this proposal.
- **Offshore islands.** The IBGE polygons were checked for every unit: any polygon more than 0.5° from the unit's largest
  polygon was listed. Two detached islands are in the polygons, and two offshore islands are not in them at all.
  - **Fernando de Noronha** (`BR-PE`, about 2.4° east of the mainland) is **kept** in the PE box, because it is a
    Pernambuco island with people living on it, and no other map would show it. Its tight edge is -32.40° W, so the PE
    box with margin reaches -32.24° W.
    Without Noronha the box would end at -34.81° W; the cost is about 2.4° of mostly ocean.
  - **Trindade and Martim Vaz** (`BR-ES`, about 10° east of the mainland, around 20.5° S) are **left out** of the ES
    box. Keeping them would stretch the ES box from -39.67° W to -29.30° W, about 13° wide and mostly ocean, so the
    box would stop being useful for the mainland. Whether they need a map of their own is an open question. No resident
    population was checked for them.
  - **Atol das Rocas** (RN) and **São Pedro e São Paulo** (PE) are **not in the IBGE state polygons**, so no box
    includes them and nothing has to be cut. Whether either should have a map is an open question.
  - The rule used here: an island goes in its state's box only if it is part of the state's IBGE polygon **and** either
    is close to the mainland or has people living on it. Only Noronha passes that test. This is a proposal, not a
    settled rule.
- **Overlapping boxes.** Boxes follow each state's own outline, so neighbouring boxes overlap along borders. The
  overlap is expected and is the same as for the US and Mexico.

## Sources, layer by layer

| Layer (file) | US source today | Proposed for Brazil | Publisher | Licence | Checked |
|---|---|---|---|---|---|
| Terrain (`terrain.sqlite`) | USGS 3DEP | Copernicus DEM GLO-30, as for the fallback in REGIONS-AR.md and REGIONS-MX.md; no Brazil-specific national elevation product was checked here | ESA / Airbus | Copernicus licence | Copernicus as in REGIONS-AR.md; Brazil-specific product not checked |
| Water (`water.sqlite`) | NHD | OSM waterways and water areas, as for the US. ANA's BHO 6 is not proposed: its licence is only "free access" (see Water) | OSM contributors; ANA | ODbL (read 20 Nov 2026) | ODbL opened; ANA metadata opened, no licence named |
| Dams | NID | No open national dam list was identified in this pass. OSM `waterway=dam` as a fallback, not counted | OSM contributors | ODbL | not checked |
| Crops (`crops.sqlite`) | USDA Cropland Data Layer | MapBiomas land cover is a candidate, because it covers Brazil's crop classes, but its licence and class list were not checked | MapBiomas | not checked | not checked |
| Buildings (`buildings.sqlite`) | Microsoft US footprints, OSM heights | Google Open Buildings V3, as in REGIONS-MX.md; Brazil coverage not re-checked here; OSM to fill gaps | Google; OSM contributors | CC BY 4.0; ODbL | as REGIONS-MX.md; not re-opened for Brazil |
| Places (`places.sqlite`) | GNIS, Census gazetteers, OSM | IBGE malhas for states, municipalities and localities (the state layer was used for the boxes); OSM named places | IBGE; OSM contributors | IBGE terms unclear (see Licence notes); ODbL | state layer opened; licence not confirmed |
| Addresses (`addresses/<code>.sqlite`) | Overture addresses | Overture addresses: 89,887,635 Brazilian rows in the publisher's per-country table; per-state counts not computed; no open CEP area table found | Overture Maps Foundation; Correios (CEP) | Overture attribution not re-read; CEP not open | Overture guide opened 20 Nov 2026; Correios guide search only |
| Points of interest (`poi` rows) | OSM | OSM tags for drinking water, hospitals, clinics, fire and police stations (counts in "Water" and "Help points and counts"); CNES as a candidate for health establishments | OSM contributors; Ministério da Saúde (DATASUS) | ODbL (read); CNES dataset cc-by (read) | counted through Overpass, 20 Nov 2026 |

## Help points and counts

- **Health establishments: CNES (candidate).** The DATASUS CNES dataset page (dadosabertos.saude.gov.br, opened 20
  November 2026) gives its licence field as `cc-by` ("Creative Commons Atribuição"). That passes the test: commercial use
  and adaptation are allowed with credit. Coordinates were **not verified**, so the file layout must be checked before a
  build.
- **Caveat on CNES.** The same portal's footer says the site's content is CC BY-ND 3.0 (no adaptation). That refers to the
  site's own text, not to the dataset. Maintainers should confirm that the dataset licence governs the data.
- **Fire and police stations.** The state fire and police lists were not checked. The OSM counts below are the only
  national figures in this pass.
- **Shelters.** No open national shelter list was found; OSM `amenity=shelter` is not counted here.
- **Ministry of Health plan documents** are described in search results as CC BY-NC-SA (not opened). That licence is not
  used for any dataset here.

| Unit | `amenity=drinking_water` | `man_made=water_tap` | `natural=spring` | `man_made=water_well` | `amenity=hospital` | `amenity=clinic` | `amenity=fire_station` | `amenity=police` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `BR-AC` | 1 | 0 | 19 | 1 | 26 | 21 | 1 | 21 |
| `BR-AL` | 5 | 0 | 6 | 93 | 111 | 154 | 10 | 82 |
| `BR-AP` | 0 | 0 | 2 | 1 | 38 | 89 | 5 | 46 |
| `BR-AM` | 14 | 1 | 19 | 6 | 131 | 147 | 11 | 77 |
| `BR-BA` | 32 | 12 | 103 | 26 | 656 | 1,163 | 25 | 529 |
| `BR-CE` | 60 | 5 | 15 | 168 | 344 | 680 | 19 | 253 |
| `BR-DF` | 34 | 12 | 21 | 2 | 126 | 190 | 42 | 202 |
| `BR-ES` | 41 | 3 | 15 | 3 | 144 | 432 | 20 | 250 |
| `BR-GO` | 29 | 2 | 111 | 14 | 327 | 312 | 34 | 213 |
| `BR-MA` | 5 | 1 | 4 | 23 | 228 | 178 | 16 | 118 |
| `BR-MT` | 4 | 7 | not counted | 3 | 181 | 270 | 25 | 172 |
| `BR-MS` | 9 | 0 | 174 | 6 | 115 | 87 | 19 | 121 |
| `BR-MG` | 142 | 15 | 1,697 | 54 | 860 | 1,234 | 63 | 656 |
| `BR-PA` | 42 | 0 | 23 | 16 | 270 | 229 | 16 | 141 |
| `BR-PB` | 34 | 14 | 15 | 83 | 213 | 271 | 18 | 107 |
| `BR-PR` | 101 | 37 | 228 | 33 | 510 | 930 | 92 | 454 |
| `BR-PE` | 18 | 6 | 245 | 40 | 431 | 529 | 30 | 209 |
| `BR-PI` | 9 | 0 | 9 | 29 | 228 | 478 | 3 | 106 |
| `BR-RJ` | 71 | 22 | 727 | 54 | 603 | 797 | 118 | 541 |
| `BR-RN` | 33 | 2 | 5 | 55 | 191 | 439 | 8 | 180 |
| `BR-RS` | 88 | 30 | 84 | 38 | 560 | 1,056 | 132 | 583 |
| `BR-RO` | 3 | 0 | 3 | 0 | 52 | 41 | 6 | 71 |
| `BR-RR` | 12 | 0 | 4 | 2 | 23 | 65 | 6 | 55 |
| `BR-SC` | 34 | 3 | 484 | 20 | 252 | 1,240 | 193 | 459 |
| `BR-SP` | 470 | 92 | 2,411 | 136 | 1,370 | 2,663 | 234 | 2,195 |
| `BR-SE` | 7 | 1 | 7 | 4 | 72 | 274 | 10 | 146 |
| `BR-TO` | 7 | 0 | 11 | 0 | 52 | 75 | 2 | 28 |
| **Total (sum of the 27 units)** | **1,305** | **265** | **not counted** | **910** | **8,114** | **14,044** | **1,158** | **8,015** |

The counts are OSM objects as found by Overpass on 20 November 2026, per unit (ISO 3166-2 area); the last row is the sum
of the 27 units. A single country-wide query timed out on the Overpass server, so the country total was not counted
separately. Duplicates and closed features were not removed, so these are upper bounds for a usable map, not checked
totals.

Mato Grosso's `natural=spring` is **not counted**. Overpass gives 53,580 objects. To see where they come from, the IBGE
tight box for BR-MT (W -61.6334, S -18.0416, E -50.2248, N -7.3490) was cut in half at its midpoints, latitude -12.6953
and longitude -55.9291, and each quarter was intersected with the OSM BR-MT area. The quarters hold 31,074 (south-west),
19,825 (south-east), 40 (north-west) and 2,641 (north-east), which sum to 53,580; a whole-state query on 21 November
2026 gave the same total. Reading the object metadata of the two southern quarters, 50,807 springs (31,006 south-west
and 19,801 south-east) are in eight changesets made by one OSM user (`danctc`) on 6 November 2025 (174297625, 174297760,
174297826, 174297902, 174298479, 174298489, 174298500 and 174298643). All eight are tagged `source=SEMA-MT` (the Mato
Grosso environment department) and have no discussion comments. No permission for SEMA-MT data was found: the OSM wiki
Contributors page lists the Minas Gerais environment department but not SEMA-MT, the Import/Catalogue has no entry for
it, and the SEMA-MT website footer says "Todos os Direitos reservados" (all rights reserved). The points may be real
springs, but without a documented licence they should not be counted or shipped, so no number is shown for that column,
and the column total is not counted either.

## Licence notes and attribution

- **gov.br content.** The footer of gov.br pages says all content is published under *Creative Commons
  Atribuição-SemDerivações 3.0 Não Adaptada* (CC BY-ND 3.0 Brazil) (opened, read on 20 November 2026 on the gov.br
  "Sobre o portal" page and on the federal SAMU page). The "no derivatives" part means a page cannot be adapted into a
  library guide, so gov.br pages are not proposed as copy sources. Quoting a single number with its source is a question
  for maintainers, not a decision made here.
- **IBGE.** No explicit open licence was found for the malhas. IBGE publishes a technical and legal note with each
  product ("Informações técnicas e legais para a utilização dos dados publicados") (search only, not opened). The BC250
  base map terms describe a restricted use for support of work projects, not an open licence (search only, not opened).
  Until the note for the state malha is read, the IBGE layers are **not proposed for a build**. The boxes in this file
  are numbers computed from the data, and they should be re-checked against the licence before anyone relies on them.

## Water: drinking and clean water

This is the first priority for Brazil, so it is set out in full. For each source the question is the same as for the
rest of the map: can the library copy it, and can it be used offline?

**Proposed**

- **Water layer: OpenStreetMap, under the ODbL.** Waterways and water areas, as in the US build. The ODbL 1.0 text was
  read on its licence page on 20 November 2026 (opened): commercial use is allowed, a database built from OSM data is
  shared under the same licence, and the credit is "© OpenStreetMap contributors".
- **Drinking water points: OSM tags.** `amenity=drinking_water` (a public tap or fountain), `man_made=water_tap`,
  `natural=spring` and `man_made=water_well`. A tag does not say the water is safe to drink, so springs and wells get a
  plain "not checked for drinking" label, as REGIONS-ES.md proposes for Spain.
- **Counts per unit** are in "Help points and counts" below (Overpass API, 20 November 2026).

**Not proposed (the licence test fails)**

- **ANA Base Hidrográfica Ottocodificada (BHO 6).** The metadata record (metadados.snirh.gov.br, opened 20 November 2026)
  gives the licence as "O acesso ao dado é livre." ("access to the data is free"). That names no licence, and nothing says
  the data may be adapted or used commercially. Not proposed until ANA names one. Next step: ask ANA, and check the
  dataset page on dadosabertos.ana.gov.br.
- **CPRM SIAGAS (groundwater wells).** The SIAGAS web portal (siagasweb.sgb.gov.br, opened 20 November 2026) has no
  licence or terms text. The agreements and reports found describe software licences, not data licences, and a 2008
  document says full data needs a written request. Not proposed; OSM water wells stand in for it. Next step: ask CPRM for
  the data licence.
- **Dams.** Still not checked (see the Sources table). No open national list was found in this pass.

## Help points


The emergency numbers are the part people need most, and they are the same across the country. The primary numbers are
sourced to the Ministry of Communications. 112 and 911 are not emergency numbers in their own right: they are
conditional redirects (see the note below the table).

| Service | Number | Source for the number | Location data |
|---|---|---|---|
| Ambulance (SAMU) | 192 | Ministry of Communications, "Emergência: você sabe para quem ligar quando precisa de ajuda?", published 11 Sep 2026, updated 27 Oct 2026 (opened 21 Nov 2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | not checked |
| Fire (Corpo de Bombeiros) | 193 | Ministry of Communications, "Emergência: você sabe para quem ligar quando precisa de ajuda?", published 11 Sep 2026, updated 27 Oct 2026 (opened 21 Nov 2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | state fire services: not checked |
| Police (Polícia Militar) | 190 | Ministry of Communications, "Emergência: você sabe para quem ligar quando precisa de ajuda?", published 11 Sep 2026, updated 27 Oct 2026 (opened 21 Nov 2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | state police: not checked |
| Conditional redirect to the Brazilian emergency service (mobile phones) | 112 and 911 | [Anatel Resolution 777, article 127](https://informacoes.anatel.gov.br/legislacao/resolucoes/2025/2022-resolucao-777) (opened 21 Nov 2026): redirected only "if technically feasible"; the Anatel codes page lists them as mobile only | state police: not checked |
| Civil defence (Defesa Civil) | 199 | Ministry of Communications, "Emergência: você sabe para quem ligar quando precisa de ajuda?", published 11 Sep 2026, updated 27 Oct 2026 (opened 21 Nov 2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | not checked |

Notes:

- 112 and 911 are conditional redirects. Anatel Resolution 777, article 127, says that, "if technically feasible", a call
  to 112 or 911 is redirected to the matching Brazilian emergency service. A reader should dial 190, 192, 193 or 199
  first; 112 and 911 may not connect.
- The official lists were not checked: the national health register (CNES) and the state fire and police station lists.
  OSM counts for hospitals, clinics, fire and police stations are given under "Help points and counts".
- The number table itself belongs to [issue #261](https://github.com/Immortal-Protocols/lastbook/issues/261), not to
  this map proposal. It is listed here so that the map and the number table agree.

## Checking a map change

- A change to a layer in `web/map.js` is a change you can see: include screenshots in light and dark mode.
- A change to a pack or map tool: `packaging/test_pack_tools.py` and `packaging/scan_pack.py` check what a map set may
  hold, and `scan_pack.py` lists the allowed files under `derived/geo/` (`GEO_FILES`).
- Nothing a contributor adds may make the app open a connection. New data comes in through a build tool and ships as a
  file.

Licences read for this proposal (20 November 2026):

- **ODbL 1.0** (OSM water and points): commercial use allowed; a derivative database is shared under the ODbL; credit
  "© OpenStreetMap contributors". Read on the opendatacommons.org licence page.
- **CC BY 4.0** (Google Open Buildings; the CNES dataset's `cc-by` field): adapt, including commercially, with attribution.
  Read on the creativecommons.org deed.
- **CNES dataset** (`cc-by`, from the dataset licence field): see the caveat under "Help points and counts".
- **Not licensed, so not proposed:** ANA BHO 6 ("free access" only); CPRM SIAGAS (no licence text); gov.br content
  (CC BY-ND 3.0, no adaptation).

## Addresses in Overture, from the publisher's guide

- **Brazil: 89,887,635 addresses**, in the per-country table of the Overture addresses guide
  (docs.overturemaps.org/guides/addresses/, opened 20 November 2026). This is the publisher's count, not one made for
  this proposal. The same table lists the US and Mexico (Mexico 30,726,687, as REGIONS-MX.md reads it).
- Per-state counts were not computed. The first digit of a CEP is not a state code (see below), so splitting on it
  would put addresses in the wrong state.
- The Overture guide says address IDs are not stable enough to register in GERS, so IDs may change between releases.
  A build would need a fixed release.

## How addresses are written

Read from the Correios' *Guia Técnico de Endereçamento de Correspondências* (version 1.4, 2021) and the Correios
addressing guide page: **search snippets only**; the PDF was not opened.

- **Postcode (CEP).** Eight digits, written `00000-000` with a hyphen after the fifth digit, for example `01311-000`
  (the Correios example). The Correios API accepts eight digits without the hyphen. Keep it as text, because leading
  zeros occur.
- **Order.** Street type, street name and number, then complement and neighbourhood, then city and state (UF), with
  the CEP last. The Correios guide puts the CEP alone on the last line of a hand-written address.
- **No number.** Correios writes `SN` (*sem número*, "no number"). The CEP complement is then `00000` (search snippet
  only).
- **The CEP is not a state code.** The first digit is a broad region, not a state, and no CEP-to-state table was
  checked. Address indexes cannot be split by state until one is found or a state polygon is used.
- **What the code does now** (read in this repository, 20 November 2026):
  - `tools/build_addresses.py` keeps only `country = 'US'`; the Brazilian rows would need the country changed.
  - `normalize()` in `engine/address_search.py` replaces every character outside `a-z` and `0-9` with a space, so
    Portuguese accents split words: "Ação" becomes "a o". Accent folding would be needed, as noted for Spanish in
    REGIONS-MX.md.
  - `is_address_query()` needs a number first, so "Rua do Lago 50, 01311" is not treated as an address today.

## Still undecided

Each of these needs the maintainers' decision before any code changes.

1. **Codes in setup.** Whether `BR-AC` and the others are acceptable as a manifest `id`, and the `carry_over()` rule in
   `engine/setup/install.py` (line 335), which keeps only `[A-Z]{2}` index names.
2. **DF and Goiás.** Separate maps, or the Goiás map includes DF (the box overlap, as for CABA in REGIONS-AR.md).
3. **Trindade and Martim Vaz.** A separate small map, or no map. No resident population was checked.
4. **Atol das Rocas and São Pedro e São Paulo.** Not in the IBGE polygons; whether either should have a map.
5. **IBGE licence.** Whether the technical and legal note for the state malha allows a copy in a build.
6. **CEP.** An open CEP-area or CEP-to-state source with clear rights. Without one, address search cannot split by state.
7. **Crop classes.** MapBiomas is a candidate; its licence and class list were not checked, and the crop kinds in
   `tools/build_crops.py` have no Brazilian equivalents yet.
8. **Overlapping boxes.** Boxes follow each state's outline, so neighbours overlap along borders. Whether that is
   acceptable is the same question as in REGIONS-MX.md.
9. **Water sources.** ANA's licence for BHO 6 and CPRM's licence for SIAGAS data are both unanswered. Both fail the test
   until one is named.
10. **CNES.** Confirm that the dataset licence (`cc-by`) governs the CNES data, not the portal footer (CC BY-ND), and
    check that the file has coordinates.

## What was checked, and what was not

- **Opened on 20 November 2026:** the IBGE malhas API, state polygons at maximum quality, for all 27 units; the gov.br
  "Sobre o portal" page and the federal SAMU 192 article (footer licence CC BY-ND 3.0 Brazil); the Anatel public-utility
  and emergency codes page (190, 192, 193, 199, and 112/911 listed as mobile only); on 21 November 2026, the Ministry of
  Communications emergency numbers article and Anatel Resolution 777, article 127 (112/911 redirected only if technically
  feasible); the Overture addresses guide
  (Brazil 89,887,635); the Wikipedia article "ISO 3166-2:BR" (27 codes, names from the ISO 3166/MA).
- **Computed on 20 November 2026:** the 27 tight boxes and the 0.15° margins (floor for west and south, ceiling for
  east and north, to 0.01°); the detached-island check across all 27 units; the Espírito Santo box without Trindade and
  Martim Vaz.
- **Seen only in search results:** the IBGE technical and legal note and the BC250 terms (restricted use); the Correios
  addressing guide; a 2017 federal open-data resolution that lists CC0, PDDL, CC BY 4.0 and ODbL as acceptable.
- **Opened on 20 November 2026 (water and help points):** the Overpass API (OSM counts, eight tags: the 27 unit queries
  completed; the country-wide query timed out); the ODbL 1.0 and CC BY 4.0 licence texts; the ANA BHO 6 metadata record;
  the SIAGAS web portal (no licence text); the CNES dataset page (licence field `cc-by`); the CNES portal footer (CC
  BY-ND 3.0 for the site).
- **Checked on 21 November 2026 (Mato Grosso springs):** the four-quarter Overpass count described under "Help points
  and counts" (31,074 + 19,825 + 40 + 2,641 = 53,580) and a whole-state count (53,580); the object metadata of the
  south-west and south-east quarters; the eight changesets on the OSM API (user, date, created count, `source=SEMA-MT`,
  no comments); the OSM wiki Contributors page and Import/Catalogue (no SEMA-MT entry); the SEMA-MT home page footer and
  the Mato Grosso open-data catalogue (no licence for spring data). The GeoDados MT portal did not load without a
  browser, so it was not read.
- **Seen only in search results:** the Ministry of Health open-data plans (CC BY-NC-SA); the CPRM SIAGAS agreements;
  the ANA open-data policy wording.
- **Not checked:** the ISO Online Browsing Platform (iso.org); the IBGE technical and legal note itself; the CNES health
  register; state fire and police station lists; MapBiomas licence and class list; Google Open Buildings coverage for
  Brazil; per-state Overture address counts; the populations of Trindade and Martim Vaz.

