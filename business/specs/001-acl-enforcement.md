# Spec: ACL Enforcement — End-to-End Access Control

## Principle

> Every query is permission-filtered. No user ever sees a document they cannot access in the source system.

The rule is always:

```
Identity (SSO / Entra ID)
  → Group membership resolution
    → Document ACL filter construction
      → Retrieval restricted to authorized slice
        → Response with authorized citations only
          → Audit log entry
```

This is constant regardless of deployment mode. Only the infrastructure changes.

---

## 1. Identity Resolution

### Authentication Flow

1. User authenticates via SSO (SAML 2.0 or OIDC)
2. System receives identity claims:
   - `user_id` (unique identifier)
   - `email` (corporate email)
   - `groups[]` (security group memberships)
   - `roles[]` (application roles, if any)
3. Identity is cached with configurable TTL (default: 15 minutes)

### Supported Identity Providers

| Provider | Protocol | Notes |
|----------|----------|-------|
| Azure AD / Entra ID | OIDC + SAML | Primary for M365 customers |
| Okta | OIDC + SAML | Common in mid-market |
| Google Workspace | OIDC | For Google-first companies |
| On-prem AD | LDAP + SAML (via ADFS) | For strict local-only |

---

## 2. Permission Mapping by Source

### SharePoint / OneDrive (via Microsoft Graph)

**How permissions work in SharePoint**:
- SharePoint uses role-based permissions at the site, library, folder, and item level
- Permissions can be inherited or broken (unique permissions)
- Graph API exposes permissions via `/permissions` endpoint on `driveItem`

**What we store per document**:

```json
{
  "doc_id": "sp-abc123",
  "source": "sharepoint",
  "site_id": "site-xyz",
  "path": "/sites/finance/Shared Documents/Q4-Report.xlsx",
  "acl": {
    "type": "allowlist",
    "principals": [
      { "type": "group", "id": "sg-finance-team", "role": "read" },
      { "type": "user", "id": "user-jane@company.com", "role": "owner" }
    ]
  },
  "sensitivity_label": "confidential",
  "last_permission_sync": "2026-02-19T21:00:00Z"
}
```

**Sync strategy**:
- Full permission crawl on initial index
- Delta sync: re-check permissions when document content changes
- Periodic full re-sync of permissions (every 24h) to catch permission-only changes

### Outlook / Exchange (via Microsoft Graph)

**Permission model**:
- Mailbox access is per-user by default
- Shared mailboxes have explicit delegate permissions
- User can only search their own mailbox unless they have delegate access

**What we store**:

```json
{
  "doc_id": "mail-msg456",
  "source": "exchange",
  "mailbox_owner": "user-jane@company.com",
  "acl": {
    "type": "allowlist",
    "principals": [
      { "type": "user", "id": "user-jane@company.com", "role": "owner" },
      { "type": "user", "id": "user-bob@company.com", "role": "delegate" }
    ]
  },
  "thread_id": "thread-789",
  "folder": "Inbox"
}
```

### File Server (SMB / CIFS)

**Permission model**:
- NTFS ACLs: Allow/Deny for users and groups at folder/file level
- Inheritance from parent folders

**Sync strategy**:
- Read NTFS ACL via `icacls` or Windows API (or Samba `smbcacls`)
- Map SIDs to user/group identities via LDAP lookup
- Store as normalized ACL entries

### Confluence / Jira

**Permission model**:
- Space-level permissions (who can view a space)
- Page-level restrictions (optional override)

**What we store**:
- Space permissions as default ACL
- Override with page-level restrictions when present

### Google Drive

**Permission model**:
- Per-file/folder permissions (owner, editor, viewer, commenter)
- Domain-wide sharing settings

**Sync strategy**:
- Use Drive API `permissions.list` per file
- Map Google groups to internal group identifiers

---

## 3. Query-Time Enforcement

### Filter Construction

When a user makes a query:

1. Resolve user identity → get `user_id` + `groups[]`
2. Build ACL filter:
   ```
   WHERE acl.principals contains user_id
      OR acl.principals contains ANY(groups[])
   ```
3. Apply filter to vector search AND keyword search
4. Only return chunks that pass the ACL filter

### Implementation per Mode

**Mode A (Local / Qdrant)**:
- Store ACL principal IDs as payload metadata on each vector
- Use Qdrant payload filtering at query time
- Filter: `must: [{ key: "acl_principals", match: { any: [user_id, ...groups] } }]`

**Mode B (Azure AI Search)**:
- Use Azure AI Search [security trimming](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search)
- Store ACL principals in a filterable collection field
- Apply OData filter: `acl_principals/any(p: search.in(p, 'user-id,group-1,group-2'))`

### Deny-by-Default Policy

- If a document has NO ACL metadata → it is NOT returned in any query
- If ACL sync fails for a source → documents from that source are quarantined
- Admin dashboard shows "unresolved ACL" count per source

---

## 4. Sensitivity Labels (Optional, Mode B)

For Azure-native deployments using Microsoft Purview:

| Label | Behavior |
|-------|----------|
| `Public` | Available to all authenticated users |
| `Internal` | Available to all employees |
| `Confidential` | Restricted to specified groups |
| `Highly Confidential` | Restricted to specified individuals + requires justification |

- Labels are indexed as metadata
- Admin can configure: "Never return `Highly Confidential` in AI responses"
- Useful for governance-first buyers (Profile C)

---

## 5. Audit Trail

Every query generates an audit log entry:

```json
{
  "timestamp": "2026-02-19T21:42:00Z",
  "user_id": "user-jane@company.com",
  "query": "What was the Q4 revenue forecast?",
  "sources_returned": [
    { "doc_id": "sp-abc123", "source": "sharepoint", "chunk_id": "chunk-42" },
    { "doc_id": "sp-def456", "source": "sharepoint", "chunk_id": "chunk-17" }
  ],
  "sources_filtered_out": 3,
  "response_latency_ms": 1240,
  "session_id": "sess-xyz"
}
```

**Retention**: Configurable by customer (default: 90 days)
**Access**: Admin-only via dashboard
**Export**: CSV/JSON for compliance reporting

---

## 6. Security Threat Model

| Threat | Mitigation |
|--------|------------|
| User escalates permissions in source system | Periodic ACL re-sync (24h), event-driven re-sync on permission change |
| Prompt injection via malicious document content | Input sanitization, LLM output validation, retrieval sandboxing |
| Admin misconfigures ACL mapping | Dry-run mode for ACL changes, diff report before applying |
| Stale permissions (user leaves company) | SSO integration auto-disables, ACL re-sync removes access |
| Data exfiltration via broad queries | Rate limiting, anomaly detection on query patterns |
