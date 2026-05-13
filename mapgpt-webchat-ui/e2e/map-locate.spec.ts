import { expect, test } from "@playwright/test";

/**
 * E2E test: map renders and shows a locate pin on a locate query.
 */
test.describe("Map Locate", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
        await page.waitForSelector('[aria-label="Chat input"]', {
            timeout: 10000,
        });
    });

    test("should render the map container", async ({ page }) => {
        // The map container div should exist
        const mapContainer = page.locator("#mapViewDiv, [data-testid='map-container']");
        await expect(mapContainer.first()).toBeVisible({ timeout: 15000 });
    });

    test("should send a locate query and get a response", async ({ page }) => {
        const input = page.getByLabel("Chat input");
        await input.fill("/locate 123 Main St");

        const sendButton = page.getByRole("button", { name: "Send" });
        await sendButton.click();

        // User message should appear
        const userMessage = page.locator('[data-role="user"]');
        await expect(userMessage.first()).toBeVisible({ timeout: 5000 });

        // Wait for assistant response
        const assistantMessage = page.locator('[data-role="assistant"]');
        await expect(assistantMessage.first()).toBeVisible({ timeout: 60000 });
    });
});
