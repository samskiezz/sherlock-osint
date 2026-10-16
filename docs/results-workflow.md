# From evidence to readable results

The application opens on **Case results**. The evidence board is an optional
curation view rather than a prerequisite for reading analysis.

1. Add one or more files, or queue an authorised public source URL. Originals are
   preserved by hash and extracted in the existing network-disabled processor.
2. Successful extraction immediately creates a durable, deduplicated analysis run.
   Compatible text, source-integrity, image and comparison checks are selected
   automatically. The periodic scanner recovers pending work after restart and
   reaches originals older than the newest 500 records.
3. Read a source notebook: exact excerpts, extracted information, progress,
   negative results, failures and the full saved output of each check. Open a cited
   passage in its original context. No model is required for this reading workflow.
4. Download a source report or the case report. Case findings, AI proposals, open
   questions and acquisition failures retain their separate labels. Source reports
   also have JSON exports. Case Markdown streams one source at a time.

The analysis worker continues when the browser closes. Refreshing, searching,
reading results and exporting reports never launch analytical work. A completed
check is a computation result, not automatic confirmation of an allegation.

## Finding and using the backend capabilities

**All tools & workspaces** lists the actual executable catalogue, with family and
text search, automatically selected checks, saved status and applicability reasons.
Every specialist workspace is directly linked. A selected tool has an input form
and a readable output panel; source text is taken from the selected original,
never silently replaced by a demonstration input. Dataset-dependent tools still
need an actual dataset, and keyed methods need their actual key.

**Saved execution history** pages through durable runs, including operations with
explicit inputs and no evidence binding. Opening a run updates the URL, so its
result can be bookmarked and restored after reload. Source-dependent historical
outputs are withheld if a current source or saved output digest no longer verifies;
raw immutable workflow records remain available to the audit interface.

**Analyze pending now** queues a bounded recovery pass. **Retry automatic analysis**
creates a fresh compatible pass for one source, retaining old receipts and refusing
to duplicate a queued, running or paused pass. **Retry extraction and analysis**
appears when an intact original has missing or inconsistent text derivatives.
It cannot repair changed or omitted original bytes; those require the correct file.

## Boundaries shown in the interface

- Notes and proposed claims without originals are excluded from completed source
  analysis. Missing historical originals are not regenerated as evidence.
- Text extraction, literal dates/identifiers and exploratory comparisons can run
  locally. Optional model-written interpretation, external discovery and hybrid
  search require their configured services, models, credentials and network access.
- A partial run retains its completed outputs and its failures. Negative checks
  display "no matches" rather than disappearing. Original, extract, comparison
  source and stored-output bindings are checked before source results are shown.
- The source list is paginated. A notebook includes its latest automatic pass and
  up to 100 additional specialist receipts, with an explicit truncation notice.
  Older runs remain in execution history. A case Markdown export covers up to
  100 originals and states the limit when exceeded; individual reports remain
  available for other sources.
- The entity browser provides its separate ERPS provenance and retraction controls.
  This interface change does not remove its 10,000-mention workspace limit.
- A source push and workspace health do not publish a hosted application. The
  existing private external address needs its service and relay bindings before
  end-to-end access can be verified. See [remote access](erps.md#access-from-another-device).

## Maintained checks

```bash
.venv/bin/python -m pytest -q tests/test_results.py
.venv/bin/python -m pytest -q tests/test_automation_controller.py
.venv/bin/python -m pytest -q tests/test_case_briefing_automatic.py
.venv/bin/python -m pytest -q tests/test_v11_features.py
.venv/bin/python -m pytest -q tests/test_v12_automatic_visual.py
.venv/bin/python -m pytest -q tests/test_workflows.py
.venv/bin/python -m pytest -q tests/test_workspaces.py
npm --prefix frontend run build
npm --prefix frontend run test:results-browser
npm --prefix frontend run test:workspace-smoke
```

Run backend modules in separate processes because older application fixtures cache
their vault. Browser acceptance needs the authenticated running gateway, real
Postgres/Redis, the prepared processor image and Chromium. Its clearly labelled
synthetic source tests actual extraction, unattended execution, readable outputs,
downloads, tool use and small-screen reading. It provides no historical case proof.
Keep browser screenshots and failed-test logs private.
