// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  const Select = ({ options = [], value, onChange, "aria-label": ariaLabel }: { options?: { value: string; label: string }[]; value?: string; onChange?: (value: string) => void; "aria-label"?: string }) => <select aria-label={ariaLabel} value={value} onChange={(event) => onChange?.(event.target.value)}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>;
  return { ...actual, Select, Table: () => null };
});

import { ManagementCenter } from "./ManagementCenter";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", { value: () => ({ addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, matches: false }) });
});

function json(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.unstubAllGlobals());

describe("ManagementCenter", () => {
  it("keeps the generated temporary password visible after creating a member", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/api/admin/members") && init?.method === "POST") {
        return json({ username: "reviewer", display_name: "Reviewer", role: "member", is_active: true, must_change_password: true, temporary_password: "one-time-password" });
      }
      if (url.includes("audit-logs")) return json({ items: [], total: 0 });
      return json([]);
    }));

    render(<ManagementCenter open onClose={() => undefined} token="test-token" isSystemAdmin manageableProjects={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "新增成员" }));
    fireEvent.change(screen.getByLabelText("登录名"), { target: { value: "reviewer" } });
    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "Reviewer" } });
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(screen.getByText("one-time-password")).toBeTruthy());
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(document.querySelector(".ant-drawer-open")?.textContent).toContain("one-time-password");
  });
});
