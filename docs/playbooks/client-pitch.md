# Playbook: Client Pitch — Questions, Objections, and Answers

> Prepare for business meetings. Every question a prospect will ask, with honest answers.

---

## The 30-Second Pitch

"I can make your team's customer-mounted documents searchable with AI in a focused two-week pilot. Point me at a read-only folder — contracts, policies, technical docs — and I'll set up a system where one team can ask questions in plain English and get precise answers with source citations. Search runs on your infrastructure; cloud answer providers are optional and customer-owned."

---

## Core Questions

### "What exactly does this do?"

You have documents — PDFs, Word docs, presentations, code files. Right now, finding information means opening files, Ctrl+F, reading pages. With CodeSight, your team opens a web chat, types a question like "What are the payment terms in the Acme contract?", and gets a direct answer with the exact source (file name, page number).

Under the hood: we index every document using two search methods — keyword matching (finds exact terms like contract numbers, dates, names) and semantic search (understands meaning, so "payment terms" also finds "billing schedule"). This hybrid approach catches what either method alone would miss.

### "How is this different from ChatGPT / just uploading to Claude?"

Three problems with uploading documents to ChatGPT or Claude:

1. **File limits.** You can upload a few files. We index entire folders — hundreds or thousands of documents.
2. **No persistence.** Each chat session starts fresh. CodeSight maintains a permanent searchable index that updates as documents change.
3. **Retrieval quality.** ChatGPT uses basic RAG. We use hybrid BM25 + vector search with Reciprocal Rank Fusion — the same approach used by enterprise search engines, but running locally.

### "How is this different from Microsoft Copilot?"

Copilot may already fit teams invested in M365. CodeSight is not an M365 replacement: it searches a focused customer-mounted folder or repository export.

CodeSight is different:
- **Scoped search.** You point it at a specific folder of documents. "Search only these 200 contracts." Copilot searches everything.
- **Cost.** The recommended starting offer is a $1,000-$2,000 two-week pilot, with optional $500-$1,000/month support. Customer infrastructure and LLM usage are separate.
- **No M365 dependency.** The pilot uses a customer-mounted folder or repository export, not a live connector.
- **Privacy.** Search and indexing run on the customer deployment. Cloud answer providers receive context only when the customer configures them.

If you already have Copilot and it's working for you, you don't need this. If you don't have Copilot, or you need scoped project search, or you can't send data to Microsoft — that's where CodeSight fits.

### "We already use SharePoint / Google Drive. Why do we need this?"

SharePoint and Google Drive are storage. They can find files by name. They can't answer "What are the payment terms across all vendor contracts?" or "Which policies mention data retention?"

CodeSight doesn't replace your storage. It sits alongside it. Mount or export the documents you need searched, and CodeSight makes them answerable.

---

## Data Privacy & Security Questions

### "Where does our data go?"

**Search and indexing run on your deployment.** The default embedding model and search index are local files. Search works without an LLM key; any cloud embedding configuration is customer-selected and should be treated as an external provider call.

**Answer synthesis: your choice.** When someone asks a question and wants a written answer (not just search results), the relevant document chunks are sent to an AI model. You choose which one:

