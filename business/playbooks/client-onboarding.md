# Client Onboarding — Delivery Kickoff

## After Contract Signed

### Week 0: Setup (1-2 days)

1. Create client folder: `proposals/clients/<name>/`
2. Confirm the two-week scope, acceptance questions, and customer owner
3. Confirm a customer-mounted read-only document folder or git mirror
4. Identify the pilot project (one department or project folder)

### Week 1: Discovery + Index

1. Review the mounted folder structure and supported file types (PDF/DOCX/PPTX, text, and code)
2. Deploy the Docker or VM installation with the source folder mounted read-only
3. Index the pilot project (~20-100 documents)
4. Test search quality with 10-15 real questions from their team

### Week 2: Deploy + Train

1. Run the FastAPI browser UI with the customer's actual documents
2. Configure the customer's selected answer provider, if needed
3. Train 3-5 champions and collect feedback
4. Review acceptance metrics and hand off the compose file, environment template, backup steps, and troubleshooting runbook

## Delivery Depends On

All technical delivery uses the **codesight** repo. Live M365 sync, per-document ACLs, SSO, and broad connectors are outside this pilot and require separate future scoping.
