# LPDG Gateway Ranking Service — Project Overview

This repository contains the software wrapper and web API built around the LPDG 3-sigma anomaly ranking baseline for the **LPDG Innovation Hub Selection Challenge 2026** (Software Development Track).

---

## 1. System Overview

The service analyzes hourly gateway telemetry (offline durations, disconnections, and reboot counts) across a rolling 28-day baseline window to identify gateways experiencing statistical anomalies. Every week, it scores and ranks gateways to identify the top 15 candidates for physical site inspection by field technicians.

The project is structured into three decoupled layers:
- **Ranking Engine**: An abstract `Ranker` seam implemented by `SigmaRanker`, which wraps the baseline 3-sigma calculations without changing the underlying statistics.
- **Data Access Layer**: A dynamic `DataLoader` that re-reads parquet partitions directly from disk on demand, ensuring newly added telemetry files are processed immediately without server restarts.
- **Web API**: A FastAPI service exposing endpoints for retrieving weekly predictions, explaining individual gateway status, and triggering pipeline runs on demand.

---

## 2. Running the Project

### One-Command Execution
You can run the full pipeline and validate the submission with standard commands:

- **Run the pipeline**:
  ```bash
  python baseline_3sigma.py --data ./data --out ./predictions.csv
  ```
  *(Or with Make: `make run`)*

- **Validate the output CSV**:
  ```bash
  python validate_submission.py --path ./predictions.csv
  ```
  *(Or with Make: `make validate`)*

- **Run automated test suite**:
  ```bash
  python -m pytest -v tests/
  ```
  *(Or with Make: `make test`)*

- **Start the Web API server**:
  ```bash
  python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
  ```
  *(Or with Make: `make serve`)*

### Using a Custom Data Path
By default, the code expects data in `./data`. To point to data in another location:
- For the script: pass `--data /path/to/data`
- For the API: set the environment variable `DATA_DIR=/path/to/data`

---

## 3. Web API Endpoints

Once the API server is running, the interactive documentation is accessible at `http://127.0.0.1:8000/docs`.

### Endpoint 1: Weekly Top 15 Predictions
- **Path**: `GET /predictions/{week_start}`
- **Description**: Returns the 15 ranked gateways for a given Monday (format `YYYY-MM-DD`).
- **Example**: `GET /predictions/2026-02-02`
- **Output**: List of 15 gateways with their rank (1–15), score (flagged hours beyond 3-sigma), and an operational reason.
- **Error Handling**: Returns `422 Unprocessable Entity` if the date is malformed or not a Monday; returns `404 Not Found` if no data exists for that week.

### Endpoint 2: Explain a Gateway
- **Path**: `GET /gateways/{gateway_id}/explain?week={week_start}`
- **Description**: Provides an explanation of why a specific gateway was ranked where it was, detailing which metrics exceeded 3-sigma.
- **Example**: `GET /gateways/02441029/explain?week=2026-02-02`
- **Error Handling**: 
  - If the gateway does not exist in the dataset for that week: returns `404 Not Found`.
  - If the gateway exists in the dataset but was **not** in the top 15: returns `422 Unprocessable Entity` with an explicit explanation (e.g., `"Gateway is present in dataset but was NOT ranked in that week's top 15"`).

### Endpoint 3: Re-Run Pipeline (Hot Reload)
- **Path**: `POST /run` (optional query: `?week=YYYY-MM-DD`)
- **Description**: Re-reads parquet telemetry from disk, recomputes rankings, and refreshes the served predictions.
- **Live Ingestion**: Reads fresh partitions dropped into `./data/telemetry/` while the service is actively running without requiring a process restart.
- **Concurrency**: Returns `409 Conflict` if a pipeline run is already in progress.

---

## 4. Architecture & Interface Seam

The architecture strictly decouples the API from the ranking logic:

```
src/
├── ranking/
│   ├── base.py             # Abstract Ranker interface and GatewayRanking schema
│   └── sigma_ranker.py     # Concrete SigmaRanker wrapping baseline statistics
├── data/
│   └── loader.py           # Re-readable parquet data access layer
└── api/
    ├── main.py             # FastAPI application relying only on Ranker abstraction
    └── schemas.py          # Request and response models
```

The API layer only interacts with the `Ranker` abstract base class through dependency injection. To replace the statistical ranker with an ML model or heuristic ranker in the future, one only needs to implement the `Ranker` interface and update the dependency injection provider; no API route or handler code needs to be modified.

---

## 5. Test Suite & Validation

The test suite in `tests/` covers:
- **Synthetic Data Fixtures**: Small, hand-crafted telemetry datasets used for offline testing without copying confidential dataset rows.
- **Data Loader Tests**: Verifies disk re-reading and missing-directory error handling.
- **Ranker Tests**: Checks 3-sigma threshold detection and deterministic mergesort tie-breaking.
- **Bug-Driven Tests**: Tests written specifically for edge cases discovered during development (zero-variance baselines and stale cache reload).
- **End-to-End API Tests**: Exercises the entire flow from synthetic parquet files to HTTP requests and asserts on status codes and response bodies.

---

## 6. What It Cannot Do (Known Limitations)

1. **Baseline Window Overlap**: The 28-day baseline window includes the 7-day recent evaluation window. When a gateway degrades severely, its own recent spikes inflate its baseline mean and standard deviation, raising its threshold and partially masking the fault.
2. **Zero-Variance Gateway Blindness**: A gateway with zero variance in the baseline (e.g. constant 0 reboots for 28 days) produces `std = 0`. The baseline logic replaces 0 with `NaN` and fills comparisons with `False`, silently ignoring sudden first-time anomalies.
3. **No Memory Across Weeks**: The ranker evaluates each Monday independently. A gateway with an ongoing month-long fault will be recommended repeatedly, wasting €380 technician visits if work orders are not reconciled.
4. **Blindness to Silent Gateways**: A completely dead gateway that stops transmitting records generates zero telemetry rows and is therefore never flagged by counter breach logic.
5. **No Partition Deduplication**: The loader assumes clean data. Overlapping partition files with duplicate hourly timestamps are not reconciled before aggregations.

---

## 7. Submission Deliverables Summary

- `predictions.csv`: 120 rows across 8 weeks, strictly validated via `validate_submission.py`.
- `DECISIONS.md`: The five key architectural choices made and defended.
- `AI-USAGE.md`: Detailed account of AI tool assistance and bugs caught during development.
- `WHAT-IT-CANNOT-DO.md`: Comprehensive analysis of baseline limitations and recommended future improvements.
