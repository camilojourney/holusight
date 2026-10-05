# 030 - Source duplication evaluation and honest coverage

Status: bounded evaluation of the current deterministic helper, not the retired retrieval product.

## Recommendation

**Limited use:** Python structural duplicate/fact candidate navigation, with source review and caller/context inspection. **Do not use** as a general semantic clone detector, architecture/code-smell quality gate, repair oracle or release-readiness certification. TypeScript/Swift are not analyzed. No productivity or discovery advantage was proved.

The changes correct two end-user symptoms reproduced before implementation:

- A mixed Python/Swift inventory reported `ok`, `complete: true`, exit 0 while silently omitting Swift. Recognized unsupported selected sources now make alignment partial/incomplete and remain metadata-only. Existing ignore/root/symlink constraints remain; scope does not isolate private data.
- Normalizing a local parameter to `local_0` made `arg + local_0` and `arg + arg` indistinguishable. Impossible parsed-identifier sentinels preserve external names. v3 rejects old receipts rather than interpreting changed candidate IDs as a repair.

No dependencies, product commands/flags, API methods, environment variables, model calls, graph refresh or automatic source edits were added.

## Protocol

The protocol and synthetic oracle were frozen at baseline `9edae9f` before fixes. Seven tuning pairs and ten distinct held-out pairs cover copies, renamed locals, constants, operators, external names/defaults/decorators/attributes, closures, keyword calls, exception/pattern bindings and intentional fixture copies. Held-out results were first inspected after the correction was fixed. Identical intentional fixtures are clone positives, **not defect positives**.

Public selections are deterministic, independent of Holusight output, and never used for tuning. Each pair is scanned through `python -m holusight align` in an independent code-only Git root. Positive prediction requires one emitted `code_duplicate` group containing both paired files. TP/FP/TN/FN retain original semantic labels or explicitly identified problem-class proxies; incomplete/invalid cases stay in the denominator. Precision/recall with zero denominators are undefined, not perfect.

For stand-alone pair archives, split the unmodified bytes at the second zero-to-three-space `def`/`async def` header only if exactly two such headers exist. Do not correct indentation, Python 2 syntax or malformed operators. Unframed cases count as unpredicted/incomplete. This framing is a subset-adapter limitation, not a dataset verdict. Whole-program submissions are never wrapped into artificial functions.

## Primary sources and applicability

All URLs below are public. Corpus code/scripts were treated as data, never imported/executed. No benchmark website received private code. Search summaries contained incorrect repository names and conflicting license claims; direct repository/Zenodo metadata checks take precedence.

| Lead | Verified version/source, license and access | Fit/disposition |
|---|---|---|
| BigCloneBench | https://github.com/clonebench/BigCloneBench at `37f6c7141dac914d7eb13c09a967c6ce1a821f91`; README prefers v2 via https://github.com/jeffsvajlenko/BigCloneEval. Database CC BY-NC 4.0; underlying IJaDataset retains individual licenses. Java; full validation artifacts require author contact and large OneDrive downloads may require login. | Inapplicable language. No full run or Java result claimed. |
| CodeXGLUE clone detection | https://github.com/microsoft/CodeXGLUE at `ac74a62802a0dd159b3258c78a2df8ad36cdf2b9`; https://github.com/microsoft/CodeXGLUE/tree/ac74a62802a0dd159b3258c78a2df8ad36cdf2b9/Code-Code/Clone-detection-BigCloneBench; https://arxiv.org/abs/2102.04664. Root README: tools MIT, data C-UDA. BCB binary semantic labels; 901,028 train / 415,416 dev / 415,416 test pairs. POJ-104 is C/C++ semantic retrieval. | Java and C/C++ unsupported; other CodeXGLUE tasks are not duplication/architecture checks. No model training, official submission or full result claimed. |
| GPTCloneBench | https://github.com/srlabUsask/GPTCloneBench at `d3e953916b9323fe1fbc55c8418a2b05f7b649ed`; https://arxiv.org/abs/2308.09680; https://doi.org/10.5281/zenodo.10198952. Repo software MIT; benchmark README specifies CC BY-NC-ND for data. Public existing ZIP, no OpenAI key needed to read it; generating new pairs would require a key and was not attempted. | Python near-miss/semantic stress subset and high-syntactic controls run. Cross-language sets are inapplicable. `false_semantic_clones` are high-similarity controls, **not validated functional non-clones**; never score them as semantic FP/TN. |
| SemanticCloneBench | Original paper cited by upstream: https://doi.org/10.1109/IWSC50091.2020.9047643 semantic/crowd-sourced clone benchmark; authoritative download linked in GPTCloneBench README: https://drive.google.com/open?id=1KicfslV02p6GDPPBjZHNlmiXk-9IoGWl. Archive contains 1,000 standalone Python pair files. Public Drive download used its offered confirmation form, no login/credentials or scripts. No single benchmark-wide license independently confirmed; underlying systems retain their licenses. Do not redistribute data or assume unrestricted commercial use. | Python semantic stress subset run, not architectural validation. Full original language suites not run. |
| Project CodeNet Python800 | https://github.com/IBM/Project_CodeNet at `55c323b527ab3d6510d55edff188bc0a0d7bc5e5`; https://arxiv.org/abs/2105.12655. Official IBM storage artifact v1.0.0: https://codait-cos-dax.s3.us.cloud-object-storage.appdomain.cloud/dax-project-codenet/1.0.0/Project_CodeNet_Python800.tar.gz (30,641,525 bytes, 800 classes, 240,000 Python programs). Repo tools Apache-2.0; archive contains no license. Historical licensing page https://developer.ibm.com/exchanges/data/all/project-codenet/ returned HTTP 404; search claims of CDLA version could not be directly verified. No raw-data redistribution or commercial licensing assurance. | Bounded same/different-problem class-proxy stress subset run. Problem equality is not a proof of exact semantics; different problems can share helpers. Full 7.8 GB CodeNet and all-pairs semantic evaluation are infeasible/inapplicable to bounded whole-function checking. |
| MLCQ | https://zenodo.org/records/3666840 / https://doi.org/10.1145/3383219.3383264; verified metadata version 1.1, CC BY 4.0, nearly 15,000 professionally reviewed Java samples; CSV 7,513,770 bytes. | Java code-smell classification, not Python duplicate pairs; inapplicable, not run. |
| SmellBench | https://zenodo.org/records/19247588 / https://arxiv.org/abs/2605.07001; verified Zenodo metadata CC BY 4.0, `ExperimentsReproductionPackage.7z` 6,310,819 bytes. | Architectural smell **repair** experiments. Holusight does not classify smells or repair repositories. Inapplicable, not run; no model/agent setup introduced. |
| CloneBench / PyClone-Stream | CloneBench is an ambiguous lead, not a separately verified Python corpus. PyClone-Stream search found a paper lead but no verified public downloadable labeled artifact or maintained repo. | Unverified/unavailable artifacts, not omitted passes. No self-growing scraper or corpus-generation service built. |

