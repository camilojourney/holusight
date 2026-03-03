# Presentation Deck — Slide-by-Slide Script

> Use this as the outline for your slides (Keynote, Google Slides, or Canva).
> Each section = one slide. Speaker notes included.

---

## Slide 1: Title

**On screen:**
> **Camilo Martinez — AI Consulting**
> Make your documents searchable with AI in a day.

**Say:** Nothing. Let them read it. Pause 3 seconds, then move on.

---

## Slide 2: The Problem

**On screen:**
> Your team wastes [X] hours per week looking for information.
>
> - "What did we agree with vendor X?" — nobody knows where to look
> - "Where's the latest version of the SOP?" — it's in someone's email
> - "What are the contract terms?" — buried in a PDF from 2023
>
> **Cost: $[X]/month in lost productivity**

**Say:** "I talk to a lot of teams your size. The number one complaint is always the same — finding information takes too long. It's not that the documents don't exist. It's that nobody can find them when they need them. And when [key person] is out, the whole team is stuck."

---

## Slide 3: The Solution

**On screen:**
> AI-powered document search that plugs into what you already have.
>
> Ask a question in plain English → get the answer with the source document.
>
> [Screenshot of the Streamlit chat UI with a real answer]

**Say:** "I don't replace your SharePoint, your Drive, or your email. I make them searchable. Your team opens a web chat, types a question like they'd ask a colleague, and gets the exact answer — with the file name and page number."

---

## Slide 4: How It Works

**On screen:**
> ```
> Your documents (PDF, Word, PowerPoint)
>          │
>          ▼
> CodeSight indexes everything
> (keyword + semantic search)
>          │
>          ▼
> Web chat: ask questions in plain English
>          │
>          ▼
> Precise answers with source citations
> ```

**Say:** "Two search methods run on every question. Keyword search catches exact matches — contract numbers, names, dates. Semantic search catches meaning — so 'payment deadline' also finds 'billing due date.' This hybrid approach is what enterprise search engines use. We run it on your machine."

---

## Slide 5: Data Privacy

**On screen:**
> **Your data never leaves your network.**
>
> | What | Where it runs |
> |------|--------------|
> | Document indexing | Your machine |
> | Search | Your machine |
> | AI answers | Your choice: cloud API or 100% local |
>
> Open source — audit every line of code.

**Say:** "This is usually the first question I get, so let me address it upfront. Search and indexing run entirely on your infrastructure. No internet connection needed. The only time data goes anywhere is when you want an AI-generated answer — and you choose where: your Azure tenant, a cloud API, or a completely local model with zero network activity. I'm never in the middle."

---

## Slide 6: Live Demo

**On screen:**
> [Live demo — pre-indexed with their sample documents or realistic examples]

**Say:** "Let me show you. These are [your documents / documents like yours]. Ask me any question."

**Do:**
1. Let THEM type the first question — something they know the answer to
2. Show the answer with source citation
3. Click the source to show exactly where it came from
4. Ask something harder — a cross-document question
5. Show search works offline (turn off WiFi if dramatic)

**Key lines during demo:**
- "This indexed your entire folder in [X] seconds"
- "Search is running on this laptop. No cloud, no API"
- "The answer came from [file], page [X] — you can verify it"

---

## Slide 7: What You Get

**On screen:**
> | Phase | What | Timeline |
> |-------|------|----------|
> | **Pilot** | 1 project indexed, web chat, training | 2 weeks |
> | **Scale** | Remaining projects, full team training | 2-4 weeks |
> | **Maintain** | Monitoring, reindexing, support | Ongoing |

**Say:** "We start small. One project, two weeks, [X] dollars. I index your documents, deploy the web chat, and train your team. If it doesn't save time, you don't pay. After the pilot, we scale to other projects at [X] per project."

---

## Slide 8: Cost Comparison

**On screen:**
> | Solution | Monthly cost (50 people) | Setup time |
> |----------|-------------------------|-----------|
> | Microsoft Copilot | $1,500/mo | Weeks |
> | Glean | $2,250+/mo | Months |
> | Azure AI Search (DIY) | $500-2,000/mo | Weeks + developer |
> | **CodeSight** | **$50-200/mo** | **Hours** |

**Say:** "Copilot is $30 per user per month and searches everything — no project isolation. Glean starts at $45 per user and is built for Fortune 500. CodeSight costs a fraction and is scoped to exactly the documents you need searchable."

---

## Slide 9: Why Me

**On screen:**
> 1. Working product — you just saw the demo, not a pitch deck
> 2. Hybrid search — keyword + semantic + reranking, not just vector-only like competitors
> 3. Your data stays on your infrastructure — search is 100% local
> 4. Open source — no lock-in, no vendor dependency
> 5. Built to grow: today it searches folders, next it connects to email + SharePoint + Teams

**Say:** "I'm not selling you vaporware. You just saw it work with [your/realistic] documents. I can have this running for your team in days. And here's the roadmap: today we start with your documents in a folder. Next phase, we can connect it to your email, your SharePoint, your Teams — all searchable from one chat. Each phase builds on the last. You're not buying a dead-end tool, you're starting a platform."

---

## Slide 10: Next Step

**On screen:**
> **Let's start with a pilot.**
>
> 1 project. 2 weeks. $[7,500-10,000].
> Money-back guarantee.
>
> [email] | [phone]

**Say:** "The lowest-risk way to try this: pick one project, give me the documents, and I'll have it running in a week. Your team uses it for a week. If it doesn't save them time, you pay nothing. When can we start?"

---

## Objection Prep — Know These Cold

| They say | You say |
|----------|---------|
| "We have Copilot" | "Copilot searches everything at once — $30/user/month. This gives each project focused search for $50-200/month total." |
| "We'll build it ourselves" | "Your developer will spend 2-4 weeks building what's running here today. And they'll build vector-only search — no hybrid, worse results." |
| "Data privacy concerns" | "Search runs on your machine. You just saw me demo it with WiFi off. Open source — audit every line." |
| "Too expensive" | "Your team loses $[X]/month searching. This pays for itself in [X] weeks." |
| "We'll think about it" | "Totally fair. Want to try a free 30-minute test with your actual documents? I'll index a folder right now." |
| "Isn't this just RAG?" | "RAG is the category. Most implementations use basic vector search. We use hybrid BM25 + vector + RRF — that's what production search engines use. The retrieval is the hard part." |
| "What if we outgrow it?" | "This is built for 500-5K documents per project. If you grow to millions across the whole org, you'll want Glean. But most teams don't need that — and this engagement tells you exactly what you'd need next." |
| "Can't we just use Claude Projects?" | "Claude Projects handles 20-30 files, no persistent index, $20/user/month, data goes to Anthropic. This handles thousands of documents, local search, persistent index." |
| "What happens after the pilot?" | "If it works, we scale: more projects, connect email and SharePoint, multi-department rollout. Each phase has a clear price. You're never locked in — it's open source." |
