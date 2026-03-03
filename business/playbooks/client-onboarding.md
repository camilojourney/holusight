# Client Onboarding — Delivery Kickoff

## After Contract Signed

### Week 0: Setup (1-2 days)

1. Create client folder: `proposals/clients/<name>/`
2. Run **delivery-planner** agent to create delivery plan
3. Get M365 / data source access from client (OAuth app registration)
4. Identify the pilot project (1 department or project folder)

### Week 1: Discovery + Index

1. Audit their document structure (SharePoint sites, folder hierarchy, email patterns)
2. Extend CodeSight for their file types if needed (PDF/DOCX/PPTX)
3. Index the pilot project (~20-100 documents)
4. Test search quality with 10+ real questions from their team

### Week 2: Deploy + Train

1. Deploy search UI (Streamlit or web app)
2. Run live demo with client's team using their actual documents
3. Train 2-3 power users
4. Collect feedback, tune chunk sizes and search parameters

### Week 3: Handoff

1. Document the setup (what's indexed, how to add new projects)
2. Set up monitoring (index freshness, search quality)
3. Agree on maintenance scope and cadence
4. Transition to monthly retainer

## Delivery Depends On

All technical delivery uses the **codesight** repo. Check delivery-planner agent's memory for what CodeSight can do today vs what needs building.
