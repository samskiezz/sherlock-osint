# ERPS construction and operating contract

ERPS is an executable Rust service integrated with Sherlock's Python backend
and React entity browser. Postgres is the authoritative persistent store.
Tantivy is a disposable index of a committed database snapshot; DataFusion and
Arrow are in-process batch execution components, not persistent stores.

## Build and run

Prerequisites: the existing Sherlock Python/Node installation, a running
foundation Postgres instance, and Rust 1.90.0 (pinned in `rust-toolchain.toml`).
Install Rust through the official rustup installer if it is absent. A C linker
(`build-essential` on Debian/Ubuntu) is also required. Preserve the cloud
environment's proxy and TLS configuration.

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/erps-rustup.sh
sh /tmp/erps-rustup.sh -y --profile minimal --default-toolchain 1.90.0
. "$HOME/.cargo/env"
rustup component add rustfmt clippy
```

```bash
./setup.sh
.venv/bin/pip install -r foundation/requirements.lock
cargo build --locked -p erps-api -p erps-eval
.venv/bin/python scripts/setup_erps.py
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run_erps_stack.py
```

The foundation database must already be provisioned using the repository's
foundation setup. These commands preserve its existing private configuration.
`setup_erps.py` creates a dedicated `erps_app` role and `erps` database using
the existing local database administrator. It generates random service,
writer, and reader tokens in `data/erps.json` (0600). It never prints secrets
or overwrites an existing configuration. A separately provisioned deployment
can instead supply `ERPS_DATABASE_URL`, `ERPS_TOKEN`, `ERPS_WORKSPACE` and
optional `ERPS_READER_TOKEN`/`ERPS_WRITER_TOKEN` environment variables to the
Rust executable. Migrations run at service startup.

Open `http://127.0.0.1:8000` and select **Entity resolution**. For authenticated
access through the existing gateway, run its normal bootstrap and launcher:

```bash
.venv/bin/python scripts/bootstrap_foundation.py
.venv/bin/python scripts/run_foundation.py
```

Then use `http://127.0.0.1:8010/?view=entities`. The core and ERPS listeners remain on
loopback. A public/private hosted link needs an independently configured
authenticated relay or deployment; GitHub source publication does not create
a running application. `run_erps_stack.py` supervises Rust and core together,
refuses occupied ports, and stops its children on shutdown. For a single
service use `.venv/bin/python scripts/run_erps.py`.

For a separate Compose deployment (do not run it alongside native ERPS on the
same port), `setup_erps.py` also generates private Compose credentials:

```bash
docker compose -f compose.erps.yml up --build -d
```

The production Docker target compiles the pinned source with Cargo.lock.
The optional `proxy_ca` build secret preserves managed TLS trust without
disabling certificate validation; Compose supplies the current CA bundle.
The `native` target packages an already compiled executable for a quick runtime
smoke test: `docker build -f Dockerfile.erps --target native -t sherlock-erps:local .`.
No credentials, vault files, models or frontend caches enter this build context.

## Request and commit sequence

1. Authenticate the bearer token against `erps.policies` and require
   `X-ERPS-Purpose: investigation`. Writes require a full workspace policy.
2. Begin a SQL transaction and take a workspace advisory lock. Validate
   mentions and check identifier fields against `erps.ontology_types`.
3. Insert immutable mention IDs idempotently. An ID reused with different
   content returns 422; the entire request rolls back. Retracted sources
   cannot be reintroduced.
4. Read the complete workspace snapshot, including incoming mentions. Build
   Tantivy, commit it and reload its reader **before** querying blocking keys.
   Each distinct key is queried once. Overlarge non-identifier blocks are
   skipped. Optional MinHash bands augment this candidate set.
5. Score candidate pairs with Rayon, or DataFusion ScalarUDFs at 10,000 pairs.
   Arrow batches contain at most 8,192 pairs. SQL/UDF failure falls back to
   the same scalar scorer and emits a warning. Null UDF arguments propagate
   null; malformed HTTP mention fields are rejected. Columnar transport does
   not imply that string similarity itself is SIMD accelerated.
6. Apply 0.92 merge and 0.80 review thresholds. Missing context uses name-only
   scoring. Scores are heuristic and uncalibrated. Review edges remain
   undecided; unobserved pairs are not negative constraints.
