# Consulting Proposal: Enterprise Knowledge Platform

**Priority:** P0 — Proposal due this week  
**Created:** 2026-02-28  
**Client context:** Company using Microsoft 365 / Azure, multiple projects, wants project-level AI agents

---

## What You're Selling

**"I plug into your existing workflows and give every project its own AI brain."**

Not coding tools. Not chatbots. A **knowledge indexing system** that:
- Connects to their Microsoft 365 (emails, SharePoint, OneDrive, OneNote, Teams)
- Indexes documents per project folder
- Each project gets a **specialized agent** that knows only that project
- A **mother agent** sees across all projects for cross-project questions
- Updates automatically when documents change

---

## The Architecture You'd Deploy

```
                    ┌─────────────────┐
                    │  Mother Agent    │
                    │  (all projects)  │
                    └────────┬────────┘
                             │ asks
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │ Project A │   │ Project B │   │ Project C │
       │  Agent    │   │  Agent    │   │  Agent    │
       └─────┬────┘   └─────┬────┘   └─────┬────┘
             │               │               │
       ┌─────▼────┐   ┌─────▼────┐   ┌─────▼────┐
       │ Index A   │   │ Index B   │   │ Index C   │
       │ (docs,    │   │ (docs,    │   │ (docs,    │
       │  emails,  │   │  emails,  │   │  emails,  │
       │  notes)   │   │  notes)   │   │  notes)   │
       └──────────┘   └──────────┘   └──────────┘
```

**Why specialized agents > one big agent:**
- Each agent has focused context (~10K tokens) instead of drowning in 500K
- Better answers because the agent isn't confused by unrelated projects
- Mother agent routes questions: "Which project handles vendor X?" → asks Project B agent
- Scales: new project = new folder + new index + new agent. 5 minutes.

---

## Data Sources to Connect (Microsoft 365)

| Source | What it gives you | How to connect |
|--------|------------------|----------------|
| **SharePoint / OneDrive** | Project folders, documents, SOPs | Microsoft Graph API (`/drives`, `/items`) |
| **Outlook / Exchange** | Emails, attachments per project | Microsoft Graph API (`/messages`, `/attachments`) |
| **OneNote** | Meeting notes, project notes | Microsoft Graph API (`/onenote/pages`) |
| **Teams** | Channel messages, shared files | Microsoft Graph API (`/teams/channels/messages`) |
| **Planner / To Do** | Tasks, assignments | Microsoft Graph API (`/planner/tasks`) |

**All through ONE API:** Microsoft Graph. One OAuth token, access to everything.

---

## Tech Stack for the Proposal

| Component | Tool | Why |
|-----------|------|-----|
| **Document ingestion** | Microsoft Graph API + Python | Pull docs/emails from M365 |
| **PDF/DOCX parsing** | `unstructured` or `pymupdf` | Extract text from any file format |
| **Embeddings** | `sentence-transformers` (local) or OpenAI `text-embedding-3-small` | Privacy: local. Speed: OpenAI. |
| **Vector store** | LanceDB (from Holusight) | Zero infra, file-based, per-project isolation |
| **BM25 search** | SQLite FTS5 (from Holusight) | Keyword search for exact terms (contract numbers, names) |
| **Agent framework** | LangGraph or CrewAI | Multi-agent orchestration (project agents + mother agent) |
| **UI** | Simple chat interface (Streamlit or Next.js) | Non-technical users need a web UI, not CLI |
| **Sync/refresh** | Microsoft Graph webhooks or cron | Auto-reindex when documents change |

**Holusight's core (embeddings + LanceDB + FTS5 + hybrid search) IS the retrieval engine.** You're wrapping it with M365 connectors and a multi-agent layer.

---

## What You Present This Week

### Slide 1: The Problem
"Your team wastes 2+ hours/day searching for information across emails, SharePoint, and OneNote. When someone asks 'What did we agree with vendor X?' — nobody knows where to look."

### Slide 2: The Solution
"I build a knowledge layer that indexes everything per project. Ask a question in plain English, get the answer with the source document."

### Slide 3: How It Works
- Show the architecture diagram above
- "Each project gets its own AI agent that knows only that project's documents"
- "A master agent connects all projects for cross-cutting questions"

### Slide 4: What Gets Indexed
- Emails + attachments
- SharePoint documents
- OneNote pages
- Teams conversations
- Automatic re-indexing when things change

### Slide 5: Demo (if possible)
- Index a sample folder with 20-30 docs
- Show a chat asking "What's the deadline for deliverable X?"
- Show it pulling the answer from a specific email/document

### Slide 6: Pricing
| Tier | What they get | Price |
|------|--------------|-------|
| **Setup** | Audit workflows, connect M365, index initial projects | $5,000-10,000 |
| **Per project** | New project agent + index + training | $1,000-2,000 |
| **Monthly maintenance** | Monitoring, reindexing, agent tuning | $500-1,500/mo |
| **Custom agents** | Specialized workflows (e.g., contract analysis) | $2,000-5,000 each |

*(Adjust based on company size — these are SMB/mid-market rates)*

---

## Competitive Landscape (Know This Before the Meeting)

| Competitor | What they do | Your advantage |
|-----------|-------------|----------------|
| **Microsoft Copilot** | Built-in M365 AI | $30/user/month, generic, no project isolation, no custom agents |
| **Glean** | Enterprise search | $50K+/year, enterprise-only, overkill for SMBs |
| **Guru / Notion AI** | Knowledge base search | Requires migrating docs to their platform |
| **Custom RAG consultants** | What you're doing | You have a working tool (Holusight), not starting from scratch |

**Your pitch:** "Copilot gives everyone the same generic AI. I give each project a specialized brain that actually understands YOUR workflows — and it costs a fraction of Glean."

---

## What to Build Before the Proposal

### Must-have (this week):
1. **M365 connector script** — Python script that pulls documents from a SharePoint folder via Graph API
2. **Document parser** — Extract text from PDF/DOCX/PPTX (use `unstructured` library)
3. **Extend Holusight** to index non-code files (it currently filters by code extensions)
4. **Simple demo** — Index 20 docs, show search working via CLI or basic Streamlit chat

### Nice-to-have (after proposal is accepted):
5. Web UI chat interface
6. Multi-agent routing (mother → project agents)
7. Webhook-based auto-reindexing
8. Access control (who can query which project)

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| M365 OAuth is complex to set up | Use Azure AD app registration — well-documented, do it once |
| Client data privacy concerns | Local embeddings (sentence-transformers), data stays on their infra or yours |
| "Why not just use Copilot?" | Demo side-by-side: your project-specific answers vs Copilot's generic ones |
| Scaling to thousands of docs | LanceDB handles millions of vectors — not a problem |
| Documents in Spanish + English | Multilingual embeddings exist (`paraphrase-multilingual-MiniLM-L12-v2`) |

---

## Next Steps for Juan

- [ ] Build the M365 connector (Graph API + document pull)
- [ ] Extend Holusight to accept non-code files (PDF, DOCX, PPTX, emails)
- [ ] Create a 5-minute demo with sample documents
- [ ] Draft the proposal deck (use slides above as skeleton)
- [ ] Research the client's specific M365 setup (which apps, how many projects)
- [ ] Price it based on their size and number of projects
