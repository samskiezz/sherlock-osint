# SHERLOCK OSINT — PROJECT LOOKING GLASS

The current release runs at **http://127.0.0.1:8010** in the provided Linux workspace. It opens on **Evidence board**, backed by unattended server workers. This is not an Apple Silicon deployment or a claim that the entire master specification is flawless or complete.

## GitHub source delivery

The latest instruction authorises uploading the current source to GitHub. It replaces the earlier instruction to wait for complete implementation. The connected GitHub account is `samskiezz`, but repository creation currently returns HTTP 403, `Resource not accessible by integration`. No GitHub upload has succeeded. An empty private destination repository must exist and be enabled for the connection before the prepared source can be pushed. See `GITHUB_UPLOAD.json` for the recorded delivery state.

The prepared source snapshot includes application code, pinned dependency files, processors, migrations, tests and the implementation-gap register. The private-access Worker is included under `hosting/private-access`. The evidence vault, databases, credentials, generated investigation outputs, downloaded originals, model weights and old local Git history are excluded. Historical validation paths below refer to the original workspace and are not all distributed in this source snapshot. Engineering-reference audit metadata is retained where the application reads it; the referenced downloaded files are omitted. A metadata entry or a source upload is not an evidence archive or a deployed application.

## Current default: bulletin board with the breakdown directly underneath

The app now opens on **Evidence board**. Its real XYFlow canvas remains at the top; the dossier verification and case breakdown are immediately beneath it in the same scrolling view. Board cards use compact text previews instead of repeatedly downloading all extracted documents. Clicking a supporting passage loads the full original into the inspector.

The supplied expanded dossier is preserved as secondary evidence, SHA-256 `7daaf1409817c0dcb9ffbda7c9c8d031c835c96d7cb0cd8040d2028272698d77`, with **141 paragraph/bullet claim units**. The first source-coverage assessment records **3 supported, 10 partly supported and 128 not verified**. A partial result is not endorsement of the entire compound paragraph. Negative coverage assessments identify missing originals, blocked transcripts and unexamined audio/video. A bounded worker refreshes candidate passages when the source collection changes; a candidate match does not approve a claim.

The source queue tracked 18 jobs: 15 completed acquisitions (including reused originals) and three CourtListener HTTP 403 failures. Newly preserved primary records include the DOJ-hosted criminal complaint (`EV-515b67cc6c69`, 161,802 bytes), affidavit (`EV-c6d4cfb2872e`, 141,659 bytes), and official CORDIS Time Machine grant record (`EV-fe5e7358c427`, 483,281 bytes). These have been attached to the main evidence board and specific court/EU boards. Charges are allegations, not convictions. The original court hearing transcripts, court audio and incident video have not been claimed as acquired.

A new source-page campaign runs every 15 minutes, alongside existing watches. Dossier/source-matching workers continue while the workspace runs; the app does not autonomously finish missing software integrations after this assistant turn. The full thread audit is available in-app and in `IMPLEMENTATION_GAPS.json`: 56 requirement groups and 65 integrations not verified as integrated. No universal completion, flawless operation or exhaustive web coverage is claimed. The current GitHub upload is authorised but blocked by repository-creation permissions.

The full backend regression run passed **507 tests** with 186 warnings (`artifacts/platform-regression-under-board.log`); the final browser flow has no page exceptions and opens the actual source inspector. The 24 focused tests overlap the full run.

Validation and actual screenshots: `artifacts/under-board-tests.log`, `artifacts/under-board-browser.json`, `artifacts/board-with-breakdown.png`, `artifacts/dossier-source-proof.png`, `artifacts/dossier-partial-support.png`, `artifacts/dossier-bandit.json`.

## Case breakdown

The default Investigation screen now presents nine case threads: Caltech/JPL, games, Mondaloy patents, the X post, the proposed scientist team, images, ciphers/gematria, propulsion/quantum claims, and legal/identity claims. Each thread has directly clickable **Connections**, **Proof**, and **Analysis** sections. Connections show the exact assertion, originating board, explanation, source passage, limits and counterevidence. Originals open in the evidence inspector. Full saved reports open inside the case section, with sources, methods, measured image panels, decoding recipes and chronology where actually present. Chapter links such as `#case/mondaloy` survive reloads.

Unsupported claims remain visible as unsupported. Imported dossier notes are labelled secondary material and displayed alongside the gaps. Search/catalogue responses are collapsed separately and excluded from proof-file counts; identical originals are deduplicated by SHA-256. Topic membership is navigation based on labels and saved boards, not a newly inferred factual relationship. Saved analyses recheck source integrity on opening. Missing originals are explicit rather than replaced by generated content.

Validation: `artifacts/breakdown-tests.log`, `artifacts/case-breakdown-browser.json`, `artifacts/breakdown-build.log` and `artifacts/case-breakdown-bandit.json`. Actual running screenshots: `artifacts/case-breakdown-home.png`, `artifacts/case-breakdown-proof.png`, `artifacts/case-breakdown-analysis.png`.

## Automatic workspaces and the earlier statement feed

Open the private app at **https://sherlock-looking-glass-access.sam-kazangas-5963.chatgpt.site**, signing in with the owner's ChatGPT account. The relay connects to this running workspace; it is not a permanent deployment independent of this machine.

The earlier statement feed showed source-checked documented statements, measured results, unresolved claims and recent acquisitions. Unread state survives browser reloads; it does not imply a newly discovered historical fact. AI proposals remain separate from documented statements. Exact passages open the source inspector directly. Reading never launches analysis.

Twelve specialist tabs now default to automatically produced results and scheduled collection, rather than manual input forms: forensic analysis, automation, evidence retrieval, patents, photos, tradecraft, sources, onion research, continuous watch, ciphers/gematria, archives and the investigator. Optional specialist controls are collapsed and mounted only on request. Existing server workers continue collecting and selecting compatible checks while the UI is closed. Sources underlying documented case statements rank ahead of unrelated tool/reference material. Full saved decoder recipes and gematria tables can be inspected without rerunning them. Native board, timeline, map and graph views remain available for browsing.

This change does not make every catalogue method automatically applicable: some require keys, a defensible baseline, independent labels, comparison criteria or human judgments. Missing X credentials and unavailable Tor transport are shown explicitly. No onion acquisition or live X coverage is claimed. Source integrity checks withhold stale outputs; model proposals cannot become verified facts through this view.

Validation: `artifacts/briefing-tests.log` (27 affected tests), `artifacts/briefing-focused-tests.log` (10 focused tests; nine overlap the 27), `artifacts/briefing-build.log`, `artifacts/briefing-bandit.json`, and `artifacts/briefing-automatic-browser.json`. Screenshots show the running application in `artifacts/case-briefing.png` and `artifacts/automatic-cipher-workspace.png`. The older v0.13 gallery description below records the previous interface, now moved into a collapsed evidence browser.

## Earlier collection-wide media review in v0.13

The waterfall is one retained example, not the home screen or required input. The default view now shows a paginated image portfolio across source domains, with pending, running, failed and completed reviews. Sources are interleaved so one batch from one publisher cannot dominate the home screen. Every successfully reviewed image gets a durable `media_reports` receipt, including no-match results. Named people, artwork titles and publisher captions are not prerequisites for geometric composition findings. Names, when reported, still come from explicit source descriptions rather than biometric recognition.

The unattended visual worker discovers all acquired image rows instead of silently stopping at the newest 500. Each comparison remains bounded to the newest 500 acquired reference images; reports disclose truncated coverage, unavailable references and the number of ranked results retained. Reviews use existing isolated extraction, original/derivative integrity checks, OCR, perceptual hashes, multiscale signatures, ORB/RANSAC, channel/LSB/recompression diagnostics and the bounded four-panel mixture test. These tests do **not** constitute a universal hidden-image decoder, authenticated manipulation detector or prediction system. Residual anomalies and visual resemblance remain leads.

Recurring acquisition is separate from comparison. Public RSS/Atom feeds can now discover explicit image attachments and preserve the source post URL. Explicit seed-page watches can include uncaptioned linked images within their existing download budgets. New acquired media from research or authorised X imports/API responses records its source page/post/feed in `media_origins`. Reports and origins are included in case exports. X recent-search media monitoring is configured, but no authorised token is available here; zero live X collection is claimed. No all-Twitter or internet-wide coverage is claimed.

A broader six-hour campaign searches for hybrid-image/optical-illusion references using NASA's documented Image and Video Library API plus public search/Commons connectors. NASA catalogue responses and publisher image renditions are acquired through the existing preserving queue. An initial six-image acquisition demonstrated the pipeline but returned hybrid-aircraft photographs, not hybrid-image illusions; these remain reference/counterexample material, not case findings. A literal phrase filter now rejects those token-only search matches. A rendition is not a camera original. Bing and Commons collection attempts were refused by site collection rules in this environment; failures remain visible rather than being bypassed or counted as evidence. `scripts/configure_media_watch_v13.py` configures these watches idempotently through the authenticated local API.

The main portfolio is read-only: no per-image analysis button is required to process arrivals. A pause stops new analytical dispatch; current work and independent source schedules can continue. Services must remain running. Advanced technical checks and the older composition explanation are collapsed. See `artifacts/continuous-media-v13.png` and `artifacts/continuous-media-browser-v13.json` for the actual running interface and browser acceptance record.


### v0.13 verification

