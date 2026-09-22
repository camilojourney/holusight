# Task: Build MVP Demo + Sales Proposal (This Week)

**Priority:** P0 — Due by end of week  
**Created:** 2026-02-28  

---

## Goal

Have a working demo + one-pager + proposal doc ready to present to consulting clients.

---

## 5-Day Build Plan

| Day | What to build | Time | Done? |
|-----|--------------|------|-------|
| **Day 1** | Extend Holusight to index PDF/DOCX/TXT (not just code files) | 3-4 hrs | ☐ |
| **Day 2** | Streamlit chat UI over Holusight search | 3-4 hrs | ☐ |
| **Day 3** | Load 20-30 sample docs, polish the demo, test edge cases | 2-3 hrs | ☐ |
| **Day 4** | One-pager PDF + proposal doc | 2 hrs | ☐ |
| **Day 5** | Practice the pitch 3x out loud. Record yourself. | 1 hr | ☐ |

**Total: ~15 hours**

---

## Day 1: Extend Holusight for Documents

### What to change
Holusight currently only indexes code files (filtered by extension in `git_utils.py`). Extend it to handle business documents.

### New file types to support
| Format | Library | Notes |
|--------|---------|-------|
| **PDF** | `pymupdf` (fitz) or `pdfplumber` | Handles text + scanned (with OCR fallback) |
| **DOCX** | `python-docx` | Word documents |
| **PPTX** | `python-pptx` | PowerPoint slides |
| **XLSX** | `openpyxl` | Excel spreadsheets (extract cell text) |
| **TXT/MD/CSV** | Built-in | Already works for code, just remove extension filter |
| **EML/MSG** | `email` stdlib or `extract-msg` | Email files |

### Where to change
1. `src/semantic_search_mcp/git_utils.py` — Remove or expand the file extension filter
2. `src/semantic_search_mcp/chunker.py` — Add document-aware chunking (by page for PDFs, by section for DOCX)
3. `src/semantic_search_mcp/indexer.py` — Add file-type detection and route to appropriate parser
4. New: `src/semantic_search_mcp/parsers.py` — Document parsers (PDF, DOCX, PPTX, etc.)

### Dependencies to add
```toml
# pyproject.toml
pymupdf = ">=1.24"
python-docx = ">=1.1"
python-pptx = ">=0.6"
openpyxl = ">=3.1"
```

### Test
```bash
# Index a folder with mixed documents
python -m semantic_search_mcp index --repo-path /path/to/sample-docs/
python -m semantic_search_mcp search --query "What was the deadline for deliverable X?"
```

---

## Day 2: Streamlit Chat UI

### What to build
A simple chat interface that non-technical users can use.

### Features
- Chat input box at bottom
- Messages displayed in conversation format
- Each answer shows:
  - The AI response
  - Source documents (filename, page number, relevance score)
  - Expandable snippet showing the matched text
- Sidebar: select which project/folder to search
- "Index new folder" button

### Architecture
```
Streamlit app
    │
    ├── User types question
    ├── Calls Holusight search() via Python API (not MCP)
    ├── Sends top chunks to LLM (GPT-4o or Claude) for answer synthesis
    └── Displays answer + sources
```

### Key file
```
demo/
├── app.py          # Streamlit app
├── requirements.txt
└── README.md       # How to run the demo
```

### Run
```bash
cd demo && streamlit run app.py
```

---

## Day 3: Sample Data + Polish

### Get 20-30 sample documents
Options:
- Ask the client for anonymized project docs (best — demo uses THEIR data)
- Use public business document templates (contracts, SOPs, project plans)
- Create realistic fake documents for the demo

### Test these queries
- "What was the deadline for [project X]?"
- "Who is responsible for [deliverable Y]?"
- "What are the payment terms in the contract?"
- "Find all mentions of [vendor name]"
- "What was discussed in the meeting on [date]?"

### Polish
- Make sure results are relevant (tune chunk sizes if needed)
- Handle edge cases: empty results, very long documents, non-English text
- Add loading states to the UI

---

## Day 4: One-Pager + Proposal

### One-Pager (Leave-Behind PDF)

**Layout:** Single page, clean design, your branding

**Content:**

```
[LOGO] Camilo Martinez — AI Consulting

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THE PROBLEM
Your team spends 10+ hours per week searching for information 
across emails, SharePoint, and shared drives. Critical knowledge 
is buried in documents nobody can find.

THE SOLUTION
AI-powered document search that plugs into your existing 
Microsoft 365. No migration. No new tools. Just answers.

HOW IT WORKS
1. I connect to your Microsoft 365 (SharePoint, Outlook, OneDrive)
2. Your documents are indexed per project — isolated and secure
3. Your team searches in plain English and gets instant answers
   with source documents highlighted

THE RESULT
→ Find any document in under 5 seconds
→ Each project gets its own specialized AI brain
→ Automatic re-indexing when documents change
→ Your data never leaves your infrastructure

ROI
20 employees × 4 searches/day × 15 min each × $40/hr
= $16,000/month in lost productivity
Your investment: $10K setup + $1K/month
→ Pays for itself in 3 weeks

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEXT STEP
Let's run a 2-week pilot on one project. $3,000.
If it doesn't save your team time, you pay nothing.

Contact: juan@camilomartinez.co | camilomartinez.co
```

### Proposal Document (2-3 pages)

**Page 1: Executive Summary**
- The problem (their specific pain points from discovery call)
- The solution (project-level AI knowledge agents)
- Timeline: 2-3 weeks for pilot

**Page 2: Technical Approach**
- Architecture diagram (mother agent + project agents)
- Data sources connected (their M365 stack)
- Security: data stays on their infra, local embeddings
- What gets indexed, how often it refreshes

**Page 3: Pricing + Timeline**
| Phase | What | Timeline | Cost |
|-------|------|----------|------|
| Discovery | Audit workflows, identify high-value projects | Week 1 | Included |
| Pilot | Index 1 project, deploy search, train team | Week 2-3 | $3,000-5,000 |
| Scale | Add remaining projects, build custom agents | Week 4-8 | $1,000-2,000/project |
| Maintenance | Monitoring, reindexing, tuning | Ongoing | $500-1,500/month |

**Terms:** 50% upfront, 50% on delivery. Money-back guarantee on pilot.

---

## Day 5: Practice

### Do this
1. Set a timer for 10 minutes
2. Deliver the full pitch out loud (problem → demo → pricing → close)
3. Record yourself on your phone
4. Watch it back — fix awkward pauses, filler words, unclear points
5. Do it 2 more times

### Key phrases to nail
- "Your team wastes X hours searching for information"
- "I plug into what you already have — no migration needed"
- "Each project gets its own AI brain"
- "Let's start with a pilot on one project"

### Objection prep
| They say | You say |
|----------|---------|
| "We have Copilot" | "Copilot searches everything at once. I give each project focused answers from only that project's docs." |
| "Data privacy?" | "Everything runs on your infrastructure. Documents never leave your servers." |
| "Too expensive" | "Your team loses $16K/month in search time. This pays for itself in 3 weeks." |
| "We'll think about it" | "Totally fair. Want to try a free 30-min test with your actual documents? I'll index one folder right now." |

---

## Success Criteria

- [ ] Holusight indexes PDF/DOCX/TXT files
- [ ] Streamlit demo works with 20+ sample documents
- [ ] Search returns relevant results for 5+ test queries
- [ ] One-pager PDF is designed and printed
- [ ] Proposal template is ready (fill in client-specific details)
- [ ] Pitch practiced 3x and recorded
