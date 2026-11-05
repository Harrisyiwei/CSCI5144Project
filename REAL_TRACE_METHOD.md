# Real-access-trace integration: CLUE-LDS + modeled IBM sizes

## Purpose
Use **actual observed access timestamps** in Harris's original Python storage-tiering simulator, while preserving all four policies and his original synthetic experiments. No S3 services are invoked: all dollar figures are calculated by the same illustrative price model in `simulator.py`.

## Data and provenance
- CLUE-LDS: Nextcloud-like enterprise cloud-file events, source Zenodo DOI `10.5281/zenodo.7119953`. Our source file was extracted by hashing original file paths, keeping one of 128 hash buckets, and filtering `file_accessed` events. Source sample: **94,071 event rows and 14,256 anonymized object IDs** spanning 2017–2022.
- IBM Object Store SNIA sample: 543 unique sampled object sizes. The original CLUE records **do not include object sizes**. Sizes in `data/clue_ibm_objects.csv.gz` were randomly assigned *with replacement* from IBM's empirical size sample using random seed 5144. They are **not observed sizes of the CLUE files**.
- Both compressed inputs are bundled under `data/` and can be processed without uploading or extracting the 635 MB full CLUE archive.

## Cohort and modeling assumptions
1. Choose an evaluation start **2019-01-01**. Look backward **90 days** (2018-10-03 through 2018-12-31, inclusive). Choose only objects with one or more events in that history window. This prevents picking objects based on future accesses.
2. There are **5,841 selected objects**. A total of **12,579** recorded CLUE `file_accessed` events concern those objects during the following **180 days** (2019-01-01 through 2019-06-29 inclusive). Of those objects, **1,477** had at least one event and **4,364** had no recorded event during those 180 days.
3. We construct a hypothetical fresh S3 bucket **at the evaluation start** containing all 5,841 selected objects. All policies begin in their initial storage state and pay initial PUTs; no actual S3 uploads occur.
4. Assume **all objects persist throughout the chosen 90-, 180-, or 365-day evaluation period**. We cannot infer original file creations, deletions, or preservation from read events alone. This is especially consequential for cold/once-accessed objects; treat results as *fixed-retention sensitivity scenarios*, not reconstructed real AWS bills.
5. Convert each `file_accessed` event into one simulated full-object GET, counting same-day duplicate events separately. This is a proxy: Nextcloud file-access events do not necessarily map one-to-one to S3 GET requests. Objects that first appear during evaluation are excluded, not initialized using future observations.
6. Historic access events only select the cohort; they are **not** used to preload Intelligent-Tiering inactivity counters or the adaptive EWMA. Timers and predictions restart on day zero because the objects are modeled as newly uploaded.
7. The original Harris `simulator.py` is **unchanged**. Billing rates are illustrative and omit some real S3 charges. The output costs should not be interpreted as real AWS invoices. Policies make decisions using only access counts from completed simulation days.

## Reproducible commands (Windows PowerShell)
From this directory with Python 3.10+:

```powershell
py -m pip install -r requirements.txt
py -m unittest discover -s tests -v
py real_trace.py
py run_real_sensitivity.py
```

The first runner creates `results/real_trace/{imported_trace/,results.csv,daily.csv,metadata.json,real_trace_policy_costs.png}`. The second adds `sensitivity.csv`, `size_sensitivity_summary.csv`, and `sensitivity_meta.json`. Both use local data files and require no AWS account. The figure requires matplotlib, listed in `requirements.txt`.

For a different 90-day evaluation horizon:

```powershell
py real_trace.py --days 90 --output results/real_90
```

For a different IBM size assignment:

```powershell
py real_trace.py --size-seed 29 --output results/size_seed_29
```

For a new evaluation window (ensure a full history window exists):

```powershell
py real_trace.py --start 2018-07-01 --days 180 --output results/real_2018
```

## Preliminary results — one IBM size assignment (seed 5144)

| Horizon | Standard | Lifecycle | Intelligent-Tiering | Adaptive EWMA | Adaptive savings vs IT |
| --- | ---: | ---: | ---: | ---: | ---: |
| 90 days | $2.344 | $1.668 | $1.689 | $1.518 | +10.1% |
| 180 days | $4.656 | $2.983 | $2.285 | $2.903 | -27.0% |
| 365 days | $9.405 | $5.612 | $3.219 | $5.632 | -74.9% |

The 90-day row is a **different evaluation horizon**, not a run that starts over from day 90; all horizons start on Jan 1, 2019, using exactly the same cohort and original IBM size assignments. The adaptive heuristic is cheaper at 90 days because it can promote cold objects into Standard-IA after seven idle days, whereas Intelligent-Tiering has a 30-day inactivity threshold. At 180–365 days, Intelligent-Tiering's lower-priced Archive Instant Access tier pays off in this modeled cohort. The observed access distribution is very uneven across those time windows. Do not attribute the crossover solely to time without considering the changing workload and assumed retention.

At 180 days, five independent **IBM size assignments**, holding the *same CLUE access histories*, produced adaptive savings ranging from **-32.6% to -26.3%** relative to Intelligent-Tiering, with a mean of **-28.3%**. These five draws are **not five independent cloud workloads**, and the reported range is *not a confidence interval*.

## Limits and recommended improvements
- Incorporate CLUE creation/deletion events (if available) or bound object lifetimes, rather than assuming fixed retention.
- Compare alternative 90-day historical windows and sensitivity to the beginning of evaluation, not only Jan 2019.
- Broaden/validate the IBM object size distribution. The current deduplicated sample is just 543 objects; its strong concentration of small objects may affect S3 eligibility.
- Verify published AWS rates and storage-class rules in a chosen region. Instrument pricing/controller overhead instead of hardcoding no controller cost.
- Preserve real event timestamps and object identities. Never train an ML model on test-period information.

## File map
- `real_trace.py`: importer, prospective cohort selection, S3-policy replay, cost chart, results export.
- `run_real_sensitivity.py`: controlled size-assignment replicates and retention-horizon comparisons.
- `tests/test_real_trace.py`: tests of no-lookahead cohort membership, CSV interoperability, accounting, exact date boundaries, source sample totals, and seed reproduction.
- `data/*`: processed and anonymized CLUE timestamps/IDs and modeled IBM size inputs; no raw user identities.
- `results/real_trace/*`: complete reproducible outputs, including metadata stating all assumptions.
