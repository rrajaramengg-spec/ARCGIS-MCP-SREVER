import { expect, test } from "@playwright/test";

/**
 * E2E test: slash command dropdown appears on `/` keystroke.
 */
test.describe("Slash Command Dropdown", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
        await page.waitForSelector('[aria-label="Chat input"]', {
            timeout: 10000,
        });
    });

    test("should show command dropdown when typing /", async ({ page }) => {
        const input = page.getByLabel("Chat input");
        await input.fill("/");

        // The dropdown should appear with command options
        const dropdown = page.locator(
            ".absolute.bottom-full, [class*='bottom-full']",
        );
        await expect(dropdown).toBeVisible({ timeout: 5000 });
    });

    test("should hide dropdown when input is cleared", async ({ page }) => {
        const input = page.getByLabel("Chat input");
        await input.fill("/");

        // Wait for dropdown to appear
        const dropdown = page.locator(
            ".absolute.bottom-full, [class*='bottom-full']",
        );
        await expect(dropdown).toBeVisible({ timeout: 5000 });

        // Clear input
        await input.fill("");

        // Dropdown should disappear
        await expect(dropdown).not.toBeVisible({ timeout: 3000 });
    });
});
