# Results workflow validation

Validated on 16 October 2026 in the managed cloud workspace. This change connects
routine ingestion to automatic analysis and makes saved outputs readable in the
frontend. It does not establish completion of every historical platform requirement.

## Verified behavior

| Check | Observed result |
| --- | --- |
| Affected Python regression coverage | **95 cases passed across eight modules**, no current failures, skips or setup errors |
| New source-results regression module | **13 passed**, including real tool execution, legacy forensic bindings, tamper withholding, recovery past 500 records, retry/history and concurrent dispatch deduplication |
| Production frontend | TypeScript and Vite build passed; existing bundle-size warning remains |
| Browser navigation | **24 views rendered**; no page exceptions, API error routes, resource failures or unexpected writes |
| Text ingestion | Actual file upload, isolated extraction, immediate durable dispatch and original SHA-256 verification passed |
| Unattended text analysis | Browser closed during processing; **30 checks completed**, no failures in the final fresh-source run |
| Image ingestion and analysis | Actual PNG upload/extraction; source verification, forensic screening, visual preparation and visual search all produced readable, source-bound outputs |
| Reading and export | Source excerpts, exact character spans, extracted information, source/case report downloads and original-byte verification passed |
| Backend capability access | **258 registered tools and 21 workspace links** appeared in the directory; an actual source-bound word-frequency operation completed through its form |
| Persistence in the UI | Source bookmark and tool-run bookmark restored their saved results after reload |
| Small-screen reading | Source notebook fit the tested 390 px viewport; screenshots were inspected |
| Static checks for the new reading/provenance modules | Ruff passed; Bandit reported no findings in these modules |

The regression count describes unique current coverage across the original affected
module run, the source-binding follow-up and focused reruns. Repeated cases are
counted once. Legacy module-global vault fixtures require separate pytest processes.
Navigation recorded two existing board-layout autosaves; neither was an unexpected
write or an analytical operation. Raw traces and authenticated screenshots remain
private under the ignored validation directory.

## Defects and workflow gaps addressed

- The manual board was the home screen and outputs were scattered. **Case results**
  is now the default, with one notebook per acquired source, readable typed outputs,
  negative results, progress, failures, provenance and exports.
- Extraction did not immediately dispatch analytical work. It now queues a durable,
  fingerprinted pass; a shared lock prevents simultaneous extraction and recovery
  scans from creating duplicate workflows.
- A newest-500 scan could permanently exclude older originals. Recovery now checks
  compact persisted fingerprints across the eligible inventory before validating
  and dispatching pending sources.
- Forensic and visual core adapters omitted wrapper source bindings, so source-aware
  readers skipped legitimate completed results. New receipts bind their original
  and extract; visual receipts also bind image-extraction hashes. Visual search retains bindings for
  every compared source, including comparisons omitted from the ranked result list.
- Historical forensic receipts already contain original/extract attestations inside
  their hashed outputs. Readers validate those declarations without rewriting the
  receipt or inventing a historical hash. Legacy visual receipts with incomplete
  provenance remain withheld until a fresh pass supplies their bindings. The updated
  automatic profile runs for eligible existing sources as well as new uploads.
- Failed executions did not retain their resolved inputs. They now remain associated
  with their attempted source, and nullable failed outputs no longer break the reader.
- Valid previous outputs remain readable while a new pass is queued. Explicit retry
  preserves prior receipts and refuses to duplicate an active pass. Intact originals
  with missing/inconsistent extracts have a direct re-extraction action.
- Tool outputs were hard to rediscover after navigation. The directory exposes the
  callable catalogue, typed inputs, paginated execution history and bookmarkable run
  readings. Current source, comparison, graph and saved-output bindings are checked
  before source-dependent history is displayed.
- Repeated headers obscured actual reading content. The results/tools layout is
  compact, and small-screen status labels remain intact.

## What remains unavailable

The live check used explicitly labelled, owned synthetic documents and an abstract
image. It proves the software path; it supplies no historical case evidence or
case-level matching-accuracy estimate. The historical vault omitted from the source
archive remains omitted. Notes, unverified claims and failed acquisitions are shown
as gaps. No historical originals or case conclusions were fabricated.

Optional model-written interpretation, hybrid search and external collection still
need their reviewed models, services, credentials and network access. The earlier
eight environment-dependent integration failures and dependency findings recorded
in [the security validation](security-validation.md) have not been relabelled as
passing or repaired by this UI change. Local extraction, source reading and the
tested analytical tools work without those optional providers.

The gateway, core and ERPS were restarted and checked in the workspace. The private
external site still needs its existing relay/service bindings and an end-to-end
remote check. A Git push does not deploy that site or create a working external
application address. Reusable startup/retest instructions are saved in environment
draft revision 14; publication remains a separate environment action.

See [the workflow and reproduction commands](results-workflow.md) and
[machine-readable validation](results-validation.json).
