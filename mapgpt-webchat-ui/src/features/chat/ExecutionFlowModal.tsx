import { Modal } from "@/components/Modal";
import type { ExecutionGraph, NodeTiming } from "@/types/api";
import {
    Background,
    Controls,
    Handle,
    Position,
    ReactFlow,
    type Edge,
    type Node
} from "@xyflow/react";
import {
    BarChart,
    Circle,
    Database,
    GitMerge,
    Hash,
    Layers,
    MapPin,
    Navigation,
} from "lucide-react";
import { useMemo } from "react";

interface ExecutionFlowModalProps {
    open: boolean;
    onClose: () => void;
    graph: ExecutionGraph | null;
}

const NODE_ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
    geocode: MapPin,
    query: Database,
    buffer_and_query: Circle,
    proximity: Navigation,
    union: GitMerge,
    spatial_join: Layers,
    summarize: BarChart,
    count: Hash,
};

/** Convert execution_graph to React Flow nodes/edges with horizontal layout. */
export function toReactFlowData(graph: ExecutionGraph): {
    nodes: Node[];
    edges: Edge[];
} {
    const timings = graph.node_timing || [];
    if (timings.length === 0) return { nodes: [], edges: [] };

    // Build adjacency for BFS level assignment
    const depMap = new Map<string, string[]>();
    const nodeMap = new Map<string, NodeTiming>();
    for (const nt of timings) {
        nodeMap.set(nt.node_id, nt);
        depMap.set(nt.node_id, nt.depends_on || []);
    }

    // BFS from roots to assign levels
    const levels = new Map<string, number>();
    const roots = timings.filter(
        (nt) => !nt.depends_on || nt.depends_on.length === 0,
    );
    const queue: Array<{ id: string; level: number }> = roots.map((r) => ({
        id: r.node_id,
        level: 0,
    }));

    while (queue.length > 0) {
        const { id, level } = queue.shift()!;
        const existing = levels.get(id);
        if (existing !== undefined && existing >= level) continue;
        levels.set(id, level);

        // Find dependents (nodes that depend on this one)
        for (const nt of timings) {
            if (nt.depends_on?.includes(id)) {
                queue.push({ id: nt.node_id, level: level + 1 });
            }
        }
    }

    // Group by level for vertical spacing
    const levelGroups = new Map<number, string[]>();
    for (const [id, level] of levels) {
        const group = levelGroups.get(level) || [];
        group.push(id);
        levelGroups.set(level, group);
    }

    // Compute which nodes have deps / dependents for Handle rendering
    const nodesWithDeps = new Set<string>();
    const nodesWithDependents = new Set<string>();
    for (const e of graph.edges || []) {
        nodesWithDeps.add(e.target);
        nodesWithDependents.add(e.source);
    }

    const nodes: Node[] = timings.map((nt) => {
        const level = levels.get(nt.node_id) || 0;
        const group = levelGroups.get(level) || [nt.node_id];
        const indexInGroup = group.indexOf(nt.node_id);

        return {
            id: nt.node_id,
            type: "executionNode",
            sourcePosition: Position.Right,
            targetPosition: Position.Left,
            position: { x: level * 250, y: indexInGroup * 100 },
            data: {
                label: nt.label || nt.node_id,
                nodeType: nt.node_type || "query",
                ms: nt.ms,
                status: nt.status || "ok",
                retries: nt.retries || 0,
                hasDeps: nodesWithDeps.has(nt.node_id),
                hasDependents: nodesWithDependents.has(nt.node_id),
            },
        };
    });

    const edges: Edge[] = (graph.edges || []).map((e) => ({
        id: `e-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        animated: true,
        style: { stroke: "#6366f1", strokeWidth: 2 },
        markerEnd: { type: "arrowclosed" as const, color: "#6366f1" },
    }));

    return { nodes, edges };
}

/** Custom node component for execution graph nodes. */
function ExecutionNodeComponent({ data }: { data: Record<string, unknown> }) {
    const nodeType = data.nodeType as string;
    const label = data.label as string;
    const ms = data.ms as number;
    const status = data.status as string;
    const retries = data.retries as number;
    const hasDeps = data.hasDeps as boolean;
    const hasDependents = data.hasDependents as boolean;
    const Icon = NODE_ICONS[nodeType] || Database;

    return (
        <div className="bg-surface border border-border rounded-lg shadow-sm px-3 py-2 min-w-[160px] max-w-[200px] relative">
            {hasDeps && (
                <Handle
                    type="target"
                    position={Position.Left}
                    style={{ background: "#6366f1", width: 8, height: 8 }}
                />
            )}
            <div className="flex items-center gap-2 mb-1">
                <Icon size={14} className="text-accent shrink-0" />
                <span className="text-xs font-medium text-text truncate">
                    {label}
                </span>
                <span
                    className={`w-2 h-2 rounded-full shrink-0 ${status === "ok" ? "bg-success" : "bg-error-fg"}`}
                />
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted">
                <span className="bg-surface-alt px-1.5 py-0.5 rounded">
                    {ms != null ? `${Math.round(ms)}ms` : "—"}
                </span>
                {retries > 0 && (
                    <span className="text-warning">
                        {retries} {retries === 1 ? "retry" : "retries"}
                    </span>
                )}
            </div>
            {hasDependents && (
                <Handle
                    type="source"
                    position={Position.Right}
                    style={{ background: "#6366f1", width: 8, height: 8 }}
                />
            )}
        </div>
    );
}

const nodeTypes = { executionNode: ExecutionNodeComponent };

export function ExecutionFlowModal({
    open,
    onClose,
    graph,
}: ExecutionFlowModalProps) {
    const { nodes, edges } = useMemo(
        () => (graph ? toReactFlowData(graph) : { nodes: [], edges: [] }),
        [graph],
    );

    if (!graph) return null;

    return (
        <Modal open={open} onClose={onClose} title="Execution Flow" fullScreen>
            <div style={{ width: "100%", height: "100%" }}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    nodeTypes={nodeTypes}
                    fitView
                    fitViewOptions={{ padding: 0.3 }}
                    attributionPosition="bottom-left"
                    nodesDraggable={false}
                    nodesConnectable={false}
                    elementsSelectable={false}
                    panOnDrag
                    zoomOnScroll
                    defaultEdgeOptions={{
                        type: "smoothstep",
                        animated: true,
                        style: { stroke: "#6366f1", strokeWidth: 2 },
                    }}
                >
                    <Background />
                    <Controls showInteractive={false} />
                </ReactFlow>
            </div>
        </Modal>
    );
}
