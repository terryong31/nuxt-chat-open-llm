# Architecture decision records

Why things are the way they are, and what was rejected getting here. The
`CLAUDE.md` files say what the rules *are*; these say why. When the two
disagree, an ADR is stale — fix it.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-run-the-server-natively.md) | Run the inference server natively, no containers | Accepted |
| [0002](0002-host-the-frontend-on-vercel.md) | Host the frontend on Vercel | Accepted |
| [0003](0003-serialize-generation.md) | Serialize generation, shed excess load | Accepted |
| [0004](0004-reconcile-eos-tokens.md) | Reconcile the checkpoint's EOS tokens at load | Accepted |
| [0005](0005-render-the-frontend-client-side.md) | Render the frontend client-side | Accepted |
| [0006](0006-move-the-bff-into-a-python-gateway.md) | Move the BFF out of Nitro into a Python gateway | Accepted |

Copy the shape of an existing record. Number sequentially and never renumber.
A decision that changes gets a new record marked `Supersedes 000N`; the old one
stays, marked `Superseded`. Records are history, not documentation.
