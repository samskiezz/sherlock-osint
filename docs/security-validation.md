# Security and regression validation

Executed on 15 October 2026 against Sherlock ERPS in the cloud workspace.
The run found and fixed a gateway request-body limit bypass. It also confirmed
unresolved integration prerequisites and upstream dependency findings. The
system does not have a configured VPN, and this record does not certify it as
a VPN or establish universal safety.

See the [machine-readable results](security-test-results.json) and
[capacity measurements](security-capacity.json). Raw logs, failed-test traces
and authenticated screenshots remain private and are excluded from Git.

The final code change, `fefd3eb`, also passed the maintained
[GitHub CI workflow](https://github.com/samskiezz/sherlock-osint/actions/runs/38808765146).
That workflow's passing checks do not include the eight environment-dependent
failures or constitute a clean dependency audit.

## Executed checks

| Check | Result |
| --- | --- |
| Python coverage across 26 current modules | 563 cases: **555 passed, 8 failed**, no skips or setup errors |
| Rust workspace | **17 passed**; formatting and Clippy with warnings denied passed |
| Private relay Worker | **5 passed**; build passed |
| Authenticated browser navigation | **22 views rendered**, no page exceptions, API errors, failed resources or unexpected writes |
| ERPS browser flow | Passed navigation, deep link, lookup, lineage, source indexing and malformed-request status |
| Frontend TypeScript/Vite build | Passed; existing bundle-size warning remains |
| Production Compose / Postgres 16.15 | Passed resolution, source retraction, tombstone, audit, u64 JSON, UUID normalization, reader and anonymous denial |
| Production executable capacity | **10,000 mentions and entities**, 204,653 candidate pairs at the largest snapshot |
| Capacity recovery and limits | Idempotent retry, overflow rollback, deletion, resurrection rejection, eight concurrent reads and hard-crash restart passed |
| Original and audit integrity after deployment | Original download SHA-256 matched; case SQLite check and gateway/ERPS audit verification passed |
| Installed Python dependency audit | 103 packages; **zero known advisories** after upgrading pip to 26.2 |
| Frontend npm audit | **Zero reported vulnerable packages** |

The original 24 Python modules ran in separate pytest processes: 549 cases,
541 passed and eight failed. The added gateway suite has ten passing cases;
four ASGI body-limit cases also passed. After the gateway fix, the seven live
foundation cases and both browser checks ran again. Counts above describe
unique current coverage across these runs, not a single 563-case invocation or
an inflated sum of reruns. Legacy module-global application/vault fixtures are
the reason for process isolation.

## Gateway defect found and fixed

The gateway checked the declared `Content-Length` against its 26 MiB limit.
A chunked request omitted that header, causing the gateway to read the oversized
body and return HTTP 422 from validation instead of rejecting it with HTTP 413.
An owned 27 MiB test reproduced this gap without touching the live administrator
account or an external target.

The new ASGI middleware counts received body bytes and rejects overflow before
the route receives the request. Bounded valid chunks replay unchanged. Tests
also verify that reading stops at overflow, a false zero declared length does
not bypass the limit, and non-HTTP scopes pass through. Existing rate limiting
still runs before body buffering. Fourteen gateway/body-limit checks passed.
The workspace gateway was restarted with the fix; authenticated navigation and
original-file streaming passed afterward.

The live foundation fixture now retires its own temporary accounts and revokes
their tokens during teardown, retaining their audit history. Gateway adversarial
tests use a separate temporary Postgres database and a unique Redis key prefix;
they remove both without changing the operator's administrator account.

## Bounded adversarial and backtesting coverage

- Ten incorrect guesses against an owned account: five HTTP 401 responses,
  followed by five HTTP 429 responses. Forwarded-IP headers did not bypass it.
- Twenty-two rotating nonexistent usernames: the per-IP limit rejected requests
  21 and 22. No guesses were sent to the running gateway or a third party.
- A 605-request burst against the isolated gateway: requests 601 onward returned
  HTTP 429, while the health endpoint stayed available.
- A 140-token corpus covered malformed JWTs, unsigned tokens, wrong signatures,
  expired claims, wrong issuer/audience, missing users and revoked versions.
- Role-header spoofing, disabled accounts, logout revocation, secure cookie
  attributes, cross-origin writes, limiter outage and secret-free audit records.
- 20,000 deterministic provenance-wire mutations: no decoder panic; accepted
  values round-tripped and source retraction stayed idempotent.
- All 4,096 triples in a 16-polynomial family preserved semiring and deletion
  homomorphisms, counting/Boolean views and witness-set behavior.
- All 729 four-node hard-constraint graphs across four seeds: inconsistent
  constraints were rejected; valid partitions preserved every hard constraint.
- Existing real Docker extraction, tamper detection, cancellation, source-bound
  citation, SOCKS hostname forwarding and clearnet-redirect rejection tests passed.

These are finite input families and owned stress workloads. They are not a
proof against every protocol input, implementation defect or attack.

## Capacity result

The release executable came from the verified production image
`sha256:81696b4223c6a57d2389273a87a8d7d04210c9e266f794817411c3ad53e3c6d6`.
It used a temporary Postgres database, random identifier surfaces and distinct
overlapping synthetic passport identifiers, giving singleton ground truth.
Both Rayon and DataFusion scoring ran. The test removed its database afterward.

The 10,000-mention request snapshot generated 204,653 candidate pairs and took
40,631.607 ms for that batch's HTTP round trip. Rust API peak resident memory
was approximately 462 MiB. Ten increasing batch sizes do not establish latency
percentiles. Compiler activity shared the cloud machine during this run.
The workload measures this bounded system's capacity and recovery, not entity
matching accuracy, a production SLA or million-mention performance.

## Eight failed integration cases

Three foundation cases remain failed:

- The graph/investigator case expects a historical named board/evidence fixture
  absent from the source-only checkout.
- The collector case fails public acquisition DNS validation in this environment.
- The bridge case expects a historical original omitted from the source archive.

Five retrieval cases remain failed: embedding-manifest verification, real hybrid
search, keyword/index inventory, saved-query/export workflow and Viewer retrieval
workflow. The local model runtime responds but has **zero installed models**;
the reviewed embedding model does not pass validation. The required search/index
services and historical source corpus are not fully available. Search requests
return HTTP 503. Assertions were preserved, historical originals were not
fabricated, and SSRF or TLS checks were not bypassed to force passing results.

Historical case-specific browser acceptance/screenshot scripts reference omitted
originals, fixed evidence IDs and old case state. They were not blindly replayed
against the current case. The current 22-view navigation smoke and ERPS functional
browser flow were executed as separate, explicit checks.

## Dependency and static-analysis findings

The audits are not all clean:

- **Rust:** cargo-audit 0.22.2 used a database of 1,329 advisories at revision
  `edb58f5974b83eb8302332821cb6d389777aa351`. The 397-package lockfile includes
  `rsa 0.9.10`, flagged by `RUSTSEC-2023-0071`, with no patched version reported.
  `cargo tree -p erps-api -i rsa` showed no active API dependency on it; the
  advisory remains reported rather than suppressed.
- **Active Rust cache dependency:** Tantivy 0.22.1 uses `lru 0.12.5`, with
  `RUSTSEC-2026-0002` and `RUSTSEC-2026-0253` unsoundness warnings. Their patched
  ranges start at 0.16.3 and 0.18.2 respectively. The latest supported Tantivy
  0.26.2 still requires lru 0.16.x, so a routine version update does not resolve
  both findings. `instant` and `paste` also have unmaintained-package warnings.
  These remain unresolved dependency findings, not a clean Rust audit.
- **Optional CyberChef adapter:** npm reports 25 affected packages across three
  root advisories: node-forge signature verification, file-type ASF parsing and
  elliptic implementation risk. Two packages are rated high, 19 moderate and four
  low. Installed CyberChef 11.5.0 and node-forge 1.4.0 are current releases; npm's
  proposed CyberChef 7.1.0 downgrade is not an established compatible repair.
  Decoder execution remains non-root, network-disabled, read-only and bounded
  by CPU, memory and wall time. Containment does not remove upstream defects.
- **Bandit:** 264 low and two medium findings, no high findings. The medium
  findings are explicit `/tmp` tmpfs configuration paths for containers. Raw
  findings remain available privately; low findings were not hidden to make
  the tool return success.

## Reproduce the maintained checks

Prepare the existing Python environment, processor image, Postgres, Redis and
running authenticated application as described in [the operating guide](erps.md).
Use a fresh output directory for each run; outputs can contain private fixtures.

```bash
SHERLOCK_PROCESSOR_IMAGE=sherlock-processor:0.4-cloud \
  .venv/bin/python scripts/run_test_matrix.py --output data/test-audit/new-run
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
npm --prefix hosting/private-access test
npm --prefix hosting/private-access run build
npm --prefix frontend run build
npm --prefix frontend run test:workspace-smoke
npm --prefix frontend run test:erps-browser
.venv/bin/python scripts/stress_erps.py --binary target/debug/erps-api \
  --output data/test-audit/new-capacity --mentions 10000
.venv/bin/pip-audit
npm --prefix frontend audit
npm --prefix integrations/decoders audit
.venv/bin/bandit -r backend foundation processing scripts
```

Use the standard `sherlock-processor:0.4` image when that is the locally prepared
image; the `0.4-cloud` image is the tested cloud runtime profile. The capacity
harness accepts a separately built release executable through `--binary`.
For the Rust lockfile advisory check, install cargo-audit 0.22.2 through Cargo's
verified registry and run `cargo audit --json`. A nonzero security-audit exit
status must be investigated, not treated as a successful test.

## Access and VPN limits

The native gateway, core and ERPS respond inside the workspace. Its private
hosting credentials remain unbound; no externally working application link has
been verified. The environment reports `vpn_configured: false` and has no TCP
grants or VPN test target. Actual VPN tunnel operation, routing, kill-switch,
MTU, IPv6/DNS leak behavior and traffic anonymity remain untested. A passing
SOCKS or container-isolation fixture does not establish those properties.
