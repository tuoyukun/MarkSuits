import { expect, test } from "@playwright/test";

async function addExpense(page, label, amount) {
  await page.getByTestId("new-label").fill(label);
  await page.getByTestId("new-amount").fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
}

test("empty list shows a hint and a zero total", async ({ page }) => {
  // covers: baseline/empty
  await page.goto("/");
  await addExpense(page, "Lunch", "12");
  await page.getByTestId("expense-delete").click();
  await expect(page.getByTestId("empty")).toBeVisible();
  await expect(page.getByTestId("total")).toHaveText("0.00");
});

test("add expenses, the total sums them and survives a reload", async ({ page }) => {
  // covers: baseline/add
  await page.goto("/");
  await addExpense(page, "Lunch", "12");
  await addExpense(page, "Train", "30");
  await expect(page.getByTestId("expense-label")).toHaveText(["Lunch", "Train"]);
  await expect(page.getByTestId("total")).toHaveText("42.00");
  await expect(page.getByTestId("new-label")).toHaveValue("");
  await page.reload();
  await expect(page.getByTestId("expense-amount")).toHaveText(["12.00", "30.00"]);
  await expect(page.getByTestId("total")).toHaveText("42.00");
});

test("an invalid amount is refused and kept for correction", async ({ page }) => {
  // covers: baseline/invalid
  await page.goto("/");
  await addExpense(page, "Lunch", "abc");
  await expect(page.getByTestId("form-error")).toBeVisible();
  await expect(page.getByTestId("new-amount")).toHaveValue("abc");
  await expect(page.getByTestId("empty")).toBeVisible();
});

test("delete removes one expense and updates the total", async ({ page }) => {
  // covers: baseline/delete
  await page.goto("/");
  await addExpense(page, "a", "5");
  await addExpense(page, "b", "7");
  await page.getByRole("button", { name: "Delete a" }).click();
  await expect(page.getByTestId("expense-label")).toHaveText(["b"]);
  await expect(page.getByTestId("total")).toHaveText("7.00");
});
