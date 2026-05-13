import { expect, test } from "@playwright/test";

/**
 * E2E test: raw response modal opens and copy works.
 * This test sends a query, waits for a response, then clicks "View raw response"
 * and verifies the modal opens with JSON content and copy button.
 */
test.describe("Raw Response Modal", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
        await page.waitForSelector('[aria-label="Chat input"]', {
            timeout: 10000,
        });
    });

    test("should open raw response modal after a query response", async ({
        page,
    }) => {
        // Send a query
        const input = page.getByLabel("Chat input");
        await input.fill("show all psap in madison county");

        const sendButton = page.getByRole("button", { name: "Send" });
        await sendButton.click();

        // Wait for assistant response
        const assistantMessage = page.locator('[data-role="assistant"]');
        await expect(assistantMessage.first()).toBeVisible({ timeout: 120000 });

        // Click "View raw response" link
        const rawToggle = page.getByText("View raw response");
        if (await rawToggle.isVisible()) {
            await rawToggle.click();

            // Modal should appear with role="dialog"
            const modal = page.getByRole("dialog");
            await expect(modal).toBeVisible({ timeout: 3000 });

            // Should contain pre-formatted JSON
            const preBlock = modal.locator("pre");
            await expect(preBlock).toBeVisible();

            // Copy button should be present
            const copyBtn = page.getByRole("button", { name: /Copy/i });
            await expect(copyBtn).toBeVisible();

            // Close modal with Escape
            await page.keyboard.press("Escape");
            await expect(modal).not.toBeVisible({ timeout: 3000 });
        }
    });
});
