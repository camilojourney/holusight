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
2. "What systems do you use?" (M365, Google, Confluence — determines connectors)
3. "How many people would use this?" (size the deal)
4. "Have you tried anything else?" (understand why competitors failed)
5. "What would solving this be worth to your company?" (anchor value, not cost)

## Proposal Workflow

1. After discovery, run the **proposal-writer** agent with client context
2. Review and customize the output
3. Always include: one-pager + full proposal + pilot pricing
4. Follow up within 48 hours of sending

## Pricing Anchors

- Reference `specs/005-money-model.md` for current pricing
- Always lead with ROI: "Your team loses $X/month in search time"
- Pilot is the entry point: $3-5K, 2 weeks, one project, money-back guarantee
