# Spec: Infrastructure & Data Connectors

## 1. Data Sources & Connectors

### Microsoft Graph API (Primary)

The primary ingestion point for M365-based enterprises.

#### Required Permissions (OAuth Scopes)

| Scope | Purpose |
|-------|---------|
| `Mail.Read` | Outlook email threads |
| `Mail.ReadBasic` | Email metadata (lighter permission) |
| `Chat.Read` | Teams messages |
| `Files.Read.All` | SharePoint and OneDrive files |
| `User.Read.All` | Map data to employees/teams |
| `Group.Read.All` | Resolve security group memberships |
| `Sites.Read.All` | SharePoint site permissions |

#### Delta Sync Endpoints

| Source | Endpoint | Checkpoint |
|--------|----------|-----------|
| Outlook messages | `GET /users/{id}/messages/delta` | `deltaLink` token |
| Mail folders | `GET /users/{id}/mailFolders/delta` | `deltaLink` token |
| OneDrive/SharePoint files | `GET /drives/{id}/root/delta` | Change token |
| Teams messages | Events API / subscription webhooks | Event timestamp |

**Key constraint**: Graph API has rate limits (10,000 requests per 10 minutes per app per tenant). Implement exponential backoff + retry.

### IMAP (Fallback for Non-M365 Email)

For on-prem Exchange without Graph or other mail servers:
- IMAP IDLE for real-time notifications
- Periodic full sync with `UIDVALIDITY` + `UID` tracking
- MIME parsing for email body + attachments

### SMB / CIFS (File Servers)

- Enumerate via SMB2/3 protocol
- Track changes via file system timestamps + content hashing
- Read NTFS ACLs via `smbcacls` or Windows API
- Map SIDs to user/group identities via LDAP

### Confluence (Optional Connector)

- REST API v2 for page content
- Webhooks for real-time updates
- Space-level + page-level permission sync

### Google Drive (Optional Connector)

- Drive API v3 for file content
- Changes API for incremental sync
- `permissions.list` per file for ACL mapping

---

## 2. Ingestion Pipeline

```
Source → Fetch → Parse → Clean → Chunk → Embed → Upsert
                                                    │
                                              Store ACL metadata
```

### Step-by-Step

| Step | Description | Details |
|------|------------|---------|
| **Fetch** | Pull new/changed items since last checkpoint | Delta queries (Graph), file watchers (SMB), webhooks (Confluence) |
| **Parse** | Extract text from documents | PDF: layout-aware extraction. DOCX/PPTX/XLSX: python-docx, python-pptx, openpyxl. Email: MIME parser with threading. HTML: trafilatura. OCR: only for scanned PDFs (Tesseract / Azure Doc Intelligence) |
| **Clean** | Remove noise | Email signatures, disclaimers, boilerplate headers, HTML formatting |
| **Chunk** | Split into retrieval units | Conversation threads: by reply chain. Documents: by section headers (semantic chunking). Target: 256–512 tokens per chunk. Overlap: 50 tokens. Preserve parent document reference. |
| **Embed** | Convert to vector | Mode A: local model (BAAI/bge-large, 1024 dims). Mode B: Azure OpenAI text-embedding-3-large (3072 dims, configurable). Content hash check: skip re-embedding for unchanged text. |
| **Upsert** | Store in vector DB + doc store | Vector: Qdrant or Azure AI Search. Metadata: PostgreSQL or Azure SQL. Original doc: MinIO or Azure Blob. |

### Content Hashing for Skip Logic

```
hash = SHA-256(chunk_text)

if hash exists in chunk_store:
    skip embedding (content unchanged)
else:
    embed → upsert → store hash
```

This prevents re-embedding unchanged content during incremental updates, saving compute and API costs.

---

## 3. Vector Store Configuration

### Mode A — Qdrant (Local)

```yaml
# qdrant config
storage:
  storage_path: /data/qdrant
  
collections:
  enterprise_chunks:
    vector_size: 1024  # bge-large
    distance: Cosine
    payload_schema:
      doc_id: keyword
      source: keyword
      acl_principals: keyword[]  # for ACL filtering
      project_id: keyword
      author: keyword
      timestamp: datetime
      content_hash: keyword
      sensitivity_label: keyword
```

### Mode B — Azure AI Search

```json
{
  "name": "enterprise-chunks",
  "fields": [
    { "name": "chunk_id", "type": "Edm.String", "key": true },
    { "name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft" },
    { "name": "content_vector", "type": "Collection(Edm.Single)", "dimensions": 3072, "vectorSearchProfile": "default" },
    { "name": "doc_id", "type": "Edm.String", "filterable": true },
    { "name": "source", "type": "Edm.String", "filterable": true },
    { "name": "acl_principals", "type": "Collection(Edm.String)", "filterable": true },
    { "name": "author", "type": "Edm.String", "filterable": true },
    { "name": "timestamp", "type": "Edm.DateTimeOffset", "sortable": true },
    { "name": "sensitivity_label", "type": "Edm.String", "filterable": true }
  ]
}
```

---

## 4. Metadata Strategy

Every chunk MUST be tagged with:

| Field | Purpose | Example |
|-------|---------|---------|
| `doc_id` | Links chunk to parent document | `sp-abc123` |
| `chunk_id` | Unique chunk identifier | `chunk-42` |
| `source` | Origin system | `sharepoint`, `exchange`, `smb` |
| `acl_principals` | User/group IDs with access | `["user-jane", "sg-finance"]` |
| `project_id` | Project tag (if applicable) | `project-alpha` |
| `author` | Content creator | `jane.doe@company.com` |
| `entity_mentions` | Extracted entities | `["Acme Corp", "SEC", "Q4"]` |
| `timestamp` | Last modified | `2026-02-19T21:00:00Z` |
| `content_hash` | SHA-256 of chunk text | `a1b2c3d4...` |
| `sensitivity_label` | Purview label (if available) | `confidential` |

---

## 5. Hybrid Search Strategy

Combine vector similarity with keyword matching for best retrieval quality.

### Mode A (Qdrant + PostgreSQL FTS)

1. Vector search in Qdrant (top 50 candidates, ACL-filtered)
2. Keyword search in PostgreSQL full-text search (top 50 candidates, ACL-filtered)
3. Reciprocal Rank Fusion (RRF) to merge results
4. Return top 10 chunks to LLM

### Mode B (Azure AI Search)

1. Use Azure AI Search hybrid query (vector + keyword in single request)
2. Security trimming via `acl_principals` filter
3. Built-in RRF scoring
4. Return top 10 chunks to LLM

---

## 6. Background Job Infrastructure

| Framework | Use Case |
|-----------|----------|
| **BullMQ** (Node.js) or **Celery** (Python) | Task queue for ingestion jobs |
| **Cron / scheduler** | Periodic delta sync (configurable: 5 min – 1 hour) |
| **Webhooks** | Real-time triggers from Graph API subscriptions |

### Job Types

| Job | Trigger | Priority |
|-----|---------|----------|
| `full_sync_{source}` | Manual / initial setup | Low (background) |
| `delta_sync_{source}` | Scheduled (every 15 min default) | Medium |
| `webhook_update` | Real-time event | High |
| `permission_resync` | Scheduled (every 24h) | Medium |
| `reindex_document` | Manual / content change | High |

### Failure Handling

- Exponential backoff with jitter (max 5 retries)
- Dead letter queue for permanently failed jobs
- Alert in admin dashboard on repeated failures
- Auth token auto-refresh 5 minutes before expiry
