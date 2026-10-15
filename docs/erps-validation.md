# ERPS validation record

The later [security and full-regression report](security-validation.md) records
the expanded run, gateway fix, 10,000-mention capacity check and open dependency
findings. Counts below describe the earlier implementation validation.

Validated on 15 October 2026 in the cloud workspace. This record distinguishes
executed checks, a resolved test-contract mismatch, and blocked external checks.
It does not certify every capability of the thesis or the existing platform.

The ERPS implementation commit `4632830` passed the [GitHub Actions verification
run](https://github.com/samskiezz/sherlock-osint/actions/runs/38743720862), including
its separately provisioned Postgres 16 acceptance tests. The two preceding code
commits also passed. Documentation-only updates do not rerun this workflow.

| Check | Result |
| --- | --- |
| Rust workspace tests | 14 passed, including an 8,385-pair multi-batch scoring parity test |
| Rust formatting / Clippy with warnings denied | Passed |
| ERPS Python acceptance tests | 16 passed; real Rust process and temporary Postgres database |
| Existing local backend regression | 490 current cases covered across module and focused runs; details below |
| Foundation integration | 4 passed, 3 failed due to missing historical fixtures and public DNS |
| Available retrieval tests | 5 passed; 6 model/search checks not run |
| Private relay Worker tests | 4 passed |
| Private access follow-up | 25 Python checks and 5 Worker checks passed; includes real HTTP companion/Worker round trip using fixture storage |
| Frontend TypeScript and Vite build | Passed; existing large-chunk warning remains |
| Authenticated Chromium flow | Passed; no page exceptions; entity deep link, search, lineage, indexing, malformed-input status |
| Live gateway roles | Viewer/Analyst/Admin boundaries passed, including forged-header rejection |
| Original preservation | Uploaded synthetic original retrieved byte-for-byte; SHA-256 verified |
| Restart/outbox recovery | Controlled missing outbox entry recovered after supervisor restart |
| Native Docker image | Passed real Postgres resolution, retraction, audit, anonymous denial and non-root/read-only/capability checks |
| Production source image / isolated Compose | Passed on Postgres 16.15, including exact u64 JSON and UUID-normalized retraction |
| Python dependency consistency | pip check passed |
| Staged source privacy check | No bound runtime secret values, evidence vault, databases or build outputs included |

Production image: `sherlock-erps:0.1`, SHA-256
`81696b4223c6a57d2389273a87a8d7d04210c9e266f794817411c3ad53e3c6d6`.
The image was built from locked source in the pinned Rust toolchain and tested
with a fresh, isolated Postgres 16 database. Its temporary project and volume
were removed. The first cold release build took 43 minutes 50 seconds with two
compiler jobs in this VFS-backed environment; subsequent workspace rebuilds
reused compiled dependencies. A build-context exclusion error and a Compose
tmpfs-list error were found and corrected during these checks. The final
Compose test passed. The smaller Alpine Postgres image provides appropriate
headroom on the 32 GiB cloud disk. Build cache cleanup preserved the case vault,
active database volumes, model runtime and active application images.

## Regression accounting

The twenty existing local backend modules ran in **separate pytest processes**
with `SHERLOCK_PROCESSOR_IMAGE=sherlock-processor:0.4-cloud`,
`SHERLOCK_CONTAINER_CREATE_TIMEOUT=180`, and `ERPS_AUTO_INGEST=0`. This respects
fixtures that initialize a module-global application and vault. The raw full
run executed 489 cases: 488 passed and one failed, with no setup errors.

The failure was `test_timed_out_container_creation_still_attempts_owned_cleanup`:
its assertion hard-coded 45 seconds after creation timeout became configurable.
That test now runs at both 45 and 180 seconds, checks the selected creation
budget, and retains the assertions that the exact owned container is removed
following timeout. Both replacement cases passed. The other nine visual tests
passed unchanged in the module run. Thus the 490 current local cases are covered
by 488 unchanged passing cases plus two passing replacement cases. This is
coverage across those runs, not a claim that a new single 490-case invocation
was executed. Raw outputs remain private in `data/onboarding-validation`.

The sandbox/investigator module passed all 18 cases (about eleven minutes on
VFS); workflow and workspace modules passed all 16 and 12 cases respectively.
The implementation retains network-disabled extraction, immutable originals,
read-only mounts/root, dropped capabilities and the independent 90-second
parser execution limit. The core's creation timeout is bounded to 45–300 seconds.

Across the recorded Python runs including the private access follow-up,
540 cases passed, three external integration
cases remain failed, and six retrieval cases were not run. Rust, browser,
container and Worker checks are reported separately rather than mixed into
that Python count.

## Remaining foundation failures

- `test_source_verified_graph_and_investigator_routes`: expects a historical
  board/evidence fixture absent from the source-only checkout.
- `test_internal_bridge_requires_token_and_preserves_original_bytes`: expects
  an omitted historical original. New synthetic originals pass byte retrieval.
- `test_persistent_celery_job_actual_original_and_ownership_not_assumed`:
  acquisition is blocked by public-host DNS resolution in the environment.

These failures were present during onboarding before ERPS was added. Historical
fixtures were not fabricated, assertions were not suppressed, and SSRF/TLS checks
were not bypassed. The six deferred retrieval checks require Elasticsearch,
installed embeddings and an original-backed corpus that are not available here.

## Measured synthetic evaluation

See [the complete machine-readable measurements](erps-evaluation.json).
The fixed sample has 100 entities × 5 mentions, noise 0.15, seed 42, five repeats.
The actual measured pairwise F1 was **0.881432**, B-cubed F1 **0.907343**,
exact-cluster F1 **0.448980**, blocking recall **1.0**, and reduction **0.755784**.
The unoptimized sequential scalar harness measured p50 **5844.29 ms**, p95/p99
**7088.01 ms**. Those timings exclude HTTP and Postgres, were collected in a
shared cloud environment, and do not represent production latency guarantees.
The blueprint's example 45/120/280 ms numbers were not reused as results.

## Deployment and scope

The native authenticated application is verified at
`http://127.0.0.1:8010/?view=entities` inside this workspace. The Rust listener is
on loopback port 3000; original evidence is served by the loopback Python core.
The source repository is separate from the running application.

The existing private Sites URL responds with an authentication boundary.
Owner service/relay credentials are not bound in this workspace, so a hosted
ERPS request through that site has **not** been verified and the relay has not
been started. No externally working application link is claimed by the source
push or by the environment configuration draft.

The access follow-up fixes the authentication preflight to read an absent input
ticket (HTTP 410). The earlier unknown-operation probe expected HTTP 404, but
the Worker validates a ticket first and returns HTTP 400 for that request.
Secure environment startup and a remote verification command are now checked in;
the foundation launcher starts the relay when its bindings are present. Verification
requires remote frontend HTML, ERPS health, an authenticated entity query and the
anonymous sign-in boundary before it prints an external application URL. All
25 Python access checks passed, including an HTTP round trip through the actual
Worker code and Python polling companion against a synthetic gateway and an
in-memory R2 fixture. Five Worker checks also passed. This fixture execution
does not establish access to the live Sites deployment or create hosting credentials.

Implementation limits and security boundaries are in [the operating contract](erps.md):
10,000 mentions/workspace, 500,000 candidate pairs, full-workspace repair,
uncalibrated scoring, finite exact provenance bounds, logical retraction with
historical retention, and a constrained pivot heuristic without a claimed
approximation guarantee. There is no full ontology reasoner, arbitrary action
executor, distributed execution, full OTLP deployment or Palantir/Cellebrite parity.
