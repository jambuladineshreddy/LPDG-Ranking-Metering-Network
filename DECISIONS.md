# Architectural Decisions

Five choices made during development, the alternatives considered, and why they were rejected.

---

### 1. Specialization Area: Software Development (Not Data Science or ML)

- **Choice Made**: Selected the **Software Development** track for Part 2.
- **Alternative Considered**: Data Science (optimizing visit decision thresholds) or Machine Learning (training a predictive model on historical field visits).
- **Why It Was Rejected**:
  - In a timed challenge, Software Development provides objective, mechanically checkable evaluation criteria: a decoupled architecture, reliable API endpoints, dynamic data re-reading, error handling, and end-to-end automated tests.
  - Data Science requires defining and defending what "needs a visit" means under noisy, unverified field visit labels.
  - Machine Learning requires beating baseline total costs without overfitting on only ~320 gateways across 8 months.
  - A rushed ML model that generates false alarms costs €380 per wasted technician dispatch. Delivering a robust, extensible software wrapper around a known baseline provides immediate operational reliability without introducing uncontrolled false positives.

---

### 2. Ranking Algorithm: Kept Baseline 3-Sigma Logic Unchanged Inside a Clean Seam

- **Choice Made**: Preserved the statistical logic from `baseline_3sigma.py` exactly as provided, isolating it behind an abstract `Ranker` interface (`src/ranking/base.py`) implemented by `SigmaRanker` (`src/ranking/sigma_ranker.py`).
- **Alternative Considered**: Tuning the threshold (e.g., dropping to 2.5-sigma) or introducing heuristic weighting between disconnection counts, reboot counts, and offline duration.
- **Why It Was Rejected**:
  - The challenge instructions explicitly state that the Software Development track is evaluated on software quality (clean interfaces, API contracts, tests, error resilience), not algorithm improvements.
  - Adjusting thresholds without operational feedback or ground-truth verification risks increasing €380 false visits.
  - By establishing an abstract `Ranker` seam, the API layer depends strictly on `Ranker.rank_week()` and `Ranker.rank_all()`. A Data Science or ML model can be dropped in later without altering a single line of API routing or serialization code.

---

### 3. Tie-Breaking: Enforced Deterministic Sorting on `["flagged_hours", "gateway_id"]`

- **Choice Made**: Implemented deterministic stable sorting using `mergesort` with `flagged_hours` descending and `gateway_id` ascending as secondary key.
- **Alternative Considered**: Leaving pandas' default quicksort on `flagged_hours` alone.
- **Why It Was Rejected**:
  - In many weeks, dozens of gateways tie with identical scores (frequently 0 flagged hours).
  - An unstable or single-column sort yields arbitrary ordering that varies across operating systems, Python minor versions, or pandas releases.
  - In an operational context where predictions must be reproducible and auditable, non-deterministic outputs between runs are unacceptable.

---

### 4. Data Access: Re-Reading Parquet Telemetry on `/run` (No Stale Caching)

- **Choice Made**: Designed `DataLoader` to re-scan and re-read parquet files directly from disk whenever `POST /run` is invoked.
- **Alternative Considered**: Reading the dataset once into a global in-memory pandas DataFrame at process startup.
- **Why It Was Rejected**:
  - In utility operations, telemetry arrives continuously in monthly parquet partitions dropped into `./data/telemetry/` while the service is running.
  - Caching at startup would mean `/run` serves stale predictions until the Uvicorn process is manually restarted.
  - While re-reading parquet files from disk adds slight I/O overhead on `/run`, ranking runs occur infrequently (e.g., once a week or on-demand). Correctness and freshness outweigh startup caching speed.

---

### 5. Output Policy: Emitting 15 Rows as a Hard Cap, Not Equal Visit Recommendations

- **Choice Made**: Always emitted exactly 15 rows per week to satisfy the submission schema, but explicitly flagged sub-threshold gateways in the `reason` column (e.g., `"no metric over 3 sigma — below action threshold"`).
- **Alternative Considered**: Truncating the output to only genuinely anomalous gateways, or emitting all 15 rows with identical actionable phrasing.
- **Why It Was Rejected**:
  - Truncating would violate the 120-row submission validation contract (`validate_submission.py`).
  - However, treating all 15 rows as equally actionable is financially irresponsible: dispatching a field technician to a healthy gateway wastes €380.
  - Emitting 15 rows satisfies the structural contract, while the plain-language reason column signals to the operations manager: "these slots are filled to satisfy the cap, but these specific gateways do not exhibit active anomalies."
