# Identity strategy: unique positioning + fast to market

## Product wedge (v1): Agent handoff gate

**Trust Auditor** is sold as one product: a **handoff / payout gate** for teams that ship agents which **delegate**, **call other agents**, or **move money**. Buyers are usually **technical leads** at small companies (seed–Series A), not “generic AI trust” committees.

- **Headline job:** decide **allow / deny / review** before a high-stakes handoff, with **evidence**.
- **Not v1 positioning:** global reputation network, universal agent certification, or bank-grade KYC claims.
- **Identity ladder below** supports the gate (registered → operator_verified → partner_attested); the **transaction log** grounds behavior in **observed outcomes**.

This is an **operator playbook**, not legal advice. It pairs with the reference registry in `src/identity_registry/`.

## What makes the service defensible

Most stacks stop at “ID string looks valid.” You differentiate by shipping **layered accountability** buyers can reason about:

| Layer | What it proves | Time to ship |
|--------|----------------|--------------|
| **Mechanical** | Agent id format + optional signing key + your log correlation | Days |
| **`registered`** | Operator metadata on file; revocable listing | Days |
| **`operator_verified`** | *Your* process touched the record (manual review, paid onboarding, light KYB) | Days–weeks |
| **`partner_attested`** | A **partner system** you trust (marketplace, bank, IdP, enterprise customer) asserts the agent | Weeks (integrations) |
| **Multi-registry quorum** | Your registry **and** a partner registry must agree (`IDENTITY_REGISTRY_QUORUM`) | Weeks |

You do **not** need a “global truth network” on day one. You need a **clear ladder** and honest labeling in API responses (`trust_tier`, `flags`).

## Recommended phases

### Phase A — Launch (0–4 weeks): speed + honesty

- Ship **self-serve** `POST /v1/agents` so agents appear as `trust_tier: registered`.
- Keep **`REGISTRY_REQUIRE_KYC` and `REGISTRY_REQUIRE_SIGNING_KEY` off** initially so friction is low.
- Turn on **transaction log** (`MCP_SERVER_BASE_URL`) so reputation is tied to **observed behavior**, not vanity IDs.
- **Positioning**: “We don’t claim universal KYC; we claim **cryptographic identity + behavioral history + revocable listing**.”

### Phase B — Revenue wedge (1–2 months): operator verified

- Charge for **`operator_verified`**: manual or semi-automated review (video call, domain email, company registry check).
- Use **`POST /v1/admin/agents/{id}/attest/operator`** (protected by `REGISTRY_ADMIN_API_KEY`) after your checklist passes.
- Publish a **Trust Badge** mapping: what `operator_verified` does and does **not** mean.

### Phase C — Moat (2–6 months): partner attestations

- Sign **one** distribution partner (marketplace, cloud vendor, payments stack) that sends **`POST /v1/partner/v1/agents/{id}/attest`** with a shared secret.
- Their signal becomes **`partner_attested`**—strictly stronger than self-serve in your product story.
- Add their registry URL as a **second** entry in `IDENTITY_REGISTRY_URLS` with `IDENTITY_REGISTRY_QUORUM=majority` or `all` for high-value SKUs.

### Phase D — Enterprise (ongoing)

- `REGISTRY_REQUIRE_SIGNING_KEY=1`, `REGISTRY_REQUIRE_KYC=1`, private VPC registry, SLA, human dispute queue.

## Product rules of thumb

1. **Never imply bank-grade KYC** unless a licensed partner or your counsel says so.  
2. **Down-tier on incident**: suspend first, revoke after investigation; preserve audit trail (`metadata`, attestation timestamps).  
3. **Multi-source identity** beats single-source for anti-gaming: pair your registry with a partner feed when you can.

## Technical hooks in this repo

- Status JSON: **`trust_tier`**, **`attestor`**, **`partner_id`**, **`partner_ref`**, **`attested_at_unix`**.  
- Admin: **`REGISTRY_ADMIN_API_KEY`** + operator attest endpoint.  
- Partner: **`PARTNER_ATTESTATION_TOKEN`** + partner attest endpoint.  
- Auditor: evidence includes **`trust_tier_max`** across registries when present.
