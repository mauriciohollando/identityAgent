# Identity registry model (accountability for `agent_id`)

This describes the **reference registry** in `src/identity_registry/`. It is not a global truth network—you operate it (or fork it) and decide policy.

## What “registered” means for the Trust Auditor

The auditor calls::

    GET {registry}/agents/{agent_id}/status

and treats **`registered: true`** as passing that registry’s bar. The JSON may include richer fields for your own dashboards; the auditor’s quorum logic only needs `registered` unless you extend `audit_regimes/identity.py`.

In this implementation, **`registered`** is computed as:

1. Row exists and **`status` is `active`**, and  
2. If **`REGISTRY_REQUIRE_KYC=1`**: `kyc_verified` must be true.  
3. If **`REGISTRY_REQUIRE_SIGNING_KEY=1`**: at least one **non-revoked** signing key must exist.

`suspended` or `revoked` agents get `registered: false`.

## Trust tiers (go-to-market ladder)

See **[GO_TO_MARKET_IDENTITY.md](GO_TO_MARKET_IDENTITY.md)** for positioning. Summary:

| `trust_tier` | Meaning |
|----------------|---------|
| `registered` | Self-serve listing; mechanical checks only. |
| `operator_verified` | Your team completed an internal attestation (`POST /v1/admin/agents/{id}/attest/operator`). |
| `partner_attested` | A B2B partner asserted the agent (`POST /v1/partner/v1/agents/{id}/attest`). |

Status JSON also exposes `attested_at_unix`, `attestor`, `partner_id`, `partner_ref` when set. The Trust Auditor aggregates **`trust_tier_max`** across registries into evidence.

## Lifecycle

| Status | Meaning |
|--------|---------|
| `active` | May receive traffic; subject to KYC/key rules above. |
| `suspended` | Temporarily not trustworthy (`registered` false). |
| `revoked` | Permanently off-boarded (`registered` false). |

## Onboarding (your obligations)

1. **Vet the operator** (org membership, contract, lightweight KYC—your policy).  
2. **Register** the agent (`POST /v1/agents`) with `operator_name`, `operator_contact`, optional `org_id`.  
3. **Attach a signing key** (`POST /v1/agents/{id}/keys`) so others can verify attestations (optional unless `REGISTRY_REQUIRE_SIGNING_KEY=1`).  
4. Set **`kyc_verified`** when your process completes (patch via re-register flow or direct DB—see API).

## Key rotation

1. `POST /v1/agents/{id}/keys` with the new `public_key` (PEM or raw base64; stored as text).  
2. `POST /v1/agents/{id}/keys/{key_id}/revoke` on the old key after callers have migrated.  

Keep overlap during rotation if clients cache keys.

## Revocation and bad actors

- **`POST /v1/agents/{id}/revoke`** — terminal; set reason in body for audit trail in `metadata` / logs.  
- **`POST /v1/agents/{id}/suspend`** — reversible while you investigate.

## Multi-registry + quorum

Run several registry bases in **`IDENTITY_REGISTRY_URLS`** and set **`IDENTITY_REGISTRY_QUORUM`** to `all`, `any`, or `majority` on the auditor.

## Auth

- **`REGISTRY_SERVICE_API_KEY`**: if set, required on most write routes and on `GET /agents/.../status` (use **`IDENTITY_REGISTRY_BEARER_TOKEN`** on the auditor).
- **`REGISTRY_ADMIN_API_KEY`**: Bearer token for **`POST /v1/admin/agents/{id}/attest/operator`** only.
- **`PARTNER_ATTESTATION_TOKEN`**: sent as header **`X-Partner-Attestation-Token`** on **`POST /v1/partner/v1/agents/{id}/attest`** (no registry bearer required on that route).
