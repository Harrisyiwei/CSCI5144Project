# When does smarter storage tiering outperform S3 Intelligent-Tiering?
Midterm implementation for CSCI 5144, Fall 2026.
Team from supplied proposal: Jerich Bryant, Hugo Artajona Sazatornil, Harris Li.

## Start here
Python 3.10+ is sufficient for the simulator and tests. No AWS account, credentials, paid resources, or third-party packages are needed for them.

```bash
cd project
python3 -m unittest discover -s tests -v
python3 simulator.py --output results
python3 simulator.py --trace results/example_trace --days 180
```
Optional figures: install matplotlib, then `python3 analyze.py`.
The bundled results are genuine outputs of the included code, not AWS observations.

## Included work
- Four policies: Standard, age-30 lifecycle into Standard-IA, modeled Intelligent-Tiering (three instant tiers), and an EWMA adaptive Standard/Standard-IA heuristic.
- Five synthetic workloads and five seeds: 100 main runs.
- Size, migration fee, and controller overhead factorial sweep: 270 runs.
- Retention-horizon experiments for cold and mixed workloads: 96 runs.
- 15 unit tests with analytical and boundary checks.
- CSV importer/exporter, raw cost breakdowns, daily costs, summary statistics, optional figures.
- 466 runs total. Main runs use 240 objects, sensitivity/horizon runs use 120.

## Scope and billing conventions
`Prices` in simulator.py is the complete editable rate configuration. Numeric rates are illustrative us-east-1 style inputs, not a retrieved live rate card. Verify them before final experiments or any budget estimate. GB uses 2**30 bytes, month uses 30 days. Storage accrues daily. All objects start on day 0 and expire at the horizon. Minimum-duration balances are settled at expiration and on adaptive copies out of IA.

All synthetic reads are full-object GETs, with at most one GET/object/day. The trace importer accepts multiple GETs per day. IT uses the same GET rate as Standard, charges eligible-object monitoring, moves idle eligible objects at days 30 and 90, returns accessed objects to Frequent Access, and charges no internal transition/retrieval fees. Optional asynchronous archive tiers are disabled. Objects below 128 KiB stay at Frequent Access without monitoring. Day-level access promotion bills the accessed day at Frequent Access.

Lifecycle always moves eligible objects at age 30, irrespective of reads, and never promotes. Thirty days is our chosen rule, NOT an asserted AWS earliest-transition constraint. AWS removed that constraint in July 2026. Adaptive can demote after seven completed days. It compares a 30-day expected IA cost against Standard using a 0.2 EWMA of observed daily counts. It requires a 10% advantage and seven idle days to demote. Promotion includes a full-object IA source retrieval, source GET, destination PUT and any remaining minimum-duration balance. Migration sensitivity scales modeled transition/copy service costs, not storage penalties or user GETs.

Included cost components: initial PUT, storage, user GET requests, IA user retrieval, lifecycle/copy migration, IT monitoring, IA minimum duration and configurable adaptive controller overhead. Excluded: common egress, replication, versioning, taxes, free tier, volume discounts, KMS, inventory/log collection and actual controller infrastructure. Controller defaults to zero and is swept separately. This is a scoped policy model, not a complete AWS bill.

## File map
- simulator.py: workloads, prices, policies, cost accounting, trace I/O, experiment runner.
- tests/test_simulator.py: accounting, causality, thresholds, small-object handling, trace round trip.
- analyze.py: aggregation and reproducible scientific figures (optional matplotlib).
- results/runs.csv: 100 main runs and all cost components.
- results/summary.csv: means, sample SD, paired savings and approximate t confidence interval half-width.
- results/daily.csv: seed-17 main-run cumulative costs.
- results/sensitivity.csv: all 270 sensitivity runs.
- results/horizons.csv: 96 retention experiments using prefixes of the same 180-day trace per scenario and seed.
- results/example_trace/: objects.csv and sparse reads.csv for the mixed seed-17 workload.
- results/metadata.json: experiment configuration.

## Import your own trace
objects.csv: columns `id,size_bytes`, one unique object ID per row.
reads.csv: columns `day,object_id,count`, zero-based integer days and nonnegative integer counts. Rows may be sparse. Objects must already exist at day zero and retain their original size. Adapt real traces explicitly if they include writes, partial reads, creation/deletion, or changing object sizes. Do not silently treat missing sizes as measured sizes.

## Honest midterm status
The local simulator and synthetic experiments are complete. No deployment, real AWS billing validation, measured latency study, real-world trace evaluation, or external proposal feedback was supplied or completed. Presentation speaker assignments are proposed speaking responsibilities, not evidence of historical individual contributions. The full project continues after midterm.
