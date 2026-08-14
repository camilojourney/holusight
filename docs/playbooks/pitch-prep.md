# Pitch Prep — What to Know Before Every Meeting

> Read this before any client meeting. Covers the 30-second pitch, every question they'll ask, and how to answer honestly.
> Full technical Q&A reference: `docs/playbooks/client-pitch.md`

---

## The 30-Second Pitch

"I can make your team's customer-mounted documents searchable with AI in a focused two-week pilot. Point me at a read-only folder — contracts, policies, technical docs — and I'll set up a system where one team can ask questions in plain English and get precise answers with source citations. Search runs on your infrastructure; cloud answer providers are optional and customer-owned."

---

## Before the Meeting Checklist

- [ ] Get 10-20 sample documents from the client (or prepare realistic examples)
- [ ] Index them: `python -m codesight index /path/to/docs`
- [ ] Test 5+ questions to make sure answers are good
- [ ] Launch demo: `python -m codesight demo`
- [ ] Prepare ROI numbers: team size × searches/day × 15 min × hourly rate
- [ ] Have one-pager printed or PDF ready
- [ ] Know their stack (M365? Google? Confluence?)

---

## Key Numbers to Memorize

| Metric | Number |
|--------|--------|
| Time workers spend searching | 20%+ of work week (McKinsey) |
| Average search time per query | 15-30 minutes |
| CodeSight search time | < 5 seconds |
| Customer infrastructure | Typically $50-200/month for a small VM + disk |
| Copilot monthly cost (50 users) | $1,500 |
| Glean monthly cost (50 users) | $2,250+ |
| Index speed (500 docs) | ~30 seconds |
| Pilot price | $1,000-$2,000 |
| Pilot duration | 2 weeks |

---

## Questions They Will Ask

### About the product

**"What exactly does this do?"**
Your team opens a web chat, types a question, gets a direct answer with the source file and page number. Under the hood, we use two search methods — keyword (finds exact terms) and semantic (understands meaning). This hybrid catches what either alone would miss.

**"How is this different from Copilot?"**
CodeSight is not an M365 replacement. It searches a focused customer-mounted folder or repository export. The recommended starting offer is a $1,000-$2,000 two-week pilot, with optional $500-$1,000/month support; customer infrastructure and LLM usage are separate.

**"Can't we just upload to ChatGPT?"**
File limits (20-30 docs max). No persistent index. No hybrid search. $20/user/month. Data goes to OpenAI/Anthropic. CodeSight handles thousands of documents, persistent index, local search.

**"We already have SharePoint search."**
SharePoint finds files by name. It can't answer "What are the payment terms across all vendor contracts?" CodeSight answers questions, not just finds files.

### About privacy

**"Where does our data go?"**
Search and indexing run on the customer deployment. Answer synthesis is optional: a customer-owned cloud API or Ollama for local synthesis. We are never in the middle.

**"Can we run this completely offline?"**
Yes, when the local embedding model and Ollama model have been prepared in advance. Search is available without an LLM; fully local answers require Ollama.

**"How do we verify?"**
Open source. You can read every line. Search works with WiFi off — demonstrate this in the meeting.

### About cost

**"How much?"**
Software: free (open source). Search: local. AI answers use the customer's configured provider. Consulting: $1,000-$2,000 pilot (one team, two weeks), with optional $500-$1,000/month support. See `business/pilot-offer.md` for the authoritative offer.

**"Why pay for consulting if the software is free?"**
Speed (deployed in hours, not weeks), configuration (right LLM/embedding for your requirements), customization (tuned for your document types), training, ongoing support.

### About scaling

**"How many users can it handle?"**
This release is scoped to one team on a single Docker or VM deployment. It does not claim a concurrent-user or uptime target; larger deployments require separate scoping.

**"What documents can it handle?"**
PDF, Word, PowerPoint, code (10 languages), text files. Excel and email planned. Scanned PDFs (OCR) planned.

---

## Closing the Meeting

**Always end with a specific next step, not "we'll follow up."**

Best closing lines:
1. "Want to try a free 30-minute test with your actual documents? I'll index a folder right now."
2. "Pick one project. We'll run a focused two-week pilot for $1,000-$2,000 and review the agreed acceptance metrics."
3. "I'll send the proposal tomorrow. When works to discuss it — Thursday or Friday?"

**Never say:**
- "Let me know what you think" (passive, no commitment)
- "We can do anything you need" (no focus, sounds desperate)
- "It depends" without immediately following with specifics