7. Contract must-links, including matching strong identifiers. Reject
   contradictions with cannot-links, types or overlapping strong identifier
   conflicts. Run a deterministic seeded constrained pivot heuristic and
   check each proposed group against every existing cluster member.
8. Compute membership provenance by summing mention annotations. Persist
   entities, membership, temporal identifier assertions, pair decisions,
   transaction-time entity versions and a hash-chained audit event in the
   same transaction. Pair decision evidence uses the product of its input
   annotations and is returned separately from membership provenance.
9. Commit Postgres and return the partition. No index commit follows the
   transaction and no uncommitted index is reused by later requests.

Entity IDs are UUIDv5 of the workspace and sorted mention IDs. A changed
membership partition creates different IDs; `/entities/:id?as_of=<RFC3339>`
can read a previous transaction-time version. Valid-time intervals are
half-open. The core implements all 13 Allen relations and their composition.
The ontology is a flat, database-backed type/identifier catalogue and
constraint checker; it performs no DL-Lite entailment.

## Provenance and retraction

JSON uses `{"monomials":[{"vars":["<source UUID>","<source UUID>"],"coeff":2}]}`.
Repeated variables encode exponents. Deserialization sorts factors, combines
duplicate terms and removes zero coefficients. Arithmetic uses checked u64
coefficients. Overflow, more than 4,096 monomials or more than 256 factors
per monomial rejects the operation; the service never substitutes a different
polynomial or support-only approximation.

`GET /lineage/:id` returns `how`, `support`, `why`, `minimal_witnesses`,
`boolean`, `count`, and candidate `decisions`. Why contains all witness sets
represented by monomials; witnesses need not be minimal. Minimal witnesses
are a separate absorptive view. Boolean truth also handles the constant one,
whose variable support is empty. Source variables identify evidence files,
so this is file-granularity provenance rather than distinct base-tuple labels.
Counting derivations does not measure independent evidence or probability.

`POST /deletion {"source_var":"<UUID>"}` zeros that variable. A mention with
another surviving derivation is retained. Mentions whose annotation becomes
zero and their incident manual constraints are removed. The **whole workspace**
is then reblocked, rescored and reclustered in one transaction. This supports
cluster splitting without assuming that the clustering algorithm is monotone.
Failure rolls back both the retraction and the partition update. Retraction
is idempotent. Original vault evidence and historical entity versions remain;
this operation is a logical retraction, not physical erasure or a retention
compliance mechanism. Arbitrary action execution/cascading is not implemented.

## Python ingestion and access control

With `ERPS_AUTO_INGEST=1`, successful isolated extraction enqueues a SQLite
outbox entry keyed by evidence ID and extracted-text SHA-256. A bounded worker
retries every 30 seconds, at most ten attempts; failures remain visible in
`/api/erps/sources`. Reindexing a pending/failed source explicitly queues it
again with a fresh retry budget. Each poll also reconciles a bounded batch of
verified evidence against outbox hashes, recovering a crash after extraction
commit but before enqueue. Only verified evidence is accepted. Email, DOI, handle and possible
person mentions are extracted using documented regex baselines. Offsets are
UTF-8 byte positions in the extracted text and explicitly carry
`offset_space=ExtractedTextUtf8`; they are not PDF byte offsets. UUIDv5 IDs make
retries idempotent. Manually structured requests can specify `SourceBytes`.

The foundation gateway maps authenticated Admin, Analyst and Viewer roles to
distinct server-owned ERPS policies. Admin can retract; Analyst can resolve;
Viewer can read. Forwarded role headers require the internal bridge token,
and client-supplied role headers are discarded by the gateway. The native
loopback core is a trusted desktop boundary and has full local access.
Do not expose that core directly to a network.

Policies can restrict workspace, purpose, kind, visible source UUIDs, and
top-level properties. Restricted principals are read-only. An entity with
any hidden supporting or referenced source is withheld entirely; the service does not
remove a conjunct from a witness and falsely present the remainder as proof.
Property filtering applies to entity responses. Provenance and decision
properties require their respective allowances. Query filters cannot inspect
withheld properties; graph traversal requires the relationships property.
Successful object reads and
writes are audited; gateway access decisions, including denials, are also
audited by the foundation. Direct Rust authorization failures return 401/403
without an object audit event. These ERPS restrictions do not add fine-grained
security to the separate legacy evidence-vault API, which retains its case-wide
gateway roles. This is not Palantir-equivalent cell security.

