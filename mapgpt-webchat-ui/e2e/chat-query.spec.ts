import { expect, test } from "@playwright/test";

/**
 * E2E test: send a query and verify an assistant message appears.
 * Requires the Docker Compose stack running with --profile demo.
 */
test.describe("Chat Query Flow", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
        // Wait for the app to render
        await page.waitForSelector('[aria-label="Chat input"]', {
            timeout: 10000,
        });
    });

    test("should display the chat input and send button", async ({ page }) => {
        const input = page.getByLabel("Chat input");
        await expect(input).toBeVisible();

        const sendButton = page.getByRole("button", { name: "Send" });
        await expect(sendButton).toBeVisible();
    });

    test("should send a query and receive an assistant response", async ({
        page,
    }) => {
        const input = page.getByLabel("Chat input");
        await input.fill("show all psap in madison county");

        const sendButton = page.getByRole("button", { name: "Send" });
        await sendButton.click();

        // The user message should appear
        const userMessage = page.locator('[data-role="user"]');
        await expect(userMessage.first()).toBeVisible({ timeout: 5000 });

        // Wait for an assistant response (may take a while for LLM + ArcGIS calls)
        const assistantMessage = page.locator('[data-role="assistant"]');
        await expect(assistantMessage.first()).toBeVisible({ timeout: 120000 });
    });

    test("should disable input while processing", async ({ page }) => {
        const input = page.getByLabel("Chat input");
        await input.fill("show all psap");

        const sendButton = page.getByRole("button", { name: "Send" });
        await sendButton.click();

        // Send button should be disabled while processing
        // (we check quickly before the response comes back)
        await expect(sendButton).toBeDisabled({ timeout: 2000 });
    });
});
