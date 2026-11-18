import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Corvo Procurement Frontend Smoke Tests', () => {

  test('Smoke Test 1: Chat to PR flow', async ({ page }) => {
    // Navigate to frontend
    await page.goto('/');

    // Switch to Requester role (or click Requester Chat)
    await page.getByRole('button', { name: 'Requester', exact: true }).click();
    await expect(page.getByText('Requester Intake Assistant')).toBeVisible();

    // Type requisition message
    const input = page.getByPlaceholder('Describe your requisition or answer assistant questions...');
    await input.fill('need 200 nitrile gloves for Chakan by next Friday');
    await page.getByRole('button', { name: 'Send' }).click();

    // Assistant slot-fills and presents confirmation card
    await expect(page.getByText('Requisition Ready for Confirmation')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Confirm PR')).toBeVisible();

    // Primary action: Confirm PR
    await page.getByRole('button', { name: 'Confirm PR' }).click();

    // Verify confirmation and PR creation
    await expect(page.getByText(/Purchase Requisition Finalized:/)).toBeVisible({ timeout: 10000 });
  });

  test('Smoke Test 2: Upload batch to approve flow', async ({ page }) => {
    await page.goto('/');

    // Navigate to Batches
    await page.getByRole('button', { name: 'Batches' }).click();
    await expect(page.getByText('Upload Procurement Batch CSV')).toBeVisible();

    // Attach batch CSV
    const csvPath = path.resolve('../kit/pr_batches/sample_pr_batch.csv');
    const fileInput = page.locator('input[data-testid="batch-file-input"]');
    await fileInput.setInputFiles(csvPath);

    // Primary Action: Process batch
    const processBtn = page.getByRole('button', { name: 'Process batch' });
    await expect(processBtn).toBeEnabled();
    await processBtn.click();

    // Wait for batch evaluation results
    await expect(page.getByText('Total Rows Evaluated')).toBeVisible({ timeout: 15000 });

    // Navigate to Buyer Workspace to approve
    await page.getByRole('button', { name: 'Buyer Workspace' }).click();
    await expect(page.locator('input[placeholder="Search group ID, item, description, supplier..."]')).toBeVisible();

    // Click single approve
    const approveBtn = page.locator('button[data-testid^="approve-btn-"]').first();
    await expect(approveBtn).toBeVisible({ timeout: 10000 });
    await approveBtn.click();

    // Verify approval confirmation notice
    await expect(page.getByText(/Successfully approved/i)).toBeVisible({ timeout: 5000 });
  });

  test('Smoke Test 3: Policy upload to activate flow', async ({ page }) => {
    await page.goto('/');

    // Switch to Procurement Admin role
    await page.getByRole('button', { name: 'Procurement Admin', exact: true }).click();
    await expect(page.getByText('Upload Policy Amendment')).toBeVisible();

    // Enter amendment instruction
    const textarea = page.getByPlaceholder('Type amendment instruction or paste policy change text...');
    await textarea.fill('raise the spot PO limit to 300000 for plant CHK1 only');

    // Click Analyze Amendment
    await page.getByRole('button', { name: 'Analyze Amendment' }).click();

    // Verify Plain-Language Diff & Impact Preview appear
    await expect(page.getByText('Plain-Language Diff')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('p:has-text("Spot PO")')).toBeVisible();

    // Primary Action: Approve & activate with effective date
    const activateBtn = page.getByRole('button', { name: /Approve & Activate with Effective Date/i });
    await expect(activateBtn).toBeVisible();
    await activateBtn.click();

    // Verify activation confirmation
    await expect(page.getByText(/approved and activated/i)).toBeVisible({ timeout: 5000 });
  });

});

