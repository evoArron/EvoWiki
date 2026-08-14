// @vitest-environment jsdom
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const initialize = vi.fn();
const renderDiagram = vi.fn().mockResolvedValue({ svg: "<svg />" });

vi.mock("mermaid", () => ({ default: { initialize, render: renderDiagram } }));

import { MermaidDiagram } from "./App";

describe("MermaidDiagram", () => {
  it("does not load Mermaid until its details element opens", async () => {
    const { container } = render(<MermaidDiagram chart="graph TD; A-->B" />);
    const details = container.querySelector("details")!;

    expect(initialize).not.toHaveBeenCalled();
    details.open = true;
    fireEvent(details, new Event("toggle"));

    await waitFor(() => expect(initialize).toHaveBeenCalledOnce());
  });
});