| Option | Where data goes | Trust level |
|--------|----------------|-------------|
| Your own Claude API key | Anthropic (they don't train on API data) | High |
| Your Azure OpenAI | Your Azure tenant (data never leaves your infra) | Highest |
| Your OpenAI API key | OpenAI | High |
| Local model (Ollama) | Nowhere. Runs on the machine. | Maximum |

**We are never in the middle.** You own the API key. You pick the provider. We don't see your data.

### "How do we know you're not taking our data?"

The software is open source — you can read every line of code. The architecture is designed so:

1. Documents are read from disk and indexed into local files. No network call.
2. Search runs against local indexes. No network call.
3. The ONLY external call is when `ask()` sends document chunks to the LLM you configured. That call goes directly from your machine to the AI provider. We don't proxy it, we don't log it, we don't see it.
4. If you use local embeddings and Ollama, runtime retrieval and answer synthesis can remain on the deployment. Cloud providers require their own network access.

You can verify this by running the tool with network monitoring. Search works with airplane mode on.

### "Can we run this completely offline / air-gapped?"

Yes, after the image, embedding model, and Ollama model have been prepared while connected. Search is available without an LLM; fully local answers require Ollama. Deploy on an air-gapped server with:
- The Python package (pre-downloaded)
- The embedding model (pre-downloaded, ~270MB)
- The LLM model (pre-downloaded via Ollama, ~4-8GB)

### "What about access controls? Can everyone see everything?"

Currently, everyone with access to the web UI can search everything in the indexed folder. For most consulting engagements (one team, one project), this is fine.

For larger deployments where different teams need different access, this is on the roadmap (v0.7). In the meantime, you can run separate CodeSight instances per team/project.

---

## Cost Questions

### "How much does this cost?"

| Component | Recommended framing |
|-----------|---------------------|
| CodeSight software | Open source engine |
| Search & indexing | Runs locally; no Holusight usage fee |
| Ask / LLM answers | Customer’s Claude / Azure / OpenAI / Ollama account |
| 2-week pilot | **$1,000–$2,000** starting range |
| Optional support | **$500–$1,000 / month** |

Do not quote unverified Copilot/Glean monthly totals or per-question token costs unless you have a current, dated source. Authoritative offer: `business/pilot-offer.md`.

### "Why should we pay for consulting if the software is free?"

The software is the engine. The value is:
1. **Speed.** We deploy a working system in hours, not weeks.
2. **Configuration.** Picking the right LLM backend, embedding model, and deployment for your security requirements.
3. **Customization.** Tuning for your specific document types and query patterns.
4. **Training.** Teaching your team how to get the best answers.
5. **Ongoing support.** Document sync, reindexing schedules, model upgrades.

### "What's cheaper — this or Azure AI Search?"

| | CodeSight | Azure AI Search + Azure OpenAI |
|--|-----------|-------------------------------|
| Monthly infrastructure | Typically $50-200 for a small customer VM + disk | Separate Azure estimate |
| Setup time | Hours | Weeks |
| Developer needed | No | Yes (Azure experience required) |
| Vendor lock-in | None | Azure |

---

## Technical Questions

### "How does the search actually work?"

Two search methods run in parallel on every query:

1. **BM25 keyword search** (SQLite FTS5) — finds exact matches. If you search for "section 4.2" or "Acme Corp", it finds those exact strings. Fast and precise.

2. **Vector semantic search** (LanceDB) — understands meaning. If you search for "payment deadline", it also finds "billing due date" and "invoice terms" even though the words are different.

Results from both are merged using **Reciprocal Rank Fusion (RRF)** — a proven algorithm that combines rankings without needing to calibrate scores between different search methods.

This hybrid approach beats vector-only search (which most AI search tools use) because it catches exact keyword matches that vectors miss.

### "What about the embedding model? Is local good enough?"

For searching hundreds to thousands of documents (typical consulting scope), local embeddings are competitive with cloud APIs:

| | Local (nomic-embed-text-v1.5) | Cloud (OpenAI text-embedding-3-large) |
|--|-------------------------------|--------------------------------------|
| Quality | Good (768 dims, 8K context) | Best (3072 dims, 8K context) |
| Cost per index (500 docs) | Free | ~$5 |
| Cost per search | Free | ~$0.0001 |
| Data leaves machine | No | Yes |
| Internet needed | No | Yes |

Our hybrid search (BM25 + vector) compensates for the smaller embedding model. BM25 catches what the local model might miss.

If you want maximum quality and don't mind data going to an API, we can switch to cloud embeddings. It's a config change.

### "What documents can it handle?"

| Format | Support |
|--------|---------|
| PDF (.pdf) | Full text extraction, page-level metadata |
| Word (.docx) | Full text with heading/section detection |
| PowerPoint (.pptx) | Text per slide with title detection |
| Code (.py, .js, .ts, .go, etc.) | Language-aware chunking (10 languages) |
| Text (.md, .txt, .csv) | Full text with sliding window chunking |
| Excel (.xlsx) | Planned |
| Email (.eml, .msg) | Planned |
| Scanned PDFs (image-only) | Not yet (OCR planned) |

### "How do documents stay updated?"

When documents change, re-run indexing. Only changed content gets re-embedded (content hash comparison). Unchanged documents are skipped entirely — a re-index of 500 docs where 10 changed takes seconds, not minutes.

For automated updates: set up a cron job or scheduled task to re-index periodically. Enterprise connector (SharePoint sync) is on the roadmap.

### "How many users can it handle?"

| Scope | Deployment | LLM backend | Status |
|-------|------------|-------------|--------|
| One team | Docker or VM + FastAPI + shared API key | Customer-selected provider | Supported within pilot scope |
| Larger deployment | Separate design | Depends on deployment | Not claimed |

No concurrent-user or uptime target is claimed. Larger deployments require separate scoping; this release is a single-team pilot shape.

---

## Objections

### "We'll just build this ourselves with LangChain."

You could. It'll take your developer 2-4 weeks to build what CodeSight does out of the box, plus ongoing maintenance. And they'll likely build vector-only search (no hybrid BM25+RRF), which means worse results for keyword queries.

The consulting engagement gets you a working system in hours and lets your developers focus on your core product.

### "Isn't this just RAG? Everyone has RAG now."

RAG is the category. The quality difference is in the retrieval. Most RAG implementations use basic vector search (embed, store, retrieve). CodeSight uses hybrid BM25 + vector + RRF fusion, which is what production search engines use. The "R" in RAG is the hard part — and that's what we've optimized.

### "What if we outgrow this?"

CodeSight is designed for scoped document collections (hundreds to thousands of documents). If you grow to millions of documents across your entire organization, you'll want an enterprise solution like Glean or Azure AI Search.

But most companies don't need that. They need specific project folders searchable. And if you do outgrow it, the consulting engagement gives you a clear picture of what you need next.

### "Can't we just use Claude's Projects feature?"

Claude Projects lets you upload files and chat with them. It works for small collections (maybe 20-30 documents). Limitations:
- File size and count limits
- No persistent index (re-uploads needed)
- No hybrid search (vector-only)
- $20/user/month per Pro seat
- Data goes to Anthropic

CodeSight handles hundreds to thousands of documents, maintains a persistent index, and search runs locally.

---

## Demo Script

### Setup (do before the meeting)

```bash
# Get their sample documents beforehand (even 10-20 is enough for demo)
pip install codesight
python -m codesight index /path/to/their-sample-docs
pip install streamlit
python -m codesight demo
```

### During the meeting

1. Open the web chat UI
2. "Let me show you something. These are your documents. Ask me any question about them."
3. Let THEM type the first question — something they know the answer to
4. Show the answer with source citations
5. Click the source to show exactly where the answer came from
6. Ask something harder — a cross-document question
7. Show that search works with no internet (turn off WiFi if you want to be dramatic)

### Key talking points during demo

- "This indexed your entire folder in [X] seconds"
- "Search is running on this laptop right now. No cloud, no API, no data leaving"
- "The answer came from [file name], page [X] — you can verify it"
- "If you update a document and re-index, only the changed parts are re-processed"
