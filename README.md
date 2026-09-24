# Danish AIS data analysis

<p align="center">
  <strong>Język / Language</strong><br>
  <a href="#polski"><strong>Polski</strong></a>
  &nbsp;·&nbsp;
  <a href="#english"><strong>English</strong></a>
</p>

---

## Polski

To repozytorium zawiera kopię kodu wymaganego do uzyskania rezultatów pracy magisterskiej. Projekt umożliwia przetwarzanie danych AIS pochodzących ze strony [Duńskiej Administracji Morskiej (Danish Maritime Authority)](https://www.dma.dk/safety-at-sea/navigational-information/ais-data), ich analizę oraz wizualizację.

**Opublikowane wyniki (gotowe dashboardy):** https://amddaa.github.io/danish-ais-map/

### Odtwarzanie wyników

Pełne odtworzenie i uruchomienie kodu wymaga danych, które można pobrać (AIS z aisdata.ais.dk oraz rekordy WPI). Stworzenie środowiska, ETL i pipeline zajmują dużo czasu i nie są rekomendowane, jeśli celem jest tylko obejrzenie wyników - w tym przypadku wystarczy powyższy link.

Praca powstawała etapami, więc odtworzenie w 100% może nie być możliwe bez drobnych zmian (ścieżki, zakres dat, zależności, stan migracji bazy). Oryginalna baza danych w wolumenie Dockera zajmuje około 230 GB. Dostęp do bazy autora pozwala ominąć proces ETL i zajmować się tylko generowaniem widoków albo zmianą algorytmów przetwarzania.

Poniżej znajdują się szczegółowe instrukcje uruchomienia.

### Wymagania wstępne

- Docker i Docker Compose
- uv
- Node.js
- kopia pliku `.env`

#### Zależności Pythona

```bash
uv sync

# Opcjonalnie
uv sync --extra research
```

Skrypty uruchamiaj przez `uv run`:

```bash
uv run python -m source.main
uv run python data/ports/import_terminals.py
```

### 1. Utwórz bazę danych

```bash
docker compose up -d
```

Uruchamia TimescaleDB (Postgres 14) na porcie 5432 oraz pgAdmin pod http://localhost:5050. Pliki SQL z `migrations/` są montowane w `/docker-entrypoint-initdb.d` i wykonują się tylko przy pierwszym utworzeniu wolumenu Postgresa. Nowe migracje na istniejącym wolumenie trzeba zastosować ręcznie przez `psql` albo odtworzyć wolumen.

### 2. Pobierz dane AIS

W razie potrzeby edytuj listę URL w `data/download_aisdk.py`, a następnie pobierz dzienne archiwa ZIP z aisdata.ais.dk. Skrypt zapisuje pliki do `./aisdata/` względem katalogu roboczego (przenieś lub rozpakuj CSV do ścieżki używanej przez ETL):

```bash
uv run python data/download_aisdk.py
```

### 3. Uruchom ETL AIS

Przed uruchomieniem ustaw `CSV_FILES` na początku `source/main.py` na lokalne ścieżki do plików CSV AIS.

```bash
uv run python -m source.main
```

Daty w duńskich CSV są w formacie DD/MM/YYYY. Loader kopiuje dane do tabel TEMP (`COPY`), a następnie scala je do `vessels` oraz hypertable `ais_positions`. Przetworzone pliki są śledzone w `etl_processed_files`.

### 4. Załaduj terminale i porty WPI

Punkty z OSM w `data/ports/baltic_ports.geojson` to terminale do wizualizacji na mapie (`port_terminals`). Rekordy WPI Pub 150 wypełniają tabelę `ports`. Następnie uruchom:

```bash
uv run python data/ports/import_terminals.py
uv run python data/ports_unlocode/import_wpi.py
uv run python data/ports_unlocode/spatial_link_wpi.py
```

### 5. Wizyty w portach i trasy

```bash
uv run python -m source.analysis.ports.generate_port_geofences
uv run python -m source.analysis.ports.port_visit_extractor
uv run python -m source.analysis.ports.aggregate_results
```

JSONL wizyt/rejsów trafia do `source/analysis/ports/output/`. `aggregate_results` buduje JSON analizy tras na mapę.

### 6. Wygeneruj JSON dashboardów

```bash
uv run python -m source.analysis.ports.port_feature_matrix
uv run python -m source.analysis.ports.generate_dashboard
uv run python -m source.analysis.routes.visualize_routes
uv run python -m source.analysis.routes.generate_tracker_data
```

Wyniki trafiają do `web/src/data/` (oraz wykresy weryfikacyjne do `source/analysis/ports/output/plots/`).

### 7. Uruchom interfejs webowy

```bash
cd web
npm ci
npm run build
npm run preview
```

Lokalny development: `npm run dev`.

### Praca tylko na UI / istniejącej bazie

Jeśli wolumen bazy jest już wypełniony, nie uruchamiaj ponownie ETL ani importerów. Aby odświeżyć wyłącznie dashboardy:

```bash
uv run python -m source.analysis.routes.visualize_routes
uv run python -m source.analysis.routes.generate_tracker_data
uv run python -m source.analysis.ports.generate_dashboard
cd web && npm run dev
```

---

## English

This repository holds a copy of the code required to produce the master’s thesis results. The project processes AIS data from the [Danish Maritime Authority](https://www.dma.dk/safety-at-sea/navigational-information/ais-data), then analyses and visualises it (TimescaleDB/PostGIS -> port-call analysis -> static Astro map dashboards).

**Published results (hosted dashboards):** https://amddaa.github.io/danish-ais-map/

### Reproducing results

Full reproduction needs downloadable source data (AIS from aisdata.ais.dk and WPI records). Setting up the environment, ETL, and pipeline takes a long time and is not recommended if you only want to view the results - use the link above instead.

The work was built in stages, so a perfect 100% replay may not be possible without small local adjustments (paths, date ranges, dependencies, database migration state). The author’s original Docker Postgres volume is about 230 GB. Access to that database lets you skip ETL and focus on generating views or changing processing algorithms.

Detailed run instructions follow below.

### Prerequisites

- Docker and Docker Compose
- uv
- Node.js
- `.env` copy

#### Python dependencies

```bash
uv sync

# Optional
uv sync --extra research
```

Run scripts with `uv run`:

```bash
uv run python -m source.main
uv run python data/ports/import_terminals.py
```

### 1. Create the database

```bash
docker compose up -d
```

Starts TimescaleDB (Postgres 14) on port 5432 and pgAdmin on http://localhost:5050. SQL files in `migrations/` are mounted at `/docker-entrypoint-initdb.d` and run only when the Postgres volume is first created. New migrations on an existing volume must be applied manually with `psql`, or recreate the volume.

### 2. Download AIS data

Edit the URL list in `data/download_aisdk.py` if you need different dates, then download daily zips from aisdata.ais.dk. The script writes into `./aisdata/` relative to the working directory (move or unzip CSVs to the path used by the ETL):

```bash
uv run python data/download_aisdk.py
```

### 3. Run the AIS ETL

Edit `CSV_FILES` at the top of `source/main.py` to your local AIS CSV paths before running.

```bash
uv run python -m source.main
```

Danish CSV dates are DD/MM/YYYY. The loader COPY-stages into TEMP tables, then merges into `vessels` and the `ais_positions` hypertable. Processed files are tracked in `etl_processed_files`.

### 4. Load terminals and WPI ports

OSM harbour/marina points in `data/ports/baltic_ports.geojson` are terminals for map visualization (`port_terminals`). WPI Pub 150 records fill the `ports` table. Link them afterward:

```bash
uv run python data/ports/import_terminals.py
uv run python data/ports_unlocode/import_wpi.py
uv run python data/ports_unlocode/spatial_link_wpi.py
```

### 5. Port visits and routes

```bash
uv run python -m source.analysis.ports.generate_port_geofences
uv run python -m source.analysis.ports.port_visit_extractor
uv run python -m source.analysis.ports.aggregate_results
```

Visit/voyage JSONL lands under `source/analysis/ports/output/`. `aggregate_results` builds route analysis JSON for the map.

### 6. Generate dashboard JSON

```bash
uv run python -m source.analysis.ports.port_feature_matrix
uv run python -m source.analysis.ports.generate_dashboard
uv run python -m source.analysis.routes.visualize_routes
uv run python -m source.analysis.routes.generate_tracker_data
```

Outputs go into `web/src/data/` (and verification plots under `source/analysis/ports/output/plots/`).

### 7. Run the web UI

```bash
cd web
npm ci
npm run build
npm run preview
```

Local development: `npm run dev`.

### Read-only / UI-only work (existing DB)

If the database volume is already populated, do not re-run ETL or importers. To refresh dashboards only:

```bash
uv run python -m source.analysis.routes.visualize_routes
uv run python -m source.analysis.routes.generate_tracker_data
uv run python -m source.analysis.ports.generate_dashboard
cd web && npm run dev
```
