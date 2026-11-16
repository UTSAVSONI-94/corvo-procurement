import unittest
import csv
import os

class TestDataProfiling(unittest.TestCase):
    def setUp(self):
        self.files = {
            'item_master': 'kit/master_data/item_master.csv',
            'plants': 'kit/master_data/plants.csv',
            'supplier_master': 'kit/master_data/supplier_master.csv',
            'po_history': 'kit/master_data/po_history.csv',
            'contract_register': 'kit/contracts/contract_register.csv',
            'contract_lines': 'kit/contracts/contract_lines.csv',
            'sample_pr_batch': 'kit/pr_batches/sample_pr_batch.csv'
        }

    def test_all_files_exist(self):
        for name, path in self.files.items():
            self.assertTrue(os.path.exists(path), f"File {path} must exist")

    def test_row_counts(self):
        expected_counts = {
            'item_master': 73,
            'plants': 2,
            'supplier_master': 48,
            'po_history': 468,
            'contract_register': 10,
            'contract_lines': 26,
            'sample_pr_batch': 186
        }
        for name, expected in expected_counts.items():
            with open(self.files[name], 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)[1:] # exclude header
                self.assertEqual(len(rows), expected, f"Row count mismatch for {name}")

    def test_plants_master(self):
        with open(self.files['plants'], 'r') as f:
            plants = [r['plant'] for r in csv.DictReader(f)]
        self.assertEqual(set(plants), {'PUN1', 'CHK1'})

    def test_supplier_statuses(self):
        with open(self.files['supplier_master'], 'r') as f:
            suppliers = {r['supplier_id']: r['status'] for r in csv.DictReader(f)}
        self.assertEqual(suppliers['S004'], 'Blocked')
        self.assertEqual(suppliers['S008'], 'Blocked')
        self.assertEqual(suppliers['S011'], 'Blocked')
        self.assertEqual(suppliers['S031'], 'Inactive')
        self.assertEqual(suppliers['S034'], 'Inactive')

    def test_pr_anomalies_detected(self):
        with open(self.files['sample_pr_batch'], 'r') as f:
            prs = list(csv.DictReader(f))
        
        # Check PUN2 anomaly
        pun2_prs = [r for r in prs if r['plant'] == 'PUN2']
        self.assertEqual(len(pun2_prs), 1)
        self.assertEqual(pun2_prs[0]['pr_no'], 'PR-26-00173')

        # Check Zero Qty anomaly
        zero_qty_prs = [r for r in prs if r['quantity'] == '0']
        self.assertEqual(len(zero_qty_prs), 1)
        self.assertEqual(zero_qty_prs[0]['pr_no'], 'PR-26-00172')

        # Check Blank item_code count
        blank_items = [r for r in prs if not r['item_code']]
        self.assertEqual(len(blank_items), 39)

    def test_contract_validity_and_caps(self):
        with open(self.files['contract_register'], 'r') as f:
            contracts = {r['contract_id']: r for r in csv.DictReader(f)}
        
        # Expired contract
        self.assertTrue(contracts['RC-2025-020']['end_date'] < '2026-11-01')
        
        # Ceilings near exhaustion
        bearings_cap = float(contracts['RC-2026-002']['value_cap'])
        bearings_consumed = float(contracts['RC-2026-002']['consumed_value'])
        self.assertEqual(bearings_cap - bearings_consumed, 38000.0)

if __name__ == '__main__':
    unittest.main()

