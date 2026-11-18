import json

with open("/tmp/hosted_decisions.json") as f:
    raw = json.load(f)

data = raw.get("lines", raw)
print(f"Total decisions returned: {len(data)}")

blocked_suppliers = ["S004"]
blocked_found = [
    d for d in data
    if d.get("supplier_id") in blocked_suppliers
    or any(s in blocked_suppliers for s in d.get("suggested_supplier_ids", []))
]
print(f"Blocked/Inactive suppliers found: {len(blocked_found)} (must be 0)")

no_reason = [d for d in data if not d.get("reason")]
print(f"Rows without reason: {len(no_reason)} (must be 0)")

po_ids = set(d["po_id"] for d in data if d.get("po_id"))
print(f"POs created: {len(po_ids)} -> {sorted(list(po_ids))[:5]}...")

for d in data:
    pr = d.get("pr_no")
    if pr == "PR-BLIND-3001":
        print(f"Blocked item line ({pr}): route={d.get('route')}, supplier={d.get('supplier_id')}, suggested={d.get('suggested_supplier_ids')}")
    elif pr == "PR-BLIND-4001":
        print(f"Unknown item line ({pr}): route={d.get('route')}, item={d.get('resolved_item_code')}, suggested={d.get('suggested_supplier_ids')}")
    elif pr in ["PR-BLIND-5001", "PR-BLIND-5002"]:
        print(f"Emergency line ({pr}): route={d.get('route')}, decision={d.get('decision')}, po_id={d.get('po_id')}")
    elif pr == "PR-BLIND-6001":
        print(f"Capex line ({pr}): route={d.get('route')}, decision={d.get('decision')}")