The full regression run passed **482 tests**, with 80 warnings (`artifacts/platform-tests-final-v13.txt`). After the final source-balancing and phrase-filter changes, the **32 affected regression tests** pass (`artifacts/final-media-regressions-v13.txt`). This is not a second claim of 32 additional unique tests. The earlier full-run failure is documented, with its correction, in `artifacts/media-regression-history-v13.json`.

The running vault contains **22 acquired images across six source domains**, with **22 saved automatic media reports**; all 22 original-file SHA-256 values were independently verified by `scripts/verify_media_v13.py`. Six initial off-topic aircraft results are explicitly marked reference/counterexample material. The filtered follow-up acquired six phrase-matched illusion references; these are research inputs, not authenticated hidden messages. The latest source-watch run can remain partial when independent search providers refuse acquisition.

The production frontend builds. Authenticated browser acceptance verifies source-balanced pagination, collapsed composition findings, no manual analysis requests and no browser exceptions. `artifacts/continuous-media-state-v13.json` records the actual file IDs, hashes, sizes, review statuses and source origins; `artifacts/running-system-v13.json` records running services. Bandit on changed backend/utility files reports three low-severity utility-script findings and no medium/high findings. The wider backend/foundation/processor/scripts scan retains 223 low and two medium findings; no high findings. These scans are not a security certification.

## Previous release: automatic findings and visual explanations in v0.12


The default interface no longer presents cipher inputs, raw JSON, workflow forms, logs or an unrelated inspector. Five primary destinations remain; specialised tools and boards are collapsed. A browser acceptance test signs in and receives the actual finding with **zero manual analysis requests**. Opening the page does not create jobs. Existing source watches, acquired-evidence analysis and local-model review continue when the browser is closed, while the workspace remains running. The pause control stops new automatic analysis; current work and separately scheduled collection can continue.

The home page requests a compact evidence catalogue instead of downloading all extracted documents on every refresh. The live comparison measured approximately **71 KB** of summaries versus **12.7 MB** for the full evidence response. Original text is fetched on inspection; legacy workspaces retain their existing APIs.

### The waterfall result is now explained with images

An unattended two-worker visual service operates separately from the text-analysis backlog. It checks acquired images, upgrades old signatures through the isolated processor, compares actual originals and publishes durable explanations. It retries failures up to three times; viewing does not initiate it.

For the acquired four-panel composite, the processor tests all six possible endpoint pairs against a least-squares alpha-blending model. It saves separate panel crops, reconstructions and residual images, preserving the acquired original unchanged. The observed intermediate panels fit approximately **48.0%** and **76.8%** artwork weights, with RGB RMSE **9.6/255** and **10.5/255**. These are fitted weights between endpoints, not probabilities of authenticity. Engineering thresholds and all pair trials are retained; no calibrated case-level false-positive rate is asserted. Owned unseen blend fixtures, unrelated images and identical-panel controls test the implementation.

The photograph endpoint also matches an actual acquired AP photograph with **129 geometric inliers**. Its exact acquired publisher caption names **Donald Trump**, places the photograph in Butler on 13 July 2024, and credits **Evan Vucci**. The app connects the geometric match to that caption and preserves both evidence IDs, hashes and exact source offsets. This is reference-image correspondence and publisher attribution, not biometric identification or recognition of Trump from the standalone artwork. `artifacts/publisher-photo-match-v12.json` records the actual file and hash verification.

The v0.12 result feed showed the photograph, intermediate panels and artwork in order, followed by the measured reasoning. In v0.13 this is retained under collapsed composition findings. Optional evidence details show the matched publisher image, exact quotations, fitted reconstructions and amplified residuals. It does not claim to have decoded a hidden Trump image from the standalone waterfall or authenticated a pre-event prediction. The artwork's original publication date and historical account-header attribution still need independent archival evidence.

A bounded recurring publisher-photo campaign acquires permitted AP reference images and captions through the existing queue. Original files remain immutable; downloaded files are parsed in network-disabled containers. Missing or restricted sources remain failures. X API credentials and Tor access are not bypassed.

### Reliability and verification

The first full v0.12 test attempt exposed storage exhaustion under Docker VFS and interrupted the service. That failed attempt and the separate creation-timeout run are retained locally and are not counted as passing. `artifacts/resource-incident-v12.json` records their hashes, causes and fixes. Raw failure traces are excluded from the source package to avoid exposing runtime diagnostic context.

The parser runtime is now compacted into one filesystem layer without changing its installed programs. Shared kernel locks enforce **at most two parsers across independent API, worker and test processes**, with conservative disk headroom admission. A failed container-creation attempt still reaches cleanup. The supervisor retains owned process tracking when PID/status/audit writes fail. Tests cover actual cross-process admission, low-space refusal, creation-timeout cleanup and interrupted PID/status writes. Work can wait for capacity rather than assuming unlimited parallelism.

Final test results: **475 passed, zero failed, 72 warnings**, process exit **0**, in the final full run (`artifacts/platform-tests-final-v12.txt` and `artifacts/platform-test-status-v12.json`). The focused v0.12 suite passes **10 tests**, including actual Docker image processing and autonomous startup without a browser POST. Frontend production build passes. `artifacts/automatic-case-browser-v12.json` records the default view, four loaded image panels, compact catalogue usage, zero manual analysis requests and browser errors. `artifacts/automatic-case-v12.png` and `artifacts/visual-proof-v12.png` are actual running UI captures. This verification is not a certification of flawless or production-safe operation.

The existing CyberChef dependency advisory and live X/Tor/Mac limitations described below remain material. No new model or unsupported encryption-breaking capability is claimed in this release.

## Retained v0.11 capabilities

## Automatic and parallel investigation in v0.11

- **258 callable tools**, including the existing 35 ML/model adapters. The total also includes 157 deterministic procedures, 53 classical transforms/numerical puzzle methods and 13 operational adapters. These are not 258 autonomous LLM agents. The earlier 253-feature primary-document review remains available, with six additional acquired engineering references in `artifacts/engineering-reference-review-v11.json`.
- **Automatic compatible-source profiles:** stored original hashes and attested text determine which functions can run. New and existing originals are picked up every 15 seconds, with source-fingerprint deduplication and saved applicability reasons across the catalogue. Text, controlled cipher screening, literal encoded-string detection, gematria and cited corpus analyses fan out automatically. Images receive isolated signature extraction and comparison. Numerical baselines, labels, missing keys and claims are not invented to force every algorithm onto every file. Profiles scan at most the first 16,000 characters for encoded spans; general text analyses use a bounded 4,000-character window and corpus methods use up to eight 1,500-character source windows.
- **Parallel execution:** four analytical actions globally, up to three ready branches in each automatic profile, four independent workflow batches, two isolated media parsers and two established decoder containers. Local model generation is limited to one call at a time. X polling has its own two-worker pool and a single streaming session. Dependencies, pause/cancel, failed attempts and source hashes remain durable. Workflows allow up to 128 steps and 256 KB definitions. Corpus definitions contain source references rather than repeated document text; actual quoted windows are reverified and loaded at execution. Resource bounds remain intentional.
- **Established automatic deciphering:** GCHQ CyberChef 11.5.0 Magic chooses layered recipes without cipher selection. Exact known tests decoded hexadecimal `436f6c6520416c6c656e` to `Cole Allen` and Base64→hexadecimal to `Hello world`. It runs with no network, read-only root, one CPU, 1,536 MiB, bounded PIDs and 45-second timeout; no evidence vault or credentials are mounted. Its internal attempt count is not exposed. Readable candidates do not establish intentional messages. Install using the pinned lockfile and reviewed suffix patch in `integrations/decoders/README.md`. The current Ciphey release was reviewed but not installed: it includes a bounded program interpreter, outside this adapter's fixed-transform scope.
- **Gematria/isopsephy:** eight explicit English ordinal/reverse/reduced, Hebrew and Greek mappings run together. Results retain each original character offset/value, ignored characters, target collisions, exact map, comparison counts and seeded uniform matched-length toy controls. Permuting letters preserves additive sums and is not a valid negative control. Numerical coincidences carry no identity, authenticity or prediction inference.
- **Image examination:** ImageHash pHash/dHash/colorhash, fixed multiscale blur views and OpenCV ORB/RANSAC compare actual acquired originals. Resized images and unrelated negative fixtures are tested. Original bytes stay immutable; derivatives and descriptors are separately hashed. Search covers the acquired image corpus, not all internet images or faces. Low-frequency resemblance and geometric matches remain review-required leads.
- **Official X API v2:** recent search, entitlement-dependent full archive search and filtered-stream adapters; durable pagination/since-ID checkpoints, raw API JSON preservation, reported attribution/date fields, media acquisition and explicit access/rate failures. Imported authorised API JSON and `window.YTD` archive parts are parsed without executing JavaScript; earlier observations remain preserved when a post changes. Import through `POST /api/social/import` with an acquired evidence ID. No X token is configured here: the saved feed truthfully reports **NOT CONFIGURED**, with zero live posts claimed. Configure `X_BEARER_TOKEN` only in the existing user-owned mode-0600 provider file or service environment and restart. Stream reconnection can leave gaps; search backfill and independent archives are necessary for completeness. No all-Twitter coverage is claimed.
- **Alleged prediction audits:** exact acquired quotations, specified outcome terms, declared date order, separate timestamp quotations and counterevidence are saved. A name-only claim returns **NOT ESTABLISHED**. Even a passing chronology check requires human review; a second file does not by itself authenticate an archival timestamp or prove source independence. No future-prediction engine or proven foreknowledge is claimed.

