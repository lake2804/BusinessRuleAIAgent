# ORR Workflow and Decision Notes
Document ID: ORR-WKF-012  
Status: ACTIVE  
Effective Date: 2026-03-10

## High-Level Workflow
1. Intake case from web, app, call center, or store-assisted channel.
2. Validate minimum fields: order_id, item_id, issue_type, region, request_timestamp.
3. Fetch product master, entitlement, and payment details.
4. Check policy eligibility.
5. Check regional override.
6. Evaluate evidence completeness.
7. Evaluate risk signals.
8. Determine preferred resolution.
9. Route for approval if threshold exceeded.
10. Trigger downstream payment, replacement, repair, or investigation flow.

## Resolution Selection Heuristics
- Prefer **replacement** over **refund** when inventory is available and the item is not safety-restricted.
- Prefer **refund** over **goodwill credit** when legal entitlement exists.
- Prefer **partial reimbursement** over full refund for minor cosmetic damage if the customer accepts and local law allows.
- Prefer **investigation** over immediate refund when delivery is confirmed and porch-theft waiver is unavailable.

## Ambiguity Handling
If any of the following is missing, the system should explicitly state that a final decision cannot be made:
- region
- delivered date
- issue type
- item condition
- item category
- evidence status
- payment method age for refund routing
- active policy version reference

## Output Requirements for AI
When generating a decision summary, include:
- recommended resolution
- confidence level
- cited rules
- missing inputs
- applicable override
- approval owner if escalation is required
