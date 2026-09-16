# AI Assistant Usage Disclosure — LPDG Challenge

This document records how AI tools were used during development and details specific errors introduced by the AI that were caught and corrected through engineering review.

---

### 1. Concrete Scope of AI Usage

An AI assistant (Antigravity AI / Google DeepMind) was used as a pair-programming tool for:
1. **API & Model Scaffolding**: Drafting initial FastAPI router boilerplate, Pydantic response models, and status code mappings.
2. **Interface Refactoring**: Extracting the baseline ranking logic into an abstract `Ranker` ABC seam (`src/ranking/base.py`) to decouple the API from `SigmaRanker`.
3. **Synthetic Test Data Fixtures**: Generating synthetic parquet telemetry generator routines in `tests/fixtures/generate_fixtures.py` to ensure tests run offline without touching or copying confidential competition dataset rows.

---

### 2. Specific Errors Caught and Corrected

#### Error 1: Synthetic Telemetry Generation Caused Self-Masking (Baseline Overlap Bug)
- **What the AI Did**: When writing the synthetic data fixture for `test_sigma_ranker_detection`, the AI set `offline_duration_sec = 3600.0` continuously for all 168 hours of the recent 7-day window for the anomalous test gateway.
- **Why It Was Wrong**: The baseline 3-sigma algorithm defines its 28-day baseline window as `[end - 28 days, end)`. Because this 28-day baseline overlaps the recent 7-day window (`[end - 7 days, end)`), having 168 hours of continuous 3600-second spikes caused the gateway's baseline mean (~10,425) and standard deviation (`std ≈ 30,550`) to inflate drastically.
  Consequently, `mean + 3 * std` evaluated to `~102,075`, which exceeded the 3,600-second spike! The test failed with `assert 0.0 > 0` because zero hours were flagged.
- **How It Was Corrected**: The engineer recognized the self-masking window overlap bug, corrected the synthetic generator to inject short, sharp spikes (`offline_duration_sec = 1000.0` for 5 hours) against a low-variance baseline, ensuring the breach mathematically exceeded 3-sigma.

#### Error 2: Unanchored `.gitignore` Rule Masked Project Source Code
- **What the AI Did**: In `.gitignore`, the AI included the rule `data/` to prevent committing the 104MB raw telemetry directory.
- **Why It Was Wrong**: In gitignore pattern syntax, an unanchored rule `data/` matches any directory named `data` at any depth in the repository tree. As a result, git quietly ignored the newly created application module directory `src/data/` (including `src/data/loader.py`). If committed, the data loader source code would have been missing from the repository, causing downstream `ModuleNotFoundError` crashes on clean checkouts.
- **How It Was Corrected**: The engineer inspected `git status --ignored`, spotted `src/data/` in the ignored list, and anchored the ignore pattern to the root directory (`/data/`). This ensured that the raw dataset is excluded while `src/data/loader.py` is properly tracked.

---

### 3. Engineering Conclusion

AI assistance was helpful for rapid syntax generation and boilerplate creation, but required active validation against mathematical constraints (statistical baseline overlap behavior) and git configuration rules. All generated code and tests were manually verified via pytest and submission validation scripts.