## Actual waterfall evidence

A dedicated **Waterfall claim · originals, overlays and chronology** board contains the publisher-hosted artwork copy (7,808,026 bytes), four-panel composite (102,282 bytes), acquired secondary fact-check and cultural-heritage study page. Their original file hashes were independently recomputed in `artifacts/autonomy-live-v11.json`. The artwork/composite comparison found 22 geometric inliers; this shows shared visual material, not prediction. The acquired secondary fact-check describes progressive transparent overlays. Its reported 2021 upload date is not independently certified here. The original Unsplash page returned an access challenge/401 and remains **NOT ACQUIRED**; it was not bypassed. No original AP photograph or independently dated historical account header is represented as acquired.

A six-hour UTC research campaign watches the artefact's public provenance and searches public indexes/archives, collecting actual files through the existing acquisition queue. Source failures remain visible. No private-account access, credential probing or unknown binary execution is added. Tor/onion acquisition remains blocked by this environment's lack of relay TCP grants; the existing adapter cannot honestly claim live onion research here.

## Verification and operational limits

`artifacts/autonomy-live-v11.json` records real authenticated execution: both automatic decoder vectors, a successful 33-step source profile with overlapping action times, an additional successful 34-step profile including local qwen model review, all eight gematria maps, actual image comparison, the X access blocker and the rejected name-only prediction claim. `artifacts/autonomy-browser-v11.json` records actual authenticated UI execution with zero JavaScript errors and three screenshots. `artifacts/waterfall-board-v11.json` preserves the source-attributed board, including counterevidence.

Final regression: **464 passed, zero failed, 60 warnings** in the final full regression run (`artifacts/platform-tests-final-v11.txt`, process exit 0); the additional owned-rule stream protocol test passed separately. `artifacts/x-stream-protocol-test-v11.txt` separately tests synthetic official-format frames, owned-rule isolation, exact raw-byte preservation and immediate reconnect scheduling; it is not a live X acceptance test. Package and frontend checks are recorded with the release proofs.

Dependency review is candid: the decoder npm audit reports 25 findings (4 low, 19 moderate, 2 high including the aggregate CyberChef finding). The high underlying node-forge signature-verification advisory has no fixed published npm version at review time. This isolated Magic adapter never makes certificate/signature trust decisions. Isolation reduces exposure, not the finding count. Bandit reports 22 low findings and one medium `/tmp` heuristic for the explicit container-only tmpfs mount, with no high findings. Do not treat these scans as proof of production security. The app has not been independently security-certified, load-tested at millions of records, or demonstrated to infer future events. Full case export, research scheduling and evidence custody remain in place; this workspace must remain awake for background collection.

## Earlier releases and retained capabilities

## Automation controller delivered in v0.10

Open **http://127.0.0.1:8010 → Automation control**. Repository: `/workspace/sherlock-osint`. This is the provided Linux workspace, not the user’s Mac. The existing evidence board, original vault, background research campaigns, full-text/vector search, timeline and forensic laboratories remain available.

The new catalogue contains **253 callable tools**: **35 ML/model adapters**, **157 deterministic analytical procedures**, **52 classical cipher/encoding transformations** and **9 operational adapters**. These are not 253 independent LLM agents or 253 scientifically validated investigative techniques. The pure-tool adapters execute the installed numerical libraries or reuse the existing bounded cipher/detector engines. No additional third-party repository, install hook, untrusted binary or model-generated program is executed.

The live source review researched all 253 feature records against **171 distinct official-reference URLs**, acquired **169** reference documents and associated an acquired reference with **251** features. The two unavailable references remain recorded with their HTTP outcomes; an available API reference establishes provenance/availability, not investigative accuracy. Documentation is preserved separately from case evidence in `artifacts/feature-api-documents-v10/`. The per-feature audit is available at `GET /api/automation/feature-research` and in `artifacts/automation-feature-research-v10.json`.

Implemented controller behavior:

- Saved acyclic workflows, explicit dependencies, data-only output references, source bindings and 1–3 attempts per action. Definitions and run snapshots persist in five SQLite tables; they are included in case JSON/ZIP manifests.
- Pause/resume/cancel, failure policies, dependent-step skipping, partial outcomes, per-attempt history, elapsed active time, output hashes and hash-chained audit events. A completed step is not repeated. An interrupted step may replay; analytical operations are pure and acquisition IDs are deterministic for each run/step. This is at-least-once recovery, not a claim of exactly-once distributed execution.
- UTC cron/interval schedules and a **new-evidence trigger**, checked by the durable worker. New-evidence schedules bind each newly acquired original and process at most four unseen records per check. Existing originals are excluded unless explicitly requested. Source creation and retrieval dates retain their distinct meanings.
- Actual original/attested-text verification, exact quotation checks, source metadata, hybrid retrieval, acquisition enqueue/inspection, inventory and service-health adapters. A queued acquisition is explicitly **NOT ACQUIRED** until the existing pipeline preserves an actual file.
- A local `qwen2.5:1.5b` planner can select up to six allowed source-analysis tools. It cannot choose an arbitrary URL, host command, repository or private account. Invalid model plans fail visibly. Planning is a bounded synchronous request; the validated execution plan is durable.
- Local model notes select numbered passages from the verified original. The controller checks the selected offsets and exact quotations independently. **Quotation correctness does not prove that a generated claim follows from the quotation.** Every model interpretation remains **HYPOTHESIS / HUMAN REVIEW REQUIRED**; no factual graph edge or identity merge is created automatically.
- An operator UI with searchable tools, true computational classifications, editable JSON inputs, source selection, workflow builder, recurring controls, actual progress, source links and downloadable execution receipts.

Boundaries: analytical subprocesses accept fixed registered tool IDs and JSON only. On Linux they receive a 20-second CPU limit, a 2 GiB address-space limit, one native numerical thread and a 40-second wall timeout. Workflows allow at most 32 steps, 200 active jobs, 100 schedules and a declared active-time budget of 10–1,800 seconds, checked between actions. Local model requests have a 90-second timeout. Pause/cancel applies at the next action boundary. Numerical inputs, documents, graph sizes and output sizes are bounded. These limits are not a general-purpose OS sandbox: downloaded evidence parsing continues in the existing network-disabled, read-only Docker processor. Model-generated programs are never executed.

Verification and proof files:

- `artifacts/platform-tests-final-v10.txt` and `artifacts/platform-test-status-v10.json`: **452 passed, zero failed, 42 warnings**, actual process exit code **0**. The complete final run took 132.31 seconds.
- `artifacts/automation-focused-tests-v10.txt`: 289 focused checks, including every pure callable, known mathematical vectors, spectral tones, graph topology, source offsets, invalid-input rejection, holdout leakage detection and controller transitions. This overlaps the full suite; do not add the counts together.
- `artifacts/automation-live-proof-v10.json`: actual patent source workflows, local-model selection/results, source hashes, new-evidence processing, actual NIST PDF acquisition and restart checkpoint proof. The original model adapter returned zero cited findings; the replacement numbered-passage adapter was tested separately and the initial outcome is retained.
- `artifacts/automation-browser-v10.json`, `artifacts/automation-control-v10.png`, `artifacts/automation-workflow-v10.png`: actual authenticated UI execution and saved-workflow completion, with zero browser JavaScript errors.
- `artifacts/bandit-v10.json`: 13 low findings, one medium finding, zero high findings. The medium finding is the existing explicit `/tmp` Docker tmpfs target; this is not a clean scan or a security certification. `artifacts/npm-audit-v10.json` reports zero known production frontend dependency vulnerabilities. `artifacts/pip-check-v10.txt` records dependency consistency.

The additional acquired methodological original is **NIST AI 100-1, Artificial Intelligence Risk Management Framework**, from `https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf`: **1,946,127 actual PDF bytes**, preserved as `EV-412e247bf87f`. Its hash and acquisition job are recorded in the live proof. This is a methodological reference, not evidence establishing any allegation in the imported dossier.

Run the full platform with `.venv/bin/python scripts/run_platform.py --services` after the existing setup/build steps below. Core, bridge and workflow worker are supervised locally; PostgreSQL, Redis, API, Celery, Qdrant and Elasticsearch have Docker restart policies. Ollama remains the separately managed local-model container. Schedules run while the host and services are awake; this workspace cannot keep researching after the environment is suspended.

**Remaining master-directive gaps:** Apple Silicon installation has not been tested here. Live Tor remains blocked by the environment’s TCP policy. Whisper, GLiNER, Neo4j, external OIDC/SAML and the full third-party collector catalogue remain unimplemented/unconfigured. No complete portrait corpus, unknown APK/game binary, hidden file archive or verified common fourteen-person research team is claimed. Statistical/model case-level accuracy and production-scale graph performance have not been established. The platform is working software with measured acceptance results; it is not “flawless” or completion of every item in the master directive.

The next executable integration task is an isolated, pinned transcription adapter with a real permitted audio fixture and timestamped transcript/source acceptance, followed by document entity extraction and independent scientific review. Authentication, source integrity and explicit uncertainty must remain intact.

## Wider platform delivered in v0.9

**Current entry point: http://127.0.0.1:8010.** The existing evidence wall remains the main interface. Open **Evidence retrieval** for the new search and cross-reference workspace.