## Endpoints and failures

| Endpoint | Behavior |
| --- | --- |
| `POST /resolve` | Ingest up to 1,000 mentions/constraints and return partition |
| `GET /entities?after=&limit=&q=&kind=&valid_at=` | Stable UUID cursor, max 100/page |
| `GET /entities/:id?as_of=` | Current or historical transaction-time entity |
| `GET /entities/:id/neighbors?depth=&limit=` | Visible candidate review associations, depth 1–3, max 100 nodes |
| `GET /lineage/:id` | Five provenance views, minimal witnesses, pair evidence |
| `POST /deletion` | Logical source retraction and complete workspace repair |
| `GET /ontology` | Type and strong-identifier definitions |
| `GET /audit/verify` | Verify the workspace hash chain; full policy required |
| `GET /metrics` | Protected Prometheus counters and pool gauge |
| `GET /health` | Database readiness and configured service limits |

All object endpoints require authentication and purpose. Missing objects and
hidden objects both return 404. Contradictory constraints, invalid intervals,
resource exhaustion and immutable-ID conflicts return 422. Saturated resolve
capacity returns 429. Database failure returns 503 and rolls back writes.
The foundation bridge/proxy timeout defaults to 300 seconds (configurable
with `SHERLOCK_CORE_PROXY_TIMEOUT`, clamped to 120–600). This accommodates
slow cloud Docker creation while retaining the parser's separate 90-second
execution budget; `SHERLOCK_CONTAINER_CREATE_TIMEOUT` is clamped to 45–300.
Request bodies are capped at 8 MiB; two resolve/deletion operations can run at
once. There is no distributed queue or unbounded background index writer.
Crash recovery simply rebuilds the index from Postgres at the next resolve;
committed entities can be read immediately after restart.

Audit rows reject UPDATE/DELETE through a trigger. Sequence allocation is
serialized. Hash verification detects inconsistent stored rows, but a database
administrator can replace an entire chain; externally store returned audit
heads when that threat matters. JSON tracing and basic Prometheus metrics are
implemented; an OTLP collector/exporter is not configured.

## Verification and measured limits

```bash
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
.venv/bin/python -m pytest tests/test_erps.py -q
cargo run --locked -p erps-eval --bin eval -- \
  --entities 100 --mentions-per 5 --noise 0.15 --seed 42 --repeats 5 \
  --output data/erps-evaluation.json
```

The Python acceptance tests create and drop a dedicated test database, launch
the actual Rust binary, exercise real SQL transactions, kill/restart the
service, and compare DataFusion/Rayon results. They require local database
administrator credentials for test database creation. CI provisions its own
Postgres service; no application secrets or vault originals enter CI.

The evaluation harness measures pairwise precision/recall/F1, B-cubed,
exact-cluster F1, blocking quality/recall/reduction and empirical latency
quantiles using a fixed synthetic dataset. Contingency-table metrics avoid an
all-pairs metric calculation. Generated noise and seeded UUIDs are reproducible.
Latency covers in-process blocking/scoring/clustering, excludes HTTP and
database persistence, and uses the build profile of the executable. Five
repeats cannot establish a reliable production p99. The blueprint's sample
output is not an experimental result. Accuracy on synthetic names does not
establish forensic accuracy; no labeled real forensic corpus is bundled.

Current hard bounds are 10,000 mentions/workspace and 500,000 candidate pairs.
Whole-workspace repair, in-memory snapshots and a single Postgres service are
appropriate for this bounded implementation. Million-mention throughput,
interactive logarithmic lookup/traversal guarantees, distributed execution,
LP approximation algorithms and Palantir/Cellebrite parity are not claimed.
Pivot's classical expected factor 3 applies to the complete unweighted signed
problem, not this partial graph with hard constraints. MinHash is optional
(`ERPS_LSH=1`); its deterministic hash family approximates ideal independent
permutations. For ideal rows, b=32/r=4 gives collision probability 0.8732 at
J=0.5 and 0.003195 at J=0.1. Dropping skewed blocks can reduce recall.

`examples/erps/resolve.json` contains two **synthetic** mentions for a manual
API smoke test. These UUIDs and names do not represent acquired evidence.
