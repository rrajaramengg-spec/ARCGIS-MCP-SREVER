import { expect, test } from "@playwright/test";

/**
 * E2E test: panel maximize/minimize toggle.
 */
test.describe("Panel Layout Toggle", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
        await page.waitForSelector('[aria-label="Chat input"]', {
            timeout: 10000,
        });
    });

    test("should maximize chat panel and restore", async ({ page }) => {
        const maxChatBtn = page.getByLabel("Maximize chat");
        await expect(maxChatBtn).toBeVisible();

        await maxChatBtn.click();

        // After maximizing, the button label changes to "Restore panels"
        const restoreBtn = page.getByLabel("Restore panels").first();
        await expect(restoreBtn).toBeVisible();

        await restoreBtn.click();

        // Should be back to "Maximize chat"
        await expect(page.getByLabel("Maximize chat")).toBeVisible();
    });

    test("should maximize map panel and restore", async ({ page }) => {
        const maxMapBtn = page.getByLabel("Maximize map");
        await expect(maxMapBtn).toBeVisible();

        await maxMapBtn.click();

        // After maximizing, the button label changes to "Restore panels"
        const restoreBtn = page.getByLabel("Restore panels").first();
        await expect(restoreBtn).toBeVisible();

        await restoreBtn.click();

        // Should be back to "Maximize map"
        await expect(page.getByLabel("Maximize map")).toBeVisible();
    });
});