- **Real search services:** Elasticsearch BM25 and Qdrant cosine vectors, with an independently downloaded and SHA-256-verified local `all-minilm:22m` model. No external model API is needed. PostgreSQL, Redis, authenticated API and Celery worker also run as Compose containers.
- **Continuous indexing:** acquired originals with attested text derivatives are checked every 60 seconds. Source and text hashes, exact Unicode offsets, PDF pages, model manifest and embedding recipe are retained. A 700-character passage is represented by normalised mean embeddings of every 180-character window, respecting the model's context limit. Failed/interrupted writes retry. Per-document indexing is capped at 2,000 passages; truncation is visible. Priority source requests persist in SQLite. Secondary notes are excluded.
- **Cited retrieval:** keyword, semantic and hybrid modes. Hybrid uses reciprocal rank fusion (k=60). Every returned passage is rechecked against the actual original and derivative. Results are an extractive evidence set, not an LLM assertion. Query inputs, results, exact citations and model identity are saved and exportable as JSON. Similarity scores are not confidence or proof of a relationship.
- **Identifier cross-reference:** literal patent numbers, DOIs, public handles, ISO dates and SHA-256 values with exact source spans. Shared occurrences do not automatically produce factual graph edges or identify an account owner. Source independence remains unestablished.
- **Six additional working statistical methods:** Isolation Forest, Local Outlier Factor novelty detection, One-Class SVM, PCA reconstruction screening, Mahalanobis distance and the single-outlier Grubbs test. These use reviewed/pinned scikit-learn 1.9.1, SciPy 1.18.1 and NumPy 2.5.4. Independent baseline rows, named features/units and finite bounded matrices are required. Standardisation fits the baseline only; singular covariance and invalid inputs are rejected. Results retain parameters and library versions and remain provisional. Tests cover planted outliers, benign controls, reproducibility and hand-calculated distance, not case-level accuracy.
- **Actual case ZIP files:** licence review is available in the evidence inspector's provenance tab. Positively reviewed originals and hash-verified derivatives are written to an on-disk archive; unreviewed, missing, damaged or over-budget files receive explicit omission records. The archive includes case records, citation indexes and saved queries. It has a 1 GiB input budget. No public-domain status is inferred automatically.
- **Supervision:** `scripts/run_platform.py` supervises the owned core and token-protected bridge, rejects stale PID files and restarts failed processes. Docker restart policies cover the other services. `scripts/install_macos_service.py --full-platform` generates/installs a matching user LaunchAgent **on the target Mac**; that Mac installation remains untested here.

Storage was recovered without deleting evidence or model weights. The Linux model image omits unused GPU libraries, and the installed Elasticsearch runtime was flattened, excluding regenerated keystore/certificates and logs while preserving the remaining runtime files and persistent data volume. Their source and derived image identities are recorded in `artifacts/*-v9.json`; the private Compose environment selects the local flattened image. A fresh installation uses the pinned official multi-platform Elasticsearch distribution. Elasticsearch has a 384 MiB heap, one JVM processor, disabled unused ML modules and a 1.5 GiB memory limit. These are local-case settings, not a benchmark for millions of records.

After the existing core setup (`./setup.sh`), prepare the foundation/search configuration and dependencies:

```bash
.venv/bin/python -m pip install -r foundation/requirements.lock
.venv/bin/python scripts/setup_foundation.py
.venv/bin/python scripts/setup_retrieval.py
# Requires the reviewed Ollama runtime already installed/running; see local-model section below.
.venv/bin/python scripts/fetch_embedding_model.py
docker compose --env-file data/foundation-compose.env -f compose.foundation.yml --profile gateway build api
.venv/bin/python scripts/run_platform.py --services
# In another terminal after core startup:
.venv/bin/python scripts/bootstrap_foundation.py
```

The supervisor stays in the foreground unless managed by launchd or another service manager. Docker and the host must remain running; sleep/shutdown cannot perform research. The supplied environment is Linux, not remote access to the user's Mac.

Verification records: `artifacts/backend-test-results-v9.txt`, `artifacts/learned-anomaly-tests-v9.txt`, `artifacts/archive-report-tests-v9.txt`, `artifacts/platform-restart-proof-v9.json` and `artifacts/platform-browser-v9.json`. The latter records are produced by actual running services and browser checks, not fabricated screenshots. Prior release proofs below describe the state at those releases.

Final v0.9 verification: **162 regression tests passed**, followed by **23 focused checks** after the paginated metadata change. All six infrastructure containers and both supervised processes were restarted with records retained. The final inventory verified **89 read-only original files (108,969,842 bytes)**: 65 source artefacts, 3 publisher pages and 21 catalogue responses; these are **not 89 research papers**. All **88 eligible extracted records** were indexed into **7,698 cited passages**. The mirror held 113 metadata records and 11 persistent collection jobs. The browser rendered/highlighted the actual PDF citation and executed a labelled synthetic-control detector through the interface. Python dependency audit reported zero known vulnerabilities. Bandit reported 15 low and one medium finding, zero high; the medium is its `/tmp` heuristic on the explicitly isolated Docker tmpfs declaration in `backend/sandbox.py`, not execution of downloaded files on the host. This is not a security certification. Counts will grow as monitoring continues. See `artifacts/platform-final-inventory-v9.json` for the measured snapshot.

**Still outside the completed scope:** live Tor acquisition is blocked by this environment's lack of outbound TCP grants; no hidden/onion file is claimed acquired. Whisper transcription, GLiNER, Neo4j, external SSO, the full third-party collector catalogue and the remaining specialist methods are not implemented. The PostgreSQL mirror refreshes paginated provenance records without repeatedly loading full PDF text/coordinates into the gateway. PostgreSQL mirrors evidence metadata and owns authentication/collection jobs; the original case workflow tables remain in SQLite. This is a substantially working platform, not completion of every item in the master directive.

## Foundation delivered in v0.8 (expanded by v0.9)

Open **http://127.0.0.1:8010** to sign in and use the existing interactive evidence board through the authenticated gateway. Local administrator credentials are generated into `data/foundation-secrets/admin-login.json` (mode 0600); they are never committed or printed by setup. The original `:8000` interface remains a loopback-only compatibility service, so gateway authentication is **not** a claim that every local process is prevented from accessing the legacy API.

Implemented: SQLAlchemy models for Case, Entity, Evidence, User, AuditLog, collection outbox and schema version; actual PostgreSQL and password-protected, persistent Redis services; Argon2 passwords, short-lived HS256 JWT/cookie sessions, current database role checks through Casbin, encrypted PyOTP enrollment, consumed-code replay rejection and token revocation after MFA activation/logout. Admin provisions accounts; Analyst can collect/analyse; Viewer can read/export and cannot mutate. This is local JWT authentication, not a configured external OAuth/OIDC/SAML provider or case-specific multi-tenant authorisation.

Versioned endpoints: `/health`, `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/totp/enroll`, `/api/v1/auth/totp/confirm`, `/api/v1/users/me`, `/api/v1/users`, `/api/v1/cases`, `/api/v1/collect`, `/api/v1/collect/{job_id}`, `/api/v1/analyze`, `/api/v1/graph`, `/api/v1/report`, `/api/v1/evidence`, `/api/v1/system`, `/api/v1/audit/verify`. Inputs use Pydantic schemas. The gateway streams actual files, filters forwarded credentials, checks write origins, bounds uploads, and rate-limits logins/requests through Redis. PostgreSQL audit events use a serialised predecessor hash and append-only UPDATE/DELETE triggers; an owner can still rewrite history, so external anchors remain necessary.

A background dispatcher publishes committed PostgreSQL outbox jobs to Celery. Row locking prevents competing dispatchers; stale execution leases are recovered after five minutes. The reviewed Sherlock 0.16.2 adapter currently checks **one explicit public GitHub profile**, observes robots restrictions, preserves real page bytes through the established acquisition queue, records the tool CSV and source hash, and marks account ownership **UNVERIFIED ATTRIBUTION**. It does not perform the complete hundreds-of-sites scan or infer a person's identity from a handle. Both a visible initial failure and a corrected successful acquisition were retained. The database workspace displays live PostgreSQL counts. PostgreSQL evidence metadata synchronises with the growing existing vault every 30 seconds; original files remain in their immutable content-addressed store.

Initial schema: `foundation/models.py` and `migrations/0001_foundation.sql`. Dependencies, including transitive versions, are pinned in `foundation/requirements.lock`. The supported native launch sequence is:

```bash
.venv/bin/python -m pip install -r foundation/requirements.lock
.venv/bin/python scripts/setup_foundation.py
docker compose --env-file data/foundation-compose.env -f compose.foundation.yml up -d postgres redis
./start.sh
# In a second terminal:
.venv/bin/python scripts/bootstrap_foundation.py
.venv/bin/python scripts/run_foundation.py
```

`compose.foundation.yml` now runs PostgreSQL, Redis, API, Celery worker, Qdrant and Elasticsearch. All six services were launched in v0.9. The API/worker use the authenticated, byte-preserving host bridge to the existing core. Official upstream image digests and local derived-image identities are recorded. Redis 8 server licensing differs from the MIT Python client; review server redistribution terms independently.

