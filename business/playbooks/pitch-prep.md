# Pitch Prep — What to Know Before Every Meeting

> Read this before any client meeting. Covers the 30-second pitch, every question they'll ask, and how to answer honestly.
> Full technical Q&A reference: `codesight/docs/playbooks/client-pitch.md`

---

## The 30-Second Pitch

"I can make your company's documents searchable with AI in a day. Point me at a folder — contracts, policies, technical docs — and I'll set up a system where anyone on your team can ask questions in plain English and get precise answers with page-level citations. Search runs entirely on your machine. No data leaves your network."

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
| CodeSight monthly cost (50 users) | $50-200 |
| Copilot monthly cost (50 users) | $1,500 |
| Glean monthly cost (50 users) | $2,250+ |
| Index speed (500 docs) | ~30 seconds |
| Pilot price | $7,500-10,000 |
| Pilot duration | 2 weeks |

---

## Questions They Will Ask

### About the product

**"What exactly does this do?"**
Your team opens a web chat, types a question, gets a direct answer with the source file and page number. Under the hood, we use two search methods — keyword (finds exact terms) and semantic (understands meaning). This hybrid catches what either alone would miss.

**"How is this different from Copilot?"**
Copilot searches everything across all of M365 — $30/user/month. CodeSight is scoped: "search only these 200 contracts." Cost: $50-200/month total. No M365 dependency. Privacy: search is 100% local.

**"Can't we just upload to ChatGPT?"**
File limits (20-30 docs max). No persistent index. No hybrid search. $20/user/month. Data goes to OpenAI/Anthropic. CodeSight handles thousands of documents, persistent index, local search.

**"We already have SharePoint search."**
SharePoint finds files by name. It can't answer "What are the payment terms across all vendor contracts?" CodeSight answers questions, not just finds files.

### About privacy

**"Where does our data go?"**
Search and indexing: nowhere. Runs on the machine. Answer synthesis: your choice — cloud API (you own the key) or 100% local with Ollama. We are never in the middle.

**"Can we run this completely offline?"**
Yes. Local embedding model + Ollama. Zero internet after initial setup. Works in airplane mode.

**"How do we verify?"**
Open source. You can read every line. Search works with WiFi off — demonstrate this in the meeting.

### About cost

**"How much?"**
Software: free (open source). Search: free (local). AI answers: ~$0.01-0.03 per question via API, or free with local LLM. Consulting: $7,500-10K pilot (one project, two weeks), $3-5K per additional project, $1-2K/mo maintenance.

**"Why pay for consulting if the software is free?"**
Speed (deployed in hours, not weeks), configuration (right LLM/embedding for your requirements), customization (tuned for your document types), training, ongoing support.

### About scaling

**"How many users can it handle?"**
1-10 users: laptop. 20-50: single VM with cloud API. 50+: Docker deployment (available soon). Bottleneck is LLM answers, not search.

**"What documents can it handle?"**
PDF, Word, PowerPoint, code (10 languages), text files. Excel and email planned. Scanned PDFs (OCR) planned.

---

## Closing the Meeting

**Always end with a specific next step, not "we'll follow up."**

Best closing lines:
1. "Want to try a free 30-minute test with your actual documents? I'll index a folder right now."
2. "Pick one project. I'll have it searchable in a week. $[X], money-back guarantee."
3. "I'll send the proposal tomorrow. When works to discuss it — Thursday or Friday?"

**Never say:**
- "Let me know what you think" (passive, no commitment)
- "We can do anything you need" (no focus, sounds desperate)
- "It depends" without immediately following with specifics
