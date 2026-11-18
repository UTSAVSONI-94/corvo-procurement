# Blind Test Runbook: Step-by-Step Operator Guide

This runbook guides evaluators and operators through executing the live 2-hour procurement blind test against the Corvo Engineering Procurement System.

**Target Total Run Time:** 10–12 minutes (well under the 30-minute test threshold).  
**Live Hosted URL:** [`https://corvo-procurement-s5sq.onrender.com`](https://corvo-procurement-s5sq.onrender.com)  
**API Healthcheck:** [`https://corvo-procurement-s5sq.onrender.com/health`](https://corvo-procurement-s5sq.onrender.com/health)

---

## Prerequisites & Preflight Check (1 Minute)

1. Open your browser and navigate to the hosted app:
   ```
   https://corvo-procurement-s5sq.onrender.com
   ```
2. Verify cold-start status:
   - If the site is waking from sleep, it will respond within 20–40 seconds.
   - You can also ping `curl https://corvo-procurement-s5sq.onrender.com/health`.
3. Verify that the header shows:
   - Green badge: **`Policy Active: v5.0`**
   - Role switcher set to **`Requester`** or **`Buyer`**.

---

## Step 1: Process Baseline Batch under Policy v5.0 (3 Minutes)

### Option A: Using the React Web UI
1. In the navigation bar, click **Batches** (`/batches`).
2. Drag and drop `kit/pr_batches/sample_pr_batch.csv` (or the evaluation batch provided by reviewers) into the upload area.
3. Click the primary button: **"Process Batch"**.
4. The system validates the CSV:
   - Reports lines accepted and lines rejected (e.g. `PUN2` unknown plant, `quantity: 0`).
5. Click **Buyer Workspace** (`/workspace`):
   - Review the requirements table.
   - Click any requirement to open the **"Why" Drawer**:
     - View the matched policy clause (`Clause 5.2`, `Clause 5.4`, etc.).
     - View the real-time contract ceiling progress bar (`consumed / ceiling`).
     - View the preferred supplier score breakdown (30% frequency, 25% recency, 20% contract, 15% OTD, 10% quality).
6. Click **"Export Decisions CSV"** in the top right to download `decisions_v5.0.csv`.

### Option B: Using the CLI / API
```bash
# Direct API call:
curl -s -X POST -F "file=@kit/pr_batches/sample_pr_batch.csv" \
  https://corvo-procurement-s5sq.onrender.com/api/process-batch > submission/decisions_v5.0.json

# Or direct offline CLI:
python -m backend.app.cli process kit/pr_batches/sample_pr_batch.csv submission/decisions_v5.0.csv
```

---

## Step 2: Ingest & Activate Policy Amendments (4 Minutes)

Management frequently issues policy amendments. We test three realistic amendment scenarios:

### Amendment A: Raise Spot Limit & Emergency Cap
- **Document:** `kit/amendments/amendment_a_limits.txt`
- **Change:** Spot PO limit raised from ₹2,00,000 to ₹3,00,000; Emergency limit to ₹7,50,000.
1. In the web header, switch the role dropdown to **`Procurement Admin`**.
2. Click **Policy** in navigation (`/policy`).
3. Under **Ingest Policy Amendment**:
   - Either paste the text instruction:
     > *"Raise the spot PO limit to 3 lakh and emergency limit to 7.5 lakh effective from 2026-11-01"*
   - Or upload `kit/amendments/amendment_a_limits.txt`.
4. Click **"Ingest Amendment"**.
5. **Review Plain-English Diff**:
   - Verify the diff renders:
     > *"Threshold 'spot_limit' changed from ₹200,000.00 to ₹300,000.00."*
6. **Review Impact Preview**:
   - The preview table automatically simulates how existing requisitions migrate (15 lines shift from `RFQ` to `SPOT_PO`).
7. Click the green button: **"Approve & Activate Amendment"**.
8. Notice the header badge updates immediately to **`Policy Active: v5.1`**.

---

## Step 3: Reprocess Batch under Amended Policy v5.1 (2 Minutes)

1. Return to **Batches** (`/batches`).
2. Click **"Reprocess Latest Batch"** (or re-upload the batch CSV).
3. Switch to **Buyer Workspace** (`/workspace`):
   - Notice that requisitions valued between ₹2,00,000 and ₹3,00,000 (such as `PR-26-00001` for bearing `ITM-1053` at ₹2,58,956) now show route **`SPOT_PO`** instead of `RFQ`!
   - Consolidated POs are automatically recomputed.
4. Click **"Export Decisions CSV"** to save `submission/decisions_after_amendment.csv`.

---

## Step 4: Export Preferred Suppliers Ledger (1 Minute)

1. In navigation, click **Preferred Suppliers** (`/preferred`).
2. Select as-of date: `2026-11-01`.
3. Inspect the top 3 ranked vendors per item with their score components.
4. Click **"Export Preferred Suppliers CSV"** to save `submission/preferred_suppliers.csv`.

---

## Step 5: Verify and Push Submission Artifacts (2 Minutes)

Confirm the three required CSV files are populated in `submission/`:
```bash
ls -lh submission/
# 1. submission/decisions_v5.0.csv
# 2. submission/decisions_after_amendment.csv
# 3. submission/preferred_suppliers.csv
```

Push the submission files to GitHub:
```bash
git add submission/
git commit -m "chore(submission): freeze blind test output CSV artifacts"
git push origin main
```

---

## Step 6: Resetting to Pristine Baseline v5.0 (30 Seconds)

To reset the database back to clean baseline state for a new test run:

```bash
curl -X POST https://corvo-procurement-s5sq.onrender.com/api/admin/reset-baseline
```

Response:
```json
{
  "status": "success",
  "message": "Database reset to pristine baseline with Policy v5.0 active",
  "active_version": "v5.0"
}
```
The header badge will immediately show **`Policy Active: v5.0`**, with all rehearsal versions cleanly removed.
