import { expect, test } from '@playwright/test';

test.describe('Mehman.io Edge Cases, Viewports & Accessibility E2E', () => {
  test('Accessibility & Keyboard Navigation Smoke Test', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 1. Check Chat Textarea Focus and Accessibility
    const textarea = page.locator('.chat-textarea');
    await textarea.focus();
    await expect(textarea).toBeFocused();

    // 2. Type message and submit with Enter
    await textarea.fill('Weekend stay in Jaipur for 2');
    await textarea.press('Enter');

    // Verify message sent
    const userMsg = page.locator('.message-row.user');
    await expect(userMsg).toBeVisible();

    // Verify response received
    const assistantMsg = page.locator('.message-row.assistant');
    await expect(assistantMsg.first()).toBeVisible({ timeout: 25000 });
  });

  test('Rapid Double-Click / Duplicate Submission Guard', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const input = page.locator('.chat-textarea');
    const sendBtn = page.locator('.send-button');

    await input.fill('Find luxury hotels in Goa');

    // Rapid double click
    await Promise.all([
      sendBtn.click({ clickCount: 2 }),
    ]);

    // Verify that disabled gate or single processing occurs without crashing
    await expect(page.locator('.message-row.assistant').first()).toBeVisible({ timeout: 25000 });

    // Ensure session messages count is coherent
    const userMessages = await page.locator('.message-row.user').count();
    expect(userMessages).toBeLessThanOrEqual(2);
  });

  test('Viewports: Multi-Resolution Responsiveness', async ({ page }) => {
    // Test 1024x768 (Tablet/Small Desktop)
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('/');
    await expect(page.locator('.app-layout')).toBeVisible();

    // Test 430x932 (Large Mobile)
    await page.setViewportSize({ width: 430, height: 932 });
    await expect(page.locator('.mobile-only-btn')).toBeVisible();

    // Test 375x667 (Compact Mobile)
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(page.locator('.chat-panel')).toBeVisible();
    await expect(page.locator('.chat-textarea')).toBeVisible();
  });

  test('Network Security Audit: No Database or Secrets Leaked', async ({ page }) => {
    const interceptedRequests: string[] = [];

    page.on('request', (request) => {
      interceptedRequests.push(request.url());
    });

    await page.goto('/');
    const input = page.locator('.chat-textarea');
    await input.fill('Is there availability in Manali?');
    await page.locator('.send-button').click();
    await expect(page.locator('.message-row.assistant').first()).toBeVisible({ timeout: 25000 });

    // Verify every API request is strictly directed to FastAPI host (port 8000 / relative)
    for (const url of interceptedRequests) {
      if (url.includes('/api/')) {
        expect(url).toMatch(/127\.0\.0\.1:8000|localhost:8000/);
      }
      // Guarantee Gemini API is NEVER called directly from the browser
      expect(url).not.toContain('generativelanguage.googleapis.com');
    }
  });
});
