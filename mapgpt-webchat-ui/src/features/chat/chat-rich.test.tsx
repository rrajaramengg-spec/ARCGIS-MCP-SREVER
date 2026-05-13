import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FeatureSummary } from "./FeatureSummary";
import { FeatureTable } from "./FeatureTable";
import { FeedbackButtons } from "./FeedbackButtons";
import { LogsPanel } from "./LogsPanel";
import { RawResponseModal } from "./RawResponseModal";
import { useChatStore } from "@/stores/chat";
import type { LayerGroup } from "@/types/map";
import type { ExecuteResponse } from "@/types/api";

beforeEach(() => {
  useChatStore.setState({
    messages: [],
    logs: [],
    isThinking: false,
    progressStep: null,
    inputText: "",
    isSendDisabled: false,
  });
});

const mockLayer: LayerGroup = {
  name: "Fire Stations",
  features: [
    {
      attributes: { NAME: "Station 1", CITY: "Madison" },
      geometry: { x: -75, y: 40 },
    },
    {
      attributes: { NAME: "Station 2", CITY: "Troy" },
      geometry: { x: -74, y: 41 },
    },
  ],
  geometryType: "esriGeometryPoint",
  fields: [
    { name: "NAME", alias: "Station Name", type: "esriFieldTypeString" },
    { name: "CITY", alias: "City", type: "esriFieldTypeString" },
  ],
  spatialReference: { wkid: 4326 },
  role: "result",
  count: 2,
};

describe("FeatureSummary", () => {
  it("renders badges for layers", () => {
    render(<FeatureSummary layers={[mockLayer]} />);
    expect(screen.getByText("Fire Stations: 2")).toBeDefined();
  });

  it("shows empty message when all layers have zero features", () => {
    const emptyLayer: LayerGroup = { ...mockLayer, features: [], count: 0 };
    render(<FeatureSummary layers={[emptyLayer]} />);
    expect(screen.getByText("No features found")).toBeDefined();
  });

  it("renders buffer zone info", () => {
    const bufferLayer: LayerGroup = {
      ...mockLayer,
      bufferZone: true,
      features: [
        {
          attributes: { radius: 5, unit: "miles" },
          geometry: { rings: [] },
        },
      ],
    };
    render(<FeatureSummary layers={[bufferLayer]} />);
    expect(screen.getByText(/Buffer: 5 miles/)).toBeDefined();
  });

  it("returns null for empty layers array", () => {
    const { container } = render(<FeatureSummary layers={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("FeatureTable", () => {
  it("renders table headers using field aliases", () => {
    render(<FeatureTable layer={mockLayer} />);
    expect(screen.getByText("Station Name")).toBeDefined();
    expect(screen.getByText("City")).toBeDefined();
  });

  it("renders feature rows", () => {
    render(<FeatureTable layer={mockLayer} />);
    expect(screen.getByText("Station 1")).toBeDefined();
    expect(screen.getByText("Madison")).toBeDefined();
  });

  it("renders metadata header", () => {
    render(<FeatureTable layer={mockLayer} />);
    expect(
      screen.getByText(
        "Fire Stations · esriGeometryPoint · WKID: 4326 · 2 features",
      ),
    ).toBeDefined();
  });

  it("shows footer for more than 10 features", () => {
    const manyFeatures = Array.from({ length: 15 }, (_, i) => ({
      attributes: { NAME: `Station ${i}`, CITY: "City" },
      geometry: { x: 0, y: 0 },
    }));
    const bigLayer: LayerGroup = {
      ...mockLayer,
      features: manyFeatures,
      count: 15,
    };
    render(<FeatureTable layer={bigLayer} />);
    expect(screen.getByText("Showing 10 of 15")).toBeDefined();
  });

  it("returns null for empty features", () => {
    const empty: LayerGroup = { ...mockLayer, features: [] };
    const { container } = render(<FeatureTable layer={empty} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("FeedbackButtons", () => {
  it("renders thumbs up and down buttons", () => {
    render(<FeedbackButtons queryId="q1" />);
    expect(screen.getByLabelText("Thumbs up")).toBeDefined();
    expect(screen.getByLabelText("Thumbs down")).toBeDefined();
  });

  it("disables buttons after click", async () => {
    const user = userEvent.setup();
    // Mock fetch
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true });
    render(<FeedbackButtons queryId="q1" />);
    await user.click(screen.getByLabelText("Thumbs up"));
    expect(screen.getByLabelText("Thumbs up")).toBeDisabled();
    expect(screen.getByLabelText("Thumbs down")).toBeDisabled();
  });
});

describe("LogsPanel", () => {
  it("renders toggle bar", () => {
    render(<LogsPanel />);
    expect(screen.getByLabelText("Expand logs")).toBeDefined();
  });

  it("shows logs when expanded", async () => {
    const user = userEvent.setup();
    useChatStore.getState().addLog("info", "Connected to server");
    render(<LogsPanel />);
    await user.click(screen.getByLabelText("Expand logs"));
    expect(screen.getByText("Connected to server")).toBeDefined();
  });

  it("clears logs", async () => {
    const user = userEvent.setup();
    useChatStore.getState().addLog("info", "Test log");
    render(<LogsPanel />);
    await user.click(screen.getByLabelText("Expand logs"));
    await user.click(screen.getByText("Clear"));
    expect(screen.queryByText("Test log")).toBeNull();
  });
});

describe("RawResponseModal", () => {
  const mockResponse: ExecuteResponse = {
    action: "query",
    message: "Found 2 features",
    data: null,
    results: [],
    execution_time_ms: 100,
    timing: { total_ms: 100 },
    query_id: "q1",
    tool_name: "query_features",
    tool_args: {},
  };

  it("renders nothing when closed", () => {
    const { container } = render(
      <RawResponseModal open={false} onClose={() => {}} data={mockResponse} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders modal with JSON when open", () => {
    render(
      <RawResponseModal open={true} onClose={() => {}} data={mockResponse} />,
    );
    expect(
      screen.getByText("Raw Response — query · query_features"),
    ).toBeDefined();
  });

  it("renders null when data is null", () => {
    const { container } = render(
      <RawResponseModal open={true} onClose={() => {}} data={null} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
