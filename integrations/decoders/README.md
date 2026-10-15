# Established automatic decoder

GCHQ CyberChef 11.5.0, Apache-2.0, fixed Magic operation. This adapter infers decoding chains; it never accepts recipes or executable code from an investigation.

Install reviewed dependencies with Node 24 and npm:

```sh
cd integrations/decoders
npm ci --ignore-scripts
cd ../..
.venv/bin/python scripts/patch_cyberchef_imports.py
```

The lockfile records npm integrity hashes. The narrow ESM suffix patch follows CyberChef's documented Node API fix and records each changed file's before/after hash. Terser is explicitly pinned because this upstream package imports it at runtime. No dependency install hook is executed.

Execution uses the pinned Python slim base solely as an isolated Linux runtime, a read-only trusted Node executable and this read-only directory. It has no network, vault, credentials, host shell interface or writable root; 1 CPU, 1536 MiB, PID and time limits apply. At most two decoders run concurrently. Linux Node 24 is tested here; Apple Silicon deployment remains untested.

Security review 15 October 2026: `artifacts/decoder-audit-v11.json` reports 25 dependency findings (4 low, 19 moderate, 2 high including the aggregate CyberChef finding). The high underlying node-forge signature-verification advisory GHSA-86w9-cpqp-85rv affects the newest published 1.4.0; no fixed npm version was available. This adapter performs automatic data transformations, never certificate/signature authentication. Container isolation reduces exposure but does not erase these findings. Do not use this dependency tree for trust or signature decisions. Re-audit before deployment.

Magic's language scores are heuristics, not probabilities of authentic hidden messages. Returned candidate count does not expose every internal attempted transformation. Results need independent controls and interpretation.