Verification: live PostgreSQL/Redis API tests cover roles, MFA replay/revocation, actual reports/graphs and real Celery acquisition. The full regression suite passed **131 tests** before the added bridge check; the latest targeted Phase 1 results are in `artifacts/foundation-tests-v8.txt`. A real restart preserved users, encrypted MFA seeds, revocation counters, completed/failed jobs and evidence references. Browser acceptance signed in and loaded the actual existing board/media with no JavaScript errors. See `artifacts/foundation-live-proof-v8.json`, `artifacts/foundation-restart-v8.json`, `artifacts/foundation-browser-v8.json` and `artifacts/authenticated-evidence-board-v8.png`. This is not completion of the remaining specialised integrations, unimplemented methods or live Tor, and it has not been installed/tested on Apple Silicon.

## Executable analyses, continuous graph monitoring and reports (v0.7)

Added 17 tested computational execution paths: source-bound social-network analysis, betweenness, closeness, eigenvector centrality, k-core, seeded NetworkX Louvain communities, bounded maximal cliques; Z-scores, CUSUM, EWMA, Benford digit comparisons, Jensen–Shannon divergence, two-sample empirical KS distance, DBSCAN; and original-text-bound Kasiski, Friedman and Caesar chi-squared analysis. A board analysis revalidates the actual supporting files and quotes, excludes hypothesis edges and stores the analysed topology and source hashes. Graphs are bounded to 300 nodes / 3,000 edges; clique enumeration to 100 nodes / 1,000 outputs. These are not million-record graph benchmarks. Statistical inputs require an explicit reference population; KS/Benford outputs do not assert significance or wrongdoing.

Select an original-source board, execute an analysis, then enable its persistent monitor. Monitors support UTC cron or intervals of at least five minutes through the API; the UI defaults to 15 minutes. They retain pause state and next due time across service restarts, save changed inputs, report failures and skip duplicate analyses when the cited topology is unchanged. The seven worker heartbeats include graph-analysis monitoring. An awake host and running service remain necessary.

All 52 cipher methods remain available. Playfair, Hill, Gronsfeld, autokey, Bifid and ADFGX now have their required key/square/period controls. The browser acceptance check executes the Hill known vector `HIAT → HELP` through the real API.

The PDF and DOCX header controls download actual evidence-audit reports containing original-file inventories, stored relationship states, exact citations, failures and provisional analyses. They do not embed original files or produce an invented investigative narrative. Large analytical fields explicitly disclose abbreviation; JSON retains full records. PDF uses disclosed Latin transliteration; DOCX retains Unicode.

Audit events now have a transactionally appended SHA-256 predecessor chain. Ordinary UPDATE/DELETE operations are blocked by SQLite triggers; `/api/audit/verify` checks event hashes and missing records. API accesses are logged without request bodies, query strings or credentials; verification/anchor reads deliberately leave the head unchanged. The database workspace downloads an external hash anchor. Existing events were backfilled and are not retrospectively authenticated; a database owner can bypass triggers and rewrite the chain, so retain an anchor outside the case store.

NetworkX **3.7** is pinned after official PyPI/repository/licence checks and wheel SHA-256 verification. OpenOSINT, PhantomSignal, DoWhy and argon2-cffi package metadata were checked but those integrations are **not installed or implemented**. The original SpiderFoot remains unarchived and the proposed replacement reports itself as a fork; the claim of official supersession was not established. The additional 23-container framework, PostgreSQL/Celery/OIDC/RBAC stack, Dash replacement, biometrics and other modules in the later specification are **not integrated**.

Verification: **125 backend tests passed**, frontend build and browser checks passed, zero browser JavaScript errors, and a real service restart preserved sourced boards, analyses, monitor schedules and original hashes. The vault contains 67 original files (including catalogues), not 67 papers. The technique registry now has 25 computational methods, 11 guided human workflows, three technique families and **69 still-unimplemented requirements**. This remains an incomplete implementation of the full specification. Live Tor is blocked by the environment's TCP policy; no onion original has been acquired.

Bandit found and prompted fixes for untrusted feed XML parsing and dynamically assembled checkpoint SQL. Its final scan has 15 low findings and one medium finding (the explicit `/tmp` tmpfs target inside the isolated Docker worker); no high findings. Remaining subprocess and XML-output warnings require contextual review, not a claim of complete security validation. Proofs are in `artifacts/operational-browser-v7.json`, `artifacts/operational-restart-v7.json`, `artifacts/backend-test-results-v7.txt` and `artifacts/bandit-audit-v7.json`.

## Growing database, targeted collection and source-backed tradecraft (v0.6)

