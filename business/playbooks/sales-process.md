# Sales Process — Lead to Close

## Pipeline Stages

| Stage | What happens | Exit criteria |
|-------|-------------|---------------|
| **Lead** | Initial contact, pain identified | They have a real search/knowledge problem |
| **Qualified** | Discovery call done, budget confirmed | Know their stack, size, pain, budget range |
| **Proposal** | Proposal sent | Proposal + one-pager delivered |
| **Negotiation** | Pricing/scope discussion | Terms agreed |
| **Closed Won** | Signed | Payment received, delivery starts |
| **Closed Lost** | Didn't close | Reason documented in pipeline/closed.md |

## Discovery Call Script

1. "How does your team find information today?" (surface the pain)
2. "Where can the pilot's read-only document folder or repository export live?" (customer VM, on-prem server, or customer cloud)
3. "How many people would use this?" (size the deal)
4. "Have you tried anything else?" (understand why competitors failed)
5. "What would solving this be worth to your company?" (anchor value, not cost)

## Proposal Workflow

1. After discovery, run the **proposal-writer** agent with client context
2. Review and customize the output
3. Always include: one-pager + full proposal + pilot pricing
4. Follow up within 48 hours of sending

## Pricing Anchors

- Reference `business/pilot-offer.md` for the current recommended offer
- Use the client's own discovery numbers; do not invent ROI claims
- Pilot is the entry point: $1,000-$2,000, two weeks, one team; optional support is $500-$1,000/month
