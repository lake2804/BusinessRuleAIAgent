# ORR Regional Overrides Register
Document ID: ORR-REG-OVR-007  
Status: ACTIVE  
Effective Date: 2026-03-15  
Owner: Regional Compliance Office

## Purpose
This document defines region-specific overrides that supersede the global policy manual where legally required or operationally approved.

## Rule Priority
1. Active legal/regulatory override
2. Active regional override
3. Global policy manual v1.4
4. Historical/archived versions for reference only

## Regional Overrides

### EU
- Cooling-off withdrawal window: **14 calendar days** from delivery for eligible distance sales, even if the customer is not a premium member.
- For low-value claims below **EUR 40**, a package photo is recommended but not mandatory if carrier scan history shows damage.
- Outbound shipping must be refunded for legal withdrawal where applicable.
- Goodwill credit cannot be forced in place of refund for legal withdrawal.

### UK
- Cooling-off withdrawal window: **14 calendar days** from delivery for qualifying remote sales.
- For marketplace-serviced orders, merchant investigation may extend decision SLA by up to **3 business days** if evidence is incomplete.
- Bank-transfer reimbursement above **GBP 250** requires Finance + Compliance dual approval.

### Singapore
- Open-box electronics remain return-eligible within **7 calendar days** if all accessories and original packaging are present.
- Missing accessory cases may be resolved with partial reimbursement instead of full return if the missing part replacement cost is below **SGD 50**.
- For express shipments, carrier-lost cases may be refunded after **4 calendar days** without delivery event.

### Vietnam
- Household electronics with manufacturer seal broken are normally **not returnable for convenience reasons**, but defective-on-arrival claims remain eligible.
- Cash-on-delivery reimbursement must default to bank transfer or e-wallet; cash payout is prohibited.
- Claims with item value above **VND 10,000,000** require supervisor approval even when evidence is complete.
- Porch-theft waiver is **not allowed**; delivered-not-received always enters investigation.

### UAE
- Replacement is preferred over refund for damaged luxury items above **AED 1,500** unless stock is unavailable.
- Bank account name mismatch tolerance is reduced from **85% to 70%** when customer has verified KYC profile.
- Friday received time counts as next business day for standard SLA measurement.

## Known Edge Cases
- If a region is not listed here, the global policy applies.
- If the same region has multiple documents, the latest ACTIVE document prevails.
- If legal counsel issues a one-time temporary notice, that notice overrides both this register and the global policy for its valid period.

## Test Notes for RAG Evaluation
- This file intentionally contains threshold changes, legal overrides, and region-scoped conflicts.
- AI responses should mention the region and cite both the global and override sources when explaining why an override applies.
