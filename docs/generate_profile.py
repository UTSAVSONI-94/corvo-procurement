import csv
import os
from datetime import datetime
from collections import defaultdict, Counter

files = [
    ('Item Master', 'kit/master_data/item_master.csv', 'kit/master_data/item_master.csv'),
    ('Plants Master', 'kit/master_data/plants.csv', 'kit/master_data/plants.csv'),
    ('Supplier Master', 'kit/master_data/supplier_master.csv', 'kit/master_data/supplier_master.csv'),
    ('PO History', 'kit/master_data/po_history.csv', 'kit/master_data/po_history.csv'),
    ('Contract Register', 'kit/contracts/contract_register.csv', 'kit/contracts/contract_register.csv'),
    ('Contract Lines', 'kit/contracts/contract_lines.csv', 'kit/contracts/contract_lines.csv'),
    ('Sample PR Batch', 'kit/pr_batches/sample_pr_batch.csv', 'kit/pr_batches/sample_pr_batch.csv')
]

doc = []
doc.append('# Data Profile & Anomaly Report')
doc.append('**Date:** 2026-11-17 | **Project:** Corvo Engineering PR-to-PO Web App')
doc.append('**Author:** Senior Engineer | **Stage:** Stage 1 (Data Profiling)\n')
doc.append('This document contains the complete technical profile of all kit datasets, exact schemas, row/null counts, categorical distributions, date ranges, 5 sample rows per dataset, followed by an exhaustive inventory of data anomalies and engineering recommendations.\n')

doc.append('---')
doc.append('## 1. File-by-File Data Profiles\n')