The **Growing database** workspace displays the actual `data/case.db` database, content-addressed `data/originals/` vault and separate `data/derivatives/` directory. It reports physical bytes, catalogue-versus-source roles, missing originals, acquisition growth, free disk and persisted collector heartbeats. It offers a consistent SQLite backup (using SQLite's backup API) and a manifest that checks actual original-file SHA-256 values. Five-minute growth snapshots survive restarts. New preservation stops below a 1 GB free-space reserve rather than filling the host disk. At the v0.6 snapshot the store was SQLite WAL/FTS5. PostgreSQL and Qdrant were subsequently deployed in v0.8/v0.9; Neo4j remains unimplemented.

Three new enabled six-hour campaigns target Mondaloy patents, public photograph leads and publicly indexed onion-document leads. Cron schedules are staggered at minutes 17, 23 and 31 UTC. Google Patents search has produced real publication records and acquired originals. Publisher-source watches refetch configured public pages each run, preserve changed bytes and follow enabled media links. Identical extracted text avoids a duplicate analyst task even if raw page bytes change. Campaign edits take effect on the next run; an active run retains its settings snapshot. Source pages acquired during discovery are bound to actual verified files instead of fetched twice. Expected image/PDF downloads that return another format are marked failed; blocking pages do not count as the requested original.

New providers include Google Patents, public publisher-page watches, Wikimedia Commons, Bing RSS, Brave image search and valid v3 onion addresses mentioned in acquired public records. Current reachability is explicit: Google Patents and the configured ABC publisher page worked; Bing, Commons API and Ahmia attempts were blocked by site robots policy. Brave web/image APIs require a separately configured key. A Commons file-description URL returned 404; People returned 402 and a Caltech announcement returned 403. None was bypassed or silently substituted. Live onion acquisition remains **BLOCKED_NETWORK_POLICY** because this managed environment has no Tor relay TCP grants. No real onion original is claimed.

The **Patent intelligence** workspace presents isolated-parser metadata, original PDF links, inventor/assignee labels, priority/filing/publication dates, exact claim text, backward references and linked patent/family leads. Legal-status labels remain catalogue assertions; patent claims do not prove experimental demonstration, commercialisation or freedom to operate. The **Public photo corpus** shows publisher-linked image leads separately from preserved images, retaining attribution uncertainty. It performs no facial identification and cannot claim every photograph on the web has been found.

The **Tradecraft & hypotheses** workspace holds 106 structured method records: 12 CIA technique records, three CIA technique families, seven additional computational-method records and 84 unimplemented, unverified taxonomy research targets. The twelve CIA procedures consist of one executable ACH matrix and eleven guided human workflows. Computational tools include Bayesian updating with supplied likelihoods, MAD/modified Z, IQR, Brier calibration, expected information gain, source-dependence shingle comparisons and lawful metadata interval/link analysis. Exact source passages and original/text hashes bind citations. ACH dependency groups count once; scores are inconsistency judgments, not probabilities. Guided workflows retain assumptions, dissent and collection gaps. Saved analyses can be pinned to boards only as **HYPOTHESIS**, with source links and idempotent pinning. This is not a verified 500-method library or a reproduction of classified agency systems.

The cipher workbench now offers 52 classical/encoding/puzzle methods, adding Caesar/affine chi-squared ranking, Kasiski, Friedman, Vigenère period analysis, Playfair, Hill 2×2, Bifid, Gronsfeld, plaintext-autokey and ADFGX. Automatic screening runs 51 rules, counting up to 338 additional Caesar/affine parameter trials where input length permits. Nineteen seeded shuffled controls apply to transformation rules; additional cryptanalysis reports explicitly say that their controls/holdouts have not been run. Summary polling avoids sending full result payloads repeatedly; full attempts and failures remain available on demand.

**Modern encryption** provides six supplied-key algorithms through pinned PyCA cryptography 50.0.2: AES-GCM, AES-CCM, AES-GCM-SIV, AES-SIV, ChaCha20-Poly1305 and Fernet. Encryption uses fresh nonces where applicable. Keys are request-only, never stored in case records or logs; plaintext results are returned but excluded from history. Audit records retain algorithm/library versions, byte hashes, sizes and non-secret parameters. Reproduction requires externally retained original input and authorised key. Python does not guarantee memory zeroisation. Validating an authentication tag does not authenticate a source's claims; no modern encryption cracking is implemented.

Real new case evidence includes Caltech's 40-page Summer 2016 magazine PDF (9,553,749 bytes, SHA-256 `9a988edf2ad9187ad0766636f46b59b4a41d32121ff02524be0022b70e6fe5ea`) naming Cole Allen in the robotics caption on PDF page 11 (printed page 9). A dedicated board preserves that source-specific name transcription without merging it with a later case identity. The ABC-published 2017 interview image is also stored (501,379 bytes, SHA-256 `d82cfb0bc3b78f86e53c417344ba0d96683db63186c65d87418180253ec95bd5`), with subject attribution requiring review. Actual primary PDFs acquired include the CIA primer, Heuer's book, Berkeley Protocol, NIST SP 800-86, ICD 203/206 and NSA traffic-analysis history. Mondaloy composition/follow-on records and original patent PDFs are stored; graph-intelligence patents supplied in the request were acquired as technical disclosures.

Verification artifacts: `artifacts/collection-proof-v6.json`, `artifacts/backend-test-results-v6.txt`, `artifacts/collection-regression-tests-v6.txt`, `artifacts/collection-browser-v6.json`, `artifacts/python-audit-v6.json` and the six collection/tradecraft/crypto screenshots. The proof recorded 67 physical originals (including catalogue snapshots), 105,556,715 preserved bytes, eleven indexed patent records and three actual images. Counts grow as scheduled jobs run; they are not an exhaustive corpus claim. `artifacts/looking-glass-database-snapshot-v6.sqlite` is an actual consistent database snapshot, generated locally and excluded from version control.

### Keeping it running on a Mac

This Linux-managed workspace can stop its processes when suspended or restarted; it is not an always-on deployment on the user's Mac. After copying the project and evidence, running `./setup.sh`, and starting Docker Desktop, run `.venv/bin/python scripts/install_macos_service.py` on the Mac. The reviewed user launchd agent restarts the app after login/crash while the Mac is awake. `--generate-only PATH` previews its plist; `--uninstall` removes the service while retaining evidence. `artifacts/sherlock-launchd-v6.plist` was generated here; native installation was not executed or tested.

Optional provider keys can be supplied through inherited environment variables or a user-owned mode-0600 JSON file at `~/.config/sherlock-osint/service-env.json`. Only `BRAVE_SEARCH_API_KEY` and `ANTHROPIC_API_KEY` are accepted; existing environment bindings take precedence. This private file stays outside the repository and case exports. Native Tor/Tor Browser requires a permitted network and the existing loopback SOCKS5h configuration. Docker and source/API access must remain available for processing and collection.

## Cipher, word-puzzle and digital-forensic automation (v0.5)

Open **Cipher laboratory** for three connected workspaces: ciphers and word puzzles, image diagnostics, and automatic screening.

- 41 deterministic methods: hex/Base32/Base64/Base85/Ascii85, binary/octal/decimal, Caesar/ROT47/Atbash, Vigenère/Beaufort/affine, rail fence/keyed columnar, Morse/A1Z26/Polybius/Bacon/XOR, Unicode and URL/HTML transforms, acrostics/telestichs/line extraction/word lengths, timestamps, frequency statistics and Scrabble/anagram rack searches. Keys, shifts, offsets, input, outputs, controls and holdout expectations are persisted. Invalid transformations are also saved. Attached evidence inputs must match a passage in an integrity-verified, sandbox-attested extract; manual transcriptions are marked manual.
- Scrabble accepts blank tiles and optional exact-rack matching, with reproducible tile scores. Its original curated demonstration lexicon is intentionally small; supply a whitespace-separated dictionary for wider word coverage. Board multipliers, an official tournament dictionary and every historical cipher are not implemented.
- A durable worker checks acquired originals every 30 seconds, automatically upgrades existing images lacking diagnostics and screens bounded text extracts. It tries 46 rules, recording all outputs and failures plus 19 seeded shuffled controls per valid transformation. Original/text/configuration fingerprints prevent duplicate completed runs across restarts. Pause/resume settings, run history and exports persist in SQLite. Pausing screening stops new runs; an in-flight bounded run completes. Acquisition-time image extraction remains enabled.
- Statistical output includes entropy, coincidence index, character/bigram frequencies and Unicode formatting-control positions. English lexicon readability is exploratory. Failed controls are visible, and multiplicity-adjusted empirical scores cannot establish significance with only 19 controls across 46 attempts. A holdout match remains **UNVALIDATED**; independence is user-declared. Reusing the discovery input is flagged **NOT INDEPENDENT**.
- Network-disabled image processing creates red/green/blue channels, a sampled red least-significant-bit view and a JPEG recompression residual view as separately hashed derivatives. It records channel statistics, sampled bit balance, EXIF presence, bytes after the last JPEG end marker, local residual outliers and three benign recompression controls. Original files remain read-only and are hashed before and after processing. Diagnostic routes reject unknown names and changed derivative hashes.
- Image comparison reports exact-byte equality, dimensions and average-hash Hamming distance. These checks do **not** authenticate images, establish a common origin, attribute AI generation or prove steganography. Residual coordinates refer to the resized diagnostic display; compression, texture, flat graphics and rescaling can explain indicators.

Live verification used the actual acquired Caltech team photograph and Steam game artwork, not generated substitute images. See `artifacts/digital-forensics-live-v5.json`, `artifacts/backend-test-results-v5.txt`, `artifacts/forensics-browser-v5.json` and the three `*-v5.png` screenshots. The service restart check preserved case layouts, paused investigative tasks and original-file hashes. A temporary disk-full failure was resolved by pruning unused Docker build cache and dangling build images; originals were retained and the case database integrity check passed.

## Recurring online researcher and onion document research (v0.4)

Open **Online researcher**. Create a campaign with a case question, up to four queries, up to five providers, public feed/disclosure/onion seed URLs, an optional discovery-domain filter, a source-download budget and a UTC cron expression. The default `0 */6 * * *` runs every six hours. The backend must remain running; missed schedules create one run, not a backlog storm. Pause/resume/cancel and run-now work, including dependent acquisition and analyst jobs.

The durable workflow searches → queues actual originals → follows one hop of document links extracted in the network-disabled parser → verifies originals and text derivatives → runs the evidence investigator → attaches actual cards to a dedicated board. Optional model findings are attached only as citation-checked `HYPOTHESIS` records requiring review. Completed unchanged URLs reuse acquired originals and do not generate duplicate investigative plans. Failed acquisitions can be retried by a later scheduled run. Search responses and feed inventories are preserved separately and are not counted as papers. Discovery response bytes are capped at 5 MB; original files at 25 MB. Each acquisition/audit phase has a 15-minute wait budget. Existing manual board positions are retained.

Providers:

| Provider | What it searches | Current setup |
| --- | --- | --- |
| Internet Archive | Public text collections, then public PDF inventory links; restricted items excluded | Public connector; reachability checked per run |
| NASA NTRS | Explicitly public technical-report PDF links | Live search and download demonstrated |
| arXiv | Research records and original PDF links, ordered by recent updates | Public connector; reachability checked per run |
| Crossref | Recent publication records and PDF links where provided | Public connector |
| GDELT | Recent indexed news stories | Implemented; live attempts here failed with 503 / DNS errors, retained visibly |
| GitHub | Public repository records, with attribution kept unverified | Implemented; initial endpoint probe here returned 502 |
| Brave | General web search, including user-defined disclosure/document queries | Set `BRAVE_SEARCH_API_KEY` outside source control; no key configured here |
| Public feeds / disclosure pages | RSS/Atom records and matching original-document links | Investigator-supplied public seeds |
| Ahmia | Public web index of onion sites (clearnet discovery) | Implemented; no live successful index search claimed |
| Public onion seeds | Public v3 onion pages and same-host document links | Tor route required |

A live six-hour campaign acquired two actual NASA PDFs: **Architecture, Voltage, and Components for a Turboelectric Distributed Propulsion Electric Grid** (12,650,337 bytes, 270 pages) and **Design and Development of a 200-kw Turbo-Electric Distributed Propulsion Testbed** (2,720,258 bytes, 20 pages). Both were sandbox-processed, rehashed and published to the research board. GDELT failed, so the run is explicitly `PARTIAL`. These papers are scientific context, not evidence of a common team or a connection to Cole Allen. The first run added two vault files; later runs reuse them without another investigative plan.

Open **Onion document browser** to configure a local Tor SOCKS endpoint, queue a public v3 onion URL, inspect failures and read preserved source documents. The connector validates v3 address checksums, uses SOCKS5h remote DNS, rejects credentials/nonstandard destination ports and rejects all clearnet/private redirects. It never falls back to the normal HTTP proxy. HTML parsing and document-link extraction stay in the existing read-only, network-disabled processor. Downloaded webpage JavaScript is not executed. This is a Tor document acquisition/reader interface; it is **not** the fully hardened Tor Browser and does not claim its complete fingerprinting protections. A SOCKS handshake establishes proxy readiness, not the reachability/authenticity of an onion site.

**Live onion research is blocked in this cloud workspace:** `/etc/codex/network-policy.json` contains no TCP grants for relay connections. The adapter and startup helper refuse to send an onion request in this state. No public onion document has been acquired and no Tor network bootstrap is claimed. Protocol integration tests use a loopback SOCKS fixture and explicitly distinguish it from the live network.

On the target Mac, use either an already running Tor Browser (usually `socks5h://127.0.0.1:9150`) or a native Tor client (usually port 9050). For an already installed native Tor client, run manually from the repository root:

```bash
.venv/bin/python -m scripts.start_tor
```

If Tor is absent, install Tor Browser from the Tor Project, or use the official Homebrew `tor` formula. The helper starts only that known client binary, binds SOCKS to loopback, uses a separate private profile, and is never called by autonomous agents. Mac installation/network operation remain untested here. Configuration and source/task history survive restarts; credentials remain outside the case database.

Verification:

- `artifacts/backend-test-results-v4.txt`: **56 passing integration tests**. New coverage includes source failure isolation, cached-source reuse, pause/cancel races, dependent jobs, sandboxed document links, private-seed rejection, onion checksum checks, blocked-runtime behavior, actual SOCKS domain-name forwarding and clearnet-redirect rejection.
- `artifacts/live-online-research-v4.json`: actual downloaded PDF paths, byte counts, page counts, hashes, sandbox attestations and complete research task history.
- `artifacts/research-restart-v4.json`: an actual paused research task survived a service restart, retained task IDs, resumed and reused existing originals without another audit.
- `artifacts/research-browser-v4.json`: real source cards/PDF canvas, campaign controls, provider results and persisted Tor configuration; zero browser runtime errors. It explicitly records **zero onion originals acquired**.
- Screenshots: `artifacts/online-researcher-v4.png`, `artifacts/online-research-board-v4.png`, `artifacts/onion-document-reader-v4.png`.

## Run

The current workspace service is at **http://127.0.0.1:8000**. This is the workspace's loopback address; use workspace port forwarding to access it from another machine.

```bash
./setup.sh       # Python 3.12 and Node/npm required; creates isolated dependencies and builds UI
./start.sh       # compiled frontend + FastAPI API on loopback port 8000
```

On a Mac, copy this repository **and `data/`** to the target machine, install Python 3.12, Node and Docker Desktop, then run the commands above. FFmpeg and Tesseract are installed inside the processing image. Docker must be running; setup.sh builds that image, and the API refuses to parse evidence on the host when isolation is unavailable. The Linux virtual environment, node_modules and downloaded Linux browsers must not be copied as Mac installations. Recreate them with setup.sh. Versions are pinned in `requirements.lock` and `frontend/package-lock.json`; npm integrity hashes are in its lockfile.

For continuous operation after Mac login:

```bash
.venv/bin/python scripts/install_macos_service.py
```

The installer writes a user LaunchAgent with `RunAtLoad`, `KeepAlive` and a 15-second restart throttle. It does not run on Linux and has not been executed here. Stop/uninstall on the Mac with `launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/local.sherlock-osint.plist"`, then remove that plist. Watches run while the backend is running and the computer is awake. Sleep/shutdown cannot run jobs; missed intervals run once after recovery, rather than creating a backlog storm.

## Working features

- XYFlow infinite board: pan, zoom, dragging, multi-selection, minimap, manual connections, deletion, layout persistence, multiple boards, undo/redo for explicit board actions, ELK auto-layout and full-screen mode.
- Dark forensic and classic corkboard themes. Actual acquired image/PDF previews; missing portraits and builds are explicitly marked unavailable.
- Resizable source/relationship inspector with locally bundled PDF.js rendering, page navigation, exact-text search and coordinate highlights, image original, extracted text, document page blocks, hashes, metadata, exact passages and supporting citations. Original HTML is served as a download, never executed in an iframe.
- Durable two-worker acquisition queue: public HTTP(S), redirects revalidated, robots.txt rules, per-domain serialization and delay, retry/backoff for transient requests, pause/resume/cancel, visible failure reasons, 25 MB per-file and 5 GB evidence-vault limits.
- Read-only SHA-256 content-addressed originals, separate derivatives, duplicate IDs retained, repeated retrieval logs and chain of custody. `ORIGINAL VERIFIED` means byte integrity was verified; it does **not** certify every statement in a source.
- PDF text, page coordinates, metadata and first-page previews; image dimensions, EXIF, histogram, average hash, OCR; webpage text; JSON records; static text/code strings; FFprobe metadata and video first frames. Speech transcription is explicitly unavailable.
- SQLite WAL + FTS5 BM25 text search. SQLite replaces external databases for this small local release; it is not a substitute for the full proposed graph/vector stack at millions-of-records scale.
- Cipher workbench: hex, Base64, binary, Caesar/ROT, acrostics, X Snowflake timestamp and Unix timestamp. Exact inputs, parameters, negative controls, outputs, entropy and attempt counts persist. Results remain `UNVALIDATED`; holdout testing and statistical significance are pending.
- Interactive chronology supports zoom, pan, layers, sourced dates and uncertainty intervals. Acquisition and archive replay dates remain distinct from publication/creation dates; human date interpretation stays explicit.
- Offline MapLibre map with a bundled Natural Earth public-domain basemap. Source-linked public institutions/events only; investigator-entered coordinates are explicitly approximate.
- Graph intelligence: independently rechecked citation layer, connected components, degree ranking, bounded neighbourhoods and shortest paths. GraphML/GEXF exports retain claim states and citations. This uses an in-memory projection of SQLite boards, not a large-scale graph server.
- Claim review queue: exact-source support and contradiction, original/derivative integrity validation on proposal and review, accept/reject/dispute decisions, transactional graph updates and permanent audit records. Citation matching is not automatic logical-entailment verification.
- Historical comparison: side-by-side actual preserved text, bounded reproducible line diff, original/derivative hashes and capture dates, persisted experiments. It does not infer game-binary changes.
- Checkpointed investigation runs with seven named stages: Chief Investigator, Document Intelligence, Graph Intelligence, Chronology, optional Analyst, Evidence Auditor and Red-Team Analyst. Each task records its dependency, input original IDs, tool, attempts, output, timestamps and failure. Pause/resume/cancel and restart recovery work. Deterministic stages run without a model; they are not presented as autonomous language-model reasoning.
- Optional fixed-endpoint Ollama and Claude API adapters. Local installed models can be selected when Ollama is reachable. Claude requires `ANTHROPIC_API_KEY` and a configured/requested model name. A reviewed local Ollama 0.40.3 service and Qwen 2.5 1.5B model are now running here. All five OCI model blobs (986,061,892 bytes total) were SHA-256 verified through the session proxy. A real run extracted inventor names with an exact citation; earlier wrong/misquoted proposals were rejected and remain in the task history. Claude is not configured. Model results are proposals, exact citations are checked against supplied passages and stored originals, source locations are derived independently, and no factual graph edges are generated automatically. A user can attach a citation-checked model proposal to the board as a `HYPOTHESIS`, with its exact source link and review status. Attachments are idempotent and are not fact approvals.
- Disposable Docker parsing: network disabled, read-only original and root filesystem, only an isolated output directory writable, all capabilities dropped, no new privileges, 768 MB memory/no swap, one CPU, 64 processes, 45-second CPU limit and 90-second wall deadline. Worker result/path/output limits are checked before derivatives are committed. Original hashes are checked before and after processing; derivative hashes are recorded. Failed isolation retains the original and shows the processing failure. The API does not import image/PDF parsers for evidence preflight.
- JSON and CSV exports. ZIP is explicitly a **metadata archive**, with hash manifest and original-omission reasons where redistribution rights are unknown. It is not advertised as a complete original-file export.

## Built-in continuous watch

Open **Continuous watch** in the sidebar. Create a named watch and choose:

| Source | Behavior |
| --- | --- |
| Crossref | Search bibliographic records; filter title/abstract/subjects against every meaningful query term; preserve the actual API response; enqueue eligible new source URLs. A metadata response is not an acquired research-paper PDF. |
| RSS / Atom | Discover up to ten new links/enclosures per run; preserve the actual feed; deduplicate previously seen URLs. |
| Public URL | Re-fetch a source; preserve changed content separately and log unchanged hashes as repeat acquisitions. |
| NASA NTRS | Public keyword search, preserve the API response, then queue actual non-draft PDF download links from explicitly public records. Limited to ten catalogue records per run. |
| Internet Archive | Preserve the public CDX response and queue up to ten historical capture responses, collapsed by year. Capture/retrieval dates remain separate. |

Schedules support five-field cron expressions in UTC (for example `0 */6 * * *`) or intervals of at least five minutes. Cron overrides the interval. Impossible schedules and schedules with intervals under five minutes are rejected. Watches, next-run timestamps, discovered URLs and run history are database-backed. Pause, resume, run-now and remove controls work. Watch failures are recorded and retried after five minutes. Acquisition retries are separate. There is no autonomous host shell or host crontab editing.

Four six-hour watches are enabled: Caltech source-version monitoring, exact `Mondaloy` Crossref search, NASA superalloy literature and historical Bohrdom Steam captures. All four completed actual runs. The latest Mondaloy run returned zero eligible new items after relevance filtering; this is a valid empty result. An earlier broad query surfaced unrelated nickel papers: those acquisition jobs were cancelled, remain visible, and created no factual graph relationships.

The built-in cron/interval scheduler requires the backend to remain running. New successfully processed acquisitions automatically receive persistent seven-stage deterministic source audits. Unchanged originals already audited for that watch do not generate duplicate investigative plans. Pause prevents further discovery queuing. Model reasoning is optional; the automatic audit is provenance/attribution checking, not independent scientific reasoning. The v0.4 Online researcher adds multi-provider searches, public disclosure feeds and an optional general-web Brave connector. There is no private-account access or social-network surveillance. Factual entity relationships require review; literal catalogue-to-file links are distinct from biographical claims.

## Actual evidence and validation

The v0.3 verification snapshot contained **24 originals**, all independently rehashed. The first six case records were:

1. Caltech's original Tridroid Cup report.
2. The report's actual Blitzkrieg Bots photograph.
3. Google Patents' US20030053926A1 catalogue webpage.
4. Its linked original patent PDF (421,645 bytes, five pages).
5. Steam's public Bohrdom application metadata response.
6. The official Bohrdom Steam header artwork.

Seven additional actual NASA technical PDFs and six archived Steam responses (2019, 2020, 2022, 2024, 2025 and 2026) have now been acquired. Five remaining originals are two Crossref responses, two NASA search responses and one Internet Archive index response: catalogue responses are not papers. `artifacts/release-v3-evidence.json` records all 24 files, byte counts, hashes, the new boards, automatic audits and the historical comparison. The NASA literature is scientific context and does not establish a shared team or a connection to Cole Allen. Two older NASA fixture attempts remain visible failures; later acquisitions succeeded. No game binary, APK, court filing or original social post has been represented as examined.

The main board contains actual original previews and sourced links. The secondary dossier leads are on a separate board. The patent-provenance board lets the user click a person-name transcription, inspect its exact citation, and open page 1 of the acquired PDF. Monica A. Jacinto's inventor name is not automatically merged with the dossier's Monica Reza identity.

The supplied dossier is treated as secondary, unverified notes. Its proposed fourteen-person roster contains fifteen names; the discrepancy is retained. No common research team, time travel, account ownership, coordinated deaths, criminal allegation or face identity has been independently established by this application.

Validation artefacts:

- `artifacts/backend-test-results-v2.txt` and `artifacts/sandbox-investigator-test-results.txt`: 34 passing v0.2 integration tests, including immutable originals, PDF/image/video extraction, layout retention, exact-source citation enforcement, search, controls, SSRF rejection, scheduler persistence/deduplication/failure recovery, duplicate retrieval, non-execution of downloaded code, content-type mismatch and cross-origin write rejection.
- `artifacts/investigator-browser-results.json`: a complete seven-stage run, original source passages, citation audit inspection and browser reload recovery; zero runtime errors. Screenshots: `artifacts/investigator-control.png` and `artifacts/investigator-audit-detail.png`.
- `artifacts/sandbox-enforcement-probe.json`: real container checks demonstrating denied writes to the input, blocked network and absent host vault.
- `artifacts/case-sandbox-reprocessing.json`: all eight stored originals reprocessed in the isolated image, with unchanged original hashes.
- `artifacts/checkpoint-restart-verification.json`: a paused investigation survived a real service restart, retained task IDs, resumed to completion, and preserved board positions, eight original hashes and two enabled watches.
- `artifacts/browser-acceptance-results.json`: actual photograph drag persistence, page reload, hash inspector, relationship inspector, person-to-original-PDF path; zero browser runtime errors.
- `artifacts/restart-verification.json`: board positions and stored evidence hashes compared across an actual service restart.
- `artifacts/evidence-board.png`, `artifacts/patent-inspector.png`, `artifacts/continuous-watch.png`: screenshots of the real running application.
- `npm-audit.json`, `artifacts/python-audit-v2.json`: latest vulnerability scans. Initial vulnerable versions were upgraded; final scans report no known vulnerabilities.

## Earlier milestone boundaries (historical; superseded by releases above)

| Milestone | Actual status |
| --- | --- |
| A | Working board and acceptance interaction delivered. Resizable inspector and PDF.js source navigation are delivered. Advanced grouping, nested boards, spatial search and large-graph scaling benchmarks remain pending. |
| B | Original-source queue, custody, real files, hashes, inspector and failure demonstration delivered. NASA PDF and historical archive discovery are delivered. Browser capture and resumable downloads remain pending. |
| C | Basic parsers now execute in a disposable, constrained container; all case originals were reprocessed. Scanned PDF OCR is capped to two pages. Advanced tables, audio features, transcription, scene analysis and binary tools remain pending. |
| D | Seven checkpointed investigative stages, verified original/derivative retrieval, graph and chronology inspection, citation auditing and optional model adapters delivered. A real small local-model path is demonstrated. Cloud credentials, independent scientific model review and the full twelve-specialist system remain pending. |
| E | Basic reproducible cipher workbench and retrieval chronology delivered. Holdouts, robust statistical/holdout testing remains pending. Timeline zoom, sourced date intervals and preserved historical comparisons are delivered. |
| F | 24 original files and a sourced inventor-to-paper interaction delivered; NASA and historical-capture boards are populated. Prior case databases/files were absent from the workspace; full dossier ingestion and remaining source recovery are pending. |

Case-directed recurring discovery, tool checkpoints, original recovery and optional review-required proposals are implemented in v0.4. The next executable implementation task is independent scientific review with a stronger model, followed by document entity extraction and richer source-backed claim review. The current red-team checks are deterministic provenance/attribution checks, not independent scientific reasoning. No downloaded repository, install hook, script, APK or binary is executed. Docker is required for new processing; host fallback is prohibited.

Build the processing image independently with `./scripts/build_processor.sh`. It pins the Python base digest and parser versions; package manifests are stored inside the image. The image is portable in design, but the Apple Silicon build and Mac service are not tested here. The launcher uses a local Docker Unix socket and ignores remote context selectors. The trusted API has access to Docker; binding it to loopback remains essential. Container isolation is a practical boundary, not a claim that the daemon or kernel cannot be compromised.

Ollama uses the loopback HTTP service at port 11434; the app never downloads a model automatically. During this build, the reviewed small model was explicitly installed and tested. Its generation is capped at 600 tokens with a 4,096-token context and four CPU threads. It is a demonstration model with observed errors, not a substitute for independent scientific review. For Claude, configure `ANTHROPIC_API_KEY` outside source control and `SHERLOCK_ANTHROPIC_MODEL` before starting the service, or provide the model name in the UI. The key is never stored in case tables or sent to processing containers. The launchd installer does not automatically copy secrets from a terminal environment into its plist. External provider authorization is checked when a task executes; a configured key alone does not prove valid account access.

At the original milestone snapshot these integrations were pending. Later releases above implement PostgreSQL/Qdrant, semantic retrieval, authenticated access and real report/archive exports. Neo4j, richer media/binary analysis and independent scientific model review remain pending. The server is bound to loopback and has a cross-origin write guard; do not expose it as a multi-user internet service.

Dependencies include PyMuPDF (AGPL/commercial licensing), ELK.js (EPL) and otherwise commonly permissive frontend/API packages. Source is supplied; any redistribution or proprietary commercialization needs a dependency-licence review. No claim of a complete legal/licensing audit is made.


## Local model demonstration

The current local model container is `sherlock-local-model`, bound to `127.0.0.1:11434`, limited to four CPUs, 4 GB RAM/no swap and 128 processes. It has a read-only root filesystem, dropped capabilities and no case-vault mount. Its model store is separate in `.models/`. Forensic processors remain network-disabled; the model service has networking for explicitly requested model downloads. Model-generated text cannot execute host commands.

The running model is `qwen2.5:1.5b` (Q4_K_M). Repository, current release, MIT tool licence and Apache model licence were checked before installation. See `artifacts/local-model-source-review.json`, `artifacts/local-model-integrity.json` and `artifacts/local-model-runtime.json`. The native Ollama blob downloader did not work with this managed environment's proxy, so the same public OCI manifest and blobs were fetched through the inherited HTTP proxy with TLS and digest verification. Signed download URLs are redacted in failure logs; no access restriction was bypassed.

`artifacts/local-model-clean-text-investigation.json` records the real successful invocation and exact-source proposal. `artifacts/local-model-investigation.json` and earlier saved case runs retain the failed/misquoted attempts and a retried timeout. Retrieval now honours explicit page requests and excludes question boilerplate from passage selection. Exact quotes, actual original bytes and derivative hashes are checked independently. Citation matching establishes provenance; it does not establish logical entailment.

`artifacts/model-board-browser-results.json` records attaching the real proposal, retaining `HYPOTHESIS` status and surviving page reload. Screenshots: `artifacts/local-model-finding.png` and `artifacts/model-proposal-board.png`.

To use an already running native Ollama on a Mac, open Investigator, choose Local Ollama and select an installed model. The Linux container helper was tested with this environment's UID 1000; the native Mac model install/Metal acceleration path has not been tested here. To recreate the reviewed Linux demonstration, pull the official pinned release image, run `.venv/bin/python -m scripts.start_local_model`, and explicitly install with `.venv/bin/python scripts/fetch_local_model.py`. No model is downloaded as part of ordinary application startup. Model tasks remain optional and the deterministic mode stays the default.

## Third-release verification

- `artifacts/backend-test-results-v3-final.txt`: current full integration suite. `artifacts/workspaces-test-results-v3.txt`: source review, tamper rejection, graph layer/path separation, date provenance, public map categories, graph exports, archive comparison and scheduler regression checks.
- `artifacts/workspaces-browser-results-v3.json`: actual PDF canvas content, page navigation and passage coordinates; timeline zoom; offline map and source pin; graph shortest path; proposed claim persistence; resizable inspector. Browser testing leaves the real proposal **REVIEW REQUIRED**, rather than treating automated testing as human fact approval.
- `artifacts/release-v3-evidence.json`: actual acquisition and comparison proof. `artifacts/checkpoint-restart-verification.json`: real restart, persisted layouts/tasks and 24 independently verified originals.
- Screenshots: `source-chronology-v3.png`, `sourced-map-v3.png`, `network-analysis-v3.png`, `pdf-passage-inspector-v3.png`, `claim-review-v3.png`, `archive-comparison-v3.png`, `nasa-evidence-board-v3.png` in `artifacts/`.

MapLibre GL JS 6.14.0 (BSD-3-Clause), PDF.js 6.4.299 (Apache-2.0) and croniter 6.2.4 (MIT) were sourced from their upstream npm/PyPI packages and pinned. PDF workers, fonts, CMaps and WASM assets are bundled locally by the build script. No CDN is required to inspect a PDF or render the basemap. Natural Earth source attribution, checksum and public-domain terms are in `frontend/public/maps/LICENCE.txt`.