License/access uncertainty is deliberately preserved. These are local experimental results, not permission to redistribute benchmark corpora. Benchmark sources are pinned but not vendored into Holusight.

## Reproducible subsets and results

`tests/test_clone_benchmarks.py` is a small opt-in CLI adapter, not an automatic benchmark service. Its default pytest tests exercise only framing/scoring safety and need no datasets. Put the three inspected archives in a task-local `PUBLIC_DATA` directory. It verifies these artifact SHA-256 values before analysis:

- GPTCloneBench semantic stand-alone ZIP: `22fc617d8980f4c54df1d62fd2804f313c86f8fcefff84d8ff6a657c84cdf516`.
- SemanticCloneBench ZIP: `d5601ad925dd26b942676cabef88a68b799668f0b6d2d01f0d63db46d2584643`.
- Python800 tar.gz: `39297d11df8030ce0b6619e678547a738d74c4715c5c9a5be0af83941a5587b0`.

Selections: lexicographically first 100 Python filenames in each of GPT true-semantic, GPT high-syntactic control and SemanticCloneBench standalone groups. Python800: first 101 sorted problem IDs; first two sorted submission filenames for each of the first 100 problems are positive class proxies, first file against the next problem's first file is a negative class proxy. No training or output-based filtering; counts include unsupported Python syntax and below-threshold functions.

Example in a provisioned POSIX environment, with results outside checked source (on macOS, also deny network/consumer access with `sandbox-exec`):

```sh
uv run --offline python tests/test_clone_benchmarks.py "$PUBLIC_DATA" "$NEW_RESULT_DIR"
# baseline: run the same adapter with baseline 9edae9f's src/ on PYTHONPATH,
# or in an isolated environment installed from that revision; do not use a legacy global holus.
```

Baseline and final results were identical on these **500 selected public cases**, not official full benchmark results:

| Subset | TP / FP / TN / FN | Precision / recall | Coverage limitations |
|---|---|---|---|
| GPT true-semantic (100) | 1 / 0 / 0 / 99 | 1.00 / 0.01; no validated negatives, so precision is uninformative | Across all 200 GPT cases: 9 unframed, 100 parse-error pairs, 109 incomplete, 53 with both files containing eligible functions. High-syntactic controls: 0/100 candidate yield, unscored. |
| SemanticCloneBench (100 positives) | 0 / 0 / 0 / 100 | undefined / 0.00 | 31 incomplete/parse-error pairs; 32 both-eligible pairs. |
| Python800 (200 class proxies) | 0 / 0 / 100 / 100 | undefined / 0.00 | 41 incomplete/parse-error pairs; 19 both-eligible pairs; mostly whole programs outside function scope. |

Final elapsed CLI time was approximately 9.46 s GPT, 5.10 s SemanticCloneBench and 9.94 s Python800. Max child-process RSS was about 25 MB on macOS (cumulative maximum over child executions, not whole-adapter memory). Timing is observational, not a productivity benchmark. The public adapter may differ slightly in orchestration overhead.

Frozen synthetic relation tests: baseline 5 TP, 3 FP, 9 TN, 0 FN (precision 0.625, recall 1); final 5 TP, 0 FP, 12 TN, 0 FN (precision/recall 1). Tuning: 2 positives/5 negatives; held-out: 3 positives/7 negatives. This tiny targeted regression set demonstrates the collision correction only, not broad clone-detection performance.

Two independently allowlisted private app-source examples were scanned locally without egress. Aggregate inventory: 419 files, 262 Python and 157 unsupported sources; candidate groups retained while full reports changed from falsely complete to partial. A narrower supported-only scope remains usable. Detailed source locations, caller evidence, intentional-copy dispositions and consumer preservation checks stay in the private task report, not this repository.

## Validation boundaries

Configured lint/format/pytest and wheel/sdist/installed CLI smoke must pass at the final committed head. There is no configured type checker. Historical Graphify queries remain stale and refer to retired source; no graph rebuilt and no current architectural inference made. Consumer graph/config/knowledge data are not included in source-only snapshots, so graph commands correctly report unavailable there.

Low semantic recall is not a success metric hidden behind supported coverage. The recommended workflow is: verify coverage, inspect candidates and actual callers, classify intentional boundaries, propose the smallest independently tested refactor, then rerun. No candidate proves semantic truth, refactor benefit or correct repair.
