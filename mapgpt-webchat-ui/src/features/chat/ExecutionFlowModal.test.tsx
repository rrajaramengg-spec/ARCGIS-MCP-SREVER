import type { ExecutionGraph } from "@/types/api";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ExecutionFlowModal, toReactFlowData } from "./ExecutionFlowModal";

// Mock @xyflow/react since it requires DOM measuring
vi.mock("@xyflow/react", () => ({
    ReactFlow: ({ children, nodes, edges }: { children: React.ReactNode; nodes: unknown[]; edges: unknown[] }) => (
        <div data-testid="react-flow" data-nodes={nodes.length} data-edges={edges.length}>
            {children}
        </div>
    ),
    Background: () => <div data-testid="rf-background" />,
    Controls: () => <div data-testid="rf-controls" />,
    Handle: ({ type, position }: { type: string; position: string }) => (
        <div data-testid={`handle-${type}`} data-position={position} />
    ),
    Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}));

const mockGraph: ExecutionGraph = {
    nodes_executed: 2,
    parallel_groups: 1,
    node_timing: [
        { node_id: "n0", node_type: "geocode", ms: 100, status: "ok", depends_on: [], label: "Geocode '123 Main'" },
        { node_id: "n1", node_type: "query", ms: 250, status: "ok", depends_on: ["n0"], label: "Query PSAP" },
    ],
    edges: [{ source: "n0", target: "n1" }],
};

describe("toReactFlowData", () => {
    it("converts nodes with horizontal layout", () => {
        const { nodes, edges } = toReactFlowData(mockGraph);
        expect(nodes).toHaveLength(2);
        expect(edges).toHaveLength(1);

        // Root node at level 0
        const n0 = nodes.find((n) => n.id === "n0");
        expect(n0?.position.x).toBe(0);

        // Dependent node at level 1
        const n1 = nodes.find((n) => n.id === "n1");
        expect(n1?.position.x).toBe(250);
    });

    it("handles empty graph", () => {
        const { nodes, edges } = toReactFlowData({ node_timing: [] });
        expect(nodes).toHaveLength(0);
        expect(edges).toHaveLength(0);
    });

    it("assigns correct data to nodes", () => {
        const { nodes } = toReactFlowData(mockGraph);
        const n0 = nodes.find((n) => n.id === "n0");
        expect(n0?.data.label).toBe("Geocode '123 Main'");
        expect(n0?.data.nodeType).toBe("geocode");
        expect(n0?.data.ms).toBe(100);
    });

    it("creates smoothstep animated edges", () => {
        const { edges } = toReactFlowData(mockGraph);
        expect(edges[0].type).toBe("smoothstep");
        expect(edges[0].animated).toBe(true);
        expect(edges[0].source).toBe("n0");
        expect(edges[0].target).toBe("n1");
    });

    it("edges have stroke style and arrow marker", () => {
        const { edges } = toReactFlowData(mockGraph);
        expect(edges[0].style).toEqual({ stroke: "#6366f1", strokeWidth: 2 });
        expect(edges[0].markerEnd).toEqual({ type: "arrowclosed", color: "#6366f1" });
    });

    it("sets hasDeps and hasDependents flags on nodes", () => {
        const { nodes } = toReactFlowData(mockGraph);
        const n0 = nodes.find((n) => n.id === "n0");
        const n1 = nodes.find((n) => n.id === "n1");
        // n0 is root (no deps) but has dependents (n1 depends on it)
        expect(n0?.data.hasDeps).toBe(false);
        expect(n0?.data.hasDependents).toBe(true);
        // n1 depends on n0 but nothing depends on n1
        expect(n1?.data.hasDeps).toBe(true);
        expect(n1?.data.hasDependents).toBe(false);
    });
});

describe("ExecutionFlowModal", () => {
    it("renders nothing when graph is null", () => {
        const { container } = render(
            <ExecutionFlowModal open={true} onClose={vi.fn()} graph={null} />,
        );
        expect(container.innerHTML).toBe("");
    });

    it("renders modal with ReactFlow when graph is provided", () => {
        render(
            <ExecutionFlowModal open={true} onClose={vi.fn()} graph={mockGraph} />,
        );
        expect(screen.getByText("Execution Flow")).toBeDefined();
        expect(screen.getByTestId("react-flow")).toBeDefined();
    });

    it("renders nothing when closed", () => {
        const { container } = render(
            <ExecutionFlowModal open={false} onClose={vi.fn()} graph={mockGraph} />,
        );
        expect(container.innerHTML).toBe("");
    });

    it("renders fullscreen modal with controls", () => {
        render(
            <ExecutionFlowModal open={true} onClose={vi.fn()} graph={mockGraph} />,
        );
        // Modal should use fullScreen prop — check for 96vw class
        const dialog = screen.getByRole("dialog");
        const panel = dialog.querySelector("[class*='96vw']");
        expect(panel).toBeTruthy();
        // Controls should be rendered
        expect(screen.getByTestId("rf-controls")).toBeDefined();
    });
});