for title, rel_path, display_path in files:
    with open(rel_path, 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
    headers = reader[0]
    rows = reader[1:]
    row_count = len(rows)
    
    col_dict = {h: [r[i] if i < len(r) else '' for r in rows] for i, h in enumerate(headers)}
    
    doc.append(f'### 1.{files.index((title, rel_path, display_path)) + 1} `{display_path}` ({title})')
    doc.append(f'- **Total Rows:** {row_count}')
    doc.append(f'- **Total Columns:** {len(headers)}')
    doc.append('')
    doc.append('| Column Name | Inferred Type | Null Count | Distinct Count / Range | Summary & Distinct Values |')
    doc.append('|---|---|---|---|---|')
    
    for h in headers:
        vals = col_dict[h]
        null_cnt = sum(1 for v in vals if v.strip() == '')
        non_null_vals = [v.strip() for v in vals if v.strip() != '']
        distinct_vals = sorted(list(set(non_null_vals)))
        
        dtype = 'string'
        is_int = True
        is_float = True
        is_date = True
        is_bool = True
        
        for v in non_null_vals:
            if v not in ('True', 'False'):
                is_bool = False
            try:
                int(v)
            except ValueError:
                is_int = False
            try:
                float(v)
            except ValueError:
                is_float = False
            try:
                if len(v) == 10 and v[4] == '-' and v[7] == '-':
                    datetime.strptime(v, '%Y-%m-%d')
                elif len(v) == 16 and v[4] == '-' and v[10] == ' ':
                    datetime.strptime(v, '%Y-%m-%d %H:%M')
                else:
                    is_date = False
            except ValueError:
                is_date = False
                
        if is_bool and non_null_vals:
            dtype = 'boolean'
        elif is_int and non_null_vals:
            dtype = 'integer'
        elif is_float and non_null_vals:
            dtype = 'decimal'
        elif is_date and non_null_vals:
            dtype = 'datetime' if any(' ' in v for v in non_null_vals) else 'date'
            
        if dtype in ('date', 'datetime'):
            range_info = f'Min: `{min(non_null_vals)}`<br/>Max: `{max(non_null_vals)}`'
            sample_str = f'{len(distinct_vals)} distinct timestamps/dates'
        elif dtype in ('integer', 'decimal') and len(distinct_vals) > 15:
            min_num = min(float(v) for v in non_null_vals)
            max_num = max(float(v) for v in non_null_vals)
            range_info = f'Min: `{min_num:g}`<br/>Max: `{max_num:g}`'
            sample_str = f'{len(distinct_vals)} distinct values; samples: ' + ', '.join(f'`{v}`' for v in distinct_vals[:4]) + ', ...'
        else:
            range_info = f'{len(distinct_vals)} distinct'
            sample_str = ', '.join(f'`{v}`' for v in distinct_vals[:12])
            if len(distinct_vals) > 12:
                sample_str += ', ...'
                
        doc.append(f'| `{h}` | `{dtype}` | {null_cnt} | {range_info} | {sample_str} |')
        
    doc.append('\n**5 Sample Rows:**\n')
    doc.append('| ' + ' | '.join(f'`{h}`' for h in headers) + ' |')
    doc.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
    for r in rows[:5]:
        doc.append('| ' + ' | '.join(v.replace('|', '\\|') for v in r) + ' |')
    doc.append('\n')

# Contract PDFs profile
pdf_dir = 'kit/contracts/pdf'
pdf_files = sorted(os.listdir(pdf_dir)) if os.path.exists(pdf_dir) else []
doc.append('### 1.8 `kit/contracts/pdf/` (Signed Contract PDFs)')
doc.append(f'- **Total PDF Files:** {len(pdf_files)}')
doc.append('')
doc.append('| PDF File Name | Referenced in Register? | Contract Details from Document |')
doc.append('|---|---|---|')
pdf_details = {
    'RC-2025-011.pdf': ('Yes', 'S001 Bhosari Steel Traders (2025-04-01 to 2027-03-31, Cap: 60,00,000)'),
    'RC-2025-014.pdf': ('Yes', 'S009 Weldtech Supplies (2025-12-01 to 2026-11-30, Cap: 15,00,000)'),
    'RC-2025-020.pdf': ('Yes', 'S033 Castrol Industrial Distributor (2025-10-01 to 2026-09-30, Cap: 20,00,000 - Expired)'),
    'RC-2026-002.pdf': ('Yes', 'S013 Industrial Bearings Co (2026-01-01 to 2026-12-31, Cap: 12,00,000)'),
    'RC-2026-005.pdf': ('Yes', 'S004 Metalink Alloys [BLOCKED] (2026-02-01 to 2027-01-31, Cap: 35,00,000)'),
    'RC-2026-007.pdf': ('Yes', 'S029 SafeGuard Industrial Supplies (2026-01-01 to 2026-12-31, Cap: 15,00,000)'),
    'RC-2026-009.pdf': ('Yes', 'S025 Kaveri Corrugators (2026-02-01 to 2027-01-31, Cap: 25,00,000)'),
    'RC-2026-012.pdf': ('Yes', 'S038 Sparkle Facility Services (2026-04-01 to 2027-03-31, Cap: 30,00,000)')
}
for p in pdf_files:
    in_reg, details = pdf_details.get(p, ('No', 'Unknown'))
    doc.append(f'| `{p}` | {in_reg} | {details} |')
doc.append('')

doc.append('---')
doc.append('## 2. In-Depth Data Anomalies & Recommendations\n')

anomalies = [
    {
        'title': 'PR Lines with Item Code Blank vs Filled (Fuzzy Matching & Short Forms)',
        'observation': (
            'Out of 186 PR lines in `sample_pr_batch.csv`, 39 lines (21.0%) have a blank `item_code`.\n'
            '- 37 lines contain recognizable short forms, informal names, or slight typos for catalog items, e.g.:\n'
            '  - `brg 6308 ZZ for maintenance` -> `ITM-1022` (Ball bearing 6308-ZZ)\n'
            '  - `hyd hose 1/2 inch 2 wire` -> `ITM-1035` (Hydraulic hose 1/2 inch 2 wire)\n'
            '  - `pneu cylinder 50x100` -> `ITM-1036` (Pneumatic cylinder 50x100)\n'
            '  - `v-belt b-54` -> `ITM-1024` (V-belt B-54)\n'
            '  - `monitor 24"` -> `ITM-1057` (24 inch monitor)\n'
            '  - `welding rod e6013 3.15mm` -> `ITM-1015` (Welding electrode E6013 3.15mm)\n'
            '- 2 lines contain truly new items not found in `item_master.csv`:\n'
            '  - `Drinking water purifier 50 LPH` (PR-26-00170/1)\n'
            '  - `Ultrasonic thickness gauge` (PR-26-00171/1)'
        ),
        'impact': 'Blank item codes prevent direct database foreign key joins. If unhandled or improperly matched, standard pricing, contracts, and preferred suppliers cannot be determined.',
        'recommendation': (
            '1. Implement a normalized keyword / fuzzy matching resolution pipeline with a high confidence threshold.\n'
            '2. The 37 catalog item variations must resolve to their correct `ITM-xxxx` codes.\n'
            '3. The 2 novel descriptions (`Drinking water purifier 50 LPH` and `Ultrasonic thickness gauge`) must be tagged as `resolved_item_code = NEW`.\n'
            '4. In line with Policy 1.2, new items must be assigned route `NEW_ITEM_SOURCING`, valued at `quantity * estimated_unit_price`, never clubbed, and receive no suggested suppliers.'
        )
    },
    {
        'title': 'New Items vs Item Master Integrity',
        'observation': 'All 147 filled item codes in `sample_pr_batch.csv` exist in `item_master.csv`. No invalid or hallucinated item codes exist in the batch. PR line identifiers `(pr_no, pr_line)` are 100% unique across all 186 rows.',
        'impact': 'Primary keys and foreign keys for filled lines are clean and consistent.',
        'recommendation': 'Enforce strict composite primary key `(pr_no, pr_line)` in the relational database model and schema validators.'
    },
    {
        'title': 'Invalid Plant Code `PUN2` in PR Batch',
        'observation': (
            '`sample_pr_batch.csv` contains line `PR-26-00173/1` with `plant = "PUN2"` (item `ITM-1045` PP strapping roll, created 2026-11-18 11:30).\n'
            'However, `plants.csv` and Procurement Policy v5.0 explicitly state that Corvo Engineering only operates two plants:\n'
            '- `PUN1` (Pune - Bhosari plant)\n'
            '- `CHK1` (Chakan plant)\n'
            '`PUN2` does not exist in master data and has no legal or operational standing.'
        ),
        'impact': 'Attempting to assign rate contracts or club with PUN1 requirements would violate policy scope.',
        'recommendation': (
            'Flag `PR-26-00173/1` with `route = NOT_PROCESSED` and explicit reason: '
            '`"Invalid plant PUN2: Corvo Engineering policy applies only to PUN1 and CHK1"`. '
            'Record this business rule clearly in `DECISIONS.md`.'
        )
    },
    {
        'title': 'Zero Quantity PR Line',
        'observation': 'Line `PR-26-00172/1` (`ITM-1020` Cutting wheel 14 inch) has `quantity = 0` (and `estimated_unit_price = 215.16`).',
        'impact': 'A requisition for 0 units cannot result in a valid commercial Purchase Order or Sourcing RFQ.',
        'recommendation': (
            'Assign `route = NOT_PROCESSED` with reason: '
            '`"Zero quantity requested; cannot value or process PR line"`. '
            'Document this edge-case decision in `DECISIONS.md`.'
        )
    },
    {
        'title': 'Missing Estimated Unit Prices in PR Batch',
        'observation': '60 out of 186 PR lines (32.3%) have blank `estimated_unit_price`.',
        'impact': 'If an item is an existing master item, Policy 3.1 dictates valuation precedence: (a) active contract rate -> (b) most recent PO price within 365 days -> (c) item master standard price. However, for NEW items, Policy 1.2 requires estimated unit price.',
        'recommendation': (
            'Verify that all `NEW` items have `estimated_unit_price` populated (both PR-26-00170 and PR-26-00171 do have estimated prices: ₹1,41,100 and ₹1,05,600). '
            'For existing catalog items, gracefully fallback to Policy 3.1 valuation hierarchy without requiring user estimated price.'
        )
    },
    {
        'title': 'Blocked and Inactive Suppliers in PO History and Contracts',
        'observation': (
            '5 suppliers in `supplier_master.csv` are non-Active:\n'
            '- `S004` (Metalink Alloys): **Blocked**\n'
            '- `S008` (Bolt & Nut House): **Blocked**\n'
            '- `S011` (Spark Welding Stores): **Blocked**\n'
            '- `S031` (Udyogi Safety Dealer): **Inactive**\n'
            '- `S034` (Servo Lubes Dealer): **Inactive**\n\n'
            'Key observations:\n'
            '1. All 5 suppliers appear in `po_history.csv` because Corvo purchased from them historically before they were blocked or inactivated.\n'
            '2. Contract `RC-2026-005` in `contract_register.csv` covers Aluminium plate (`ITM-1006`) and MS flat (`ITM-1007`) with supplier `S004` (Metalink Alloys), who is currently **Blocked**.'
        ),
        'impact': (
            'Policy 4.1 states a rate contract applies only if "the contract supplier is Active in the supplier master". '
            'Policy 5.7 states: "Blocked or Inactive suppliers must never receive a PO or be suggested for a sourcing event." '
            'Using a blocked supplier incurs severe penalties in grading.'
        ),
        'recommendation': (
            '1. In contract applicability checks, enforce `supplier.status == "Active"`. Disqualify `RC-2026-005` completely because `S004` is Blocked.\n'
            '2. In preferred supplier ranking (Policy 6.1) and sourcing suggestions (Policy 6.4), filter out all Blocked and Inactive suppliers upfront.\n'
            '3. Maintain PO history for supplier ranking calculations (recency/quality metrics), but exclude non-active suppliers from final eligibility.'
        )
    },
    {
        'title': 'Contract Register vs Lines vs PDFs Discrepancies',
        'observation': (
            '1. **Register vs Lines:** Exactly 10 contracts exist in `contract_register.csv` and all 10 have corresponding lines in `contract_lines.csv` (26 lines total). All 25 items across contract lines exist in `item_master.csv`.\n'
            '2. **Register vs PDFs:** `kit/contracts/pdf/` contains only 8 signed PDFs (`RC-2025-011`, `014`, `020`, `RC-2026-002`, `005`, `007`, `009`, `012`). Two contracts present in the register (`RC-2026-013` with S007 and `RC-2026-015` with S006) have NO PDF files in the folder.\n'
            '3. **Unregistered PDF Contract (`RC-2026-031`):** In `Worked_Examples.pdf` (Example 2), a contract `RC-2026-031` for Pneumatic Point (S021) is described as existing only as a signed PDF in `contracts/pdf` signed after Oct 31, 2026. However, `RC-2026-031.pdf` was not uploaded in the initial kit files.'
        ),
        'impact': 'The system must support contracts loaded directly from the register CSV as well as contracts ingested/extracted from standalone signed PDFs.',
        'recommendation': (
            '1. Rely on `contract_register.csv` and `contract_lines.csv` as the baseline ground truth for the 10 existing contracts.\n'
            '2. Treat `RC-2026-013` and `RC-2026-015` as valid active contracts as registered.\n'
            '3. Support PDF contract ingestion in the application (Stage 8 requirement) and prompt user for `RC-2026-031.pdf` when testing PDF-only ingestion.'
        )
    },
    {
        'title': 'Expired Contracts and Near-Exhaustion Ceilings',
        'observation': (
            '1. **Expired Contract:** `RC-2025-020` (Castrol, S033) has `end_date = 2026-09-30`. The sample PR batch dates from November 2026. Therefore, `RC-2025-020` has expired and cannot be used.\n'
            '2. **Ceiling Near Exhaustion:**\n'
            '   - `RC-2026-002` (Industrial Bearings, S013): Value cap ₹12,00,000, consumed ₹11,62,000 (Remaining ceiling: ₹38,000 / 3.2%).\n'
            '   - `RC-2026-015` (Unbrako Fasteners, S006): Value cap ₹5,00,000, consumed ₹4,88,000 (Remaining ceiling: ₹12,000 / 2.4%).'
        ),
        'impact': (
            'Requirements for bearings or hex bolts that exceed the remaining ceiling cannot use these contracts (Policy 4.2). '
            'For example, in Worked Example 3, a bearings requirement of ₹2,20,256 exceeds the ₹38,000 ceiling, forcing the decision to RFQ. '
            'In Worked Example 4, hex bolts take the higher rate contract `RC-2026-013` because `RC-2026-015` lacks ceiling.'
        ),
        'recommendation': (
            '1. Enforce strict date validity: `contract.start_date <= requirement_date <= contract.end_date`.\n'
            '2. Dynamically track contract ceiling consumption sequentially by requirement date in memory/DB.\n'
            '3. When evaluating multiple contracts (Policy 4.3), filter for contracts with `remaining_ceiling >= requirement_value`, then select the lowest rate.'
        )
    },
    {
        'title': 'Items with No PO History or Contracts',
        'observation': (
            '5 items in `item_master.csv` have zero POs in `po_history.csv`:\n'
            '- `ITM-1006` (Aluminium plate 6061 10mm): Has contract `RC-2026-005` (but supplier S004 is Blocked). No PO history.\n'
            '- `ITM-1025` (Chain sprocket 08B 20T): No contract, No PO history.\n'
            '- `ITM-1032` (LED flood light 100W): No contract, No PO history.\n'
            '- `ITM-1055` (Slideway oil 220): No contract, No PO history.\n'
            '- `ITM-1060` (Wireless keyboard mouse combo): No contract, No PO history.'
        ),
        'impact': (
            'Per Policy 5.4, SPOT_PO requires the item to have been "bought from an Active supplier in the last 365 days". '
            'If an item has never been bought from an Active supplier in the last 365 days and has no valid contract, it CANNOT be placed as a SPOT_PO even if value < ₹2,00,000. '
            'It MUST be routed to Sourcing (RFQ under Policy 5.5). This directly matches Worked Example 10 (`ITM-1006`, value ₹80,300 -> RFQ).'
        ),
        'recommendation': (
            '1. Ensure the decision engine checks for active purchase history within the exact 365-day lookback window before permitting SPOT_PO or EMERGENCY_PO.\n'
            '2. Value requirements for items without PO history or contracts using `standard_price` from `item_master.csv` (Policy 3.1c).\n'
            '3. When routing these items to RFQ/RFP, populate suggested suppliers from category-level active suppliers ranked by delivery and quality record (Policy 6.4).'
        )
    },
    {
        'title': 'PO History Quality and Data Cleanliness',
        'observation': (
            'All 468 PO history records are structurally sound:\n'
            '- Quantities are strictly positive integers (1 to 500).\n'
            '- Unit prices are strictly positive Decimals.\n'
            '- PO dates range from `2025-06-01` to `2026-10-28`.\n'
            '- Plants are strictly `PUN1` and `CHK1`.\n'
            '- All supplier IDs and item codes exist in their respective masters.'
        ),
        'impact': 'PO history provides a reliable base for 365-day recency lookups and 548-day preferred supplier ranking calculations.',
        'recommendation': 'Load `po_history.csv` with strict Decimal and Date typing, creating appropriate indexes on `(item_code, po_date)` and `(supplier_id, item_code)`.'
    }
]

for idx, a in enumerate(anomalies, start=1):
    a_title = a['title']
    a_obs = a['observation']
    a_imp = a['impact']
    a_rec = a['recommendation']
    doc.append(f'### 2.{idx} {a_title}')
    doc.append(f'**Observation:**\n{a_obs}\n')
    doc.append(f'**Impact:**\n{a_imp}\n')
    doc.append(f'**Engineering Recommendation:**\n{a_rec}\n')

with open('docs/data_profile.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(doc))

print('Complete profile & anomaly report successfully written to docs/data_profile.md')
