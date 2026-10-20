import { expect, test } from "@playwright/test";

// The server keeps todos in memory for its whole run, so each test starts by
// deleting whatever the previous one left.
test.beforeEach(async ({ request }) => {
  const todos = await (await request.get("/api/todos")).json();
  for (const todo of todos) await request.delete(`/api/todos/${todo.id}`);
});

test("empty list shows a hint", async ({ page }) => {
  // covers: baseline/empty
  await page.goto("/");
  await page.getByTestId("new-todo").fill("first");
  await page.getByTestId("new-todo").press("Enter");
  await page.getByTestId("todo-delete").click();
  await expect(page.getByTestId("empty")).toBeVisible();
});

test("add a todo and it survives a reload", async ({ page }) => {
  // covers: baseline/add
  await page.goto("/");
  await page.getByTestId("new-todo").fill("  Buy   milk ");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByTestId("todo-title")).toHaveText(["Buy milk"]);
  await expect(page.getByTestId("new-todo")).toHaveValue("");
  await page.reload();
  await expect(page.getByTestId("todo-title")).toHaveText(["Buy milk"]);
});

test("blank input adds nothing", async ({ page }) => {
  // covers: baseline/blank
  await page.goto("/");
  await page.getByTestId("new-todo").fill("   ");
  await page.getByTestId("new-todo").press("Enter");
  await expect(page.getByTestId("empty")).toBeVisible();
});

test("toggle marks a todo done", async ({ page }) => {
  // covers: baseline/toggle
  await page.goto("/");
  await page.getByTestId("new-todo").fill("Walk dog");
  await page.getByTestId("new-todo").press("Enter");
  await page.getByTestId("todo-toggle").check();
  await expect(page.getByTestId("todo-item")).toHaveAttribute("data-done", "true");
});

test("delete removes a todo", async ({ page }) => {
  // covers: baseline/delete
  await page.goto("/");
  for (const title of ["a", "b"]) {
    await page.getByTestId("new-todo").fill(title);
    await page.getByTestId("new-todo").press("Enter");
  }
  await page.getByRole("button", { name: "Delete a" }).click();
  await expect(page.getByTestId("todo-title")).toHaveText(["b"]);
});
