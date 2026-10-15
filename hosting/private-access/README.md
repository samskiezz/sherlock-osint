# Private HTTPS access Worker

This is the source of the existing owner-private Sites relay. The native Python companion is `scripts/private_site_access.py` at the repository root.

The Worker needs an R2 binding named `BUCKET`, a separately provisioned `RELAY_SECRET`, and owner-only authentication enforced by the hosting service. Never deploy it with public access. No runtime secret is included in this source. `.openai/hosting.json` identifies the existing Sites project; creating a different deployment requires its own hosting configuration and bindings.

Run `npm test` here to exercise the relay protocol using an in-memory storage fixture. Run `npm run build` to validate the Worker and produce the Sites build directory. This source upload does not provision hosting, an evidence vault or a running relay.
