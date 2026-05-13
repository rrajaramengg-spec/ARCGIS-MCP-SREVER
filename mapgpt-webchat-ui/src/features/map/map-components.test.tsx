import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// Mock the hooks since they depend on ArcGIS CDN
vi.mock("./hooks/useMapView", () => ({
    useMapView: () => ({
        containerRef: { current: document.createElement("div") },
        getView: () => null,
        getModules: () => null,
        isReady: false,
    }),
}));

vi.mock("./hooks/useGraphicsLayers", () => ({
    useGraphicsLayers: () => ({
        addQueryLayer: vi.fn(),
        addLocatePin: vi.fn(),
        clearAllLayers: vi.fn(),
        zoomToLocate: vi.fn(),
        zoomToQuery: vi.fn(),
    }),
}));

// Import after mocks
import { LocationPicker } from "./LocationPicker";
import { MapPanel } from "./MapPanel";
import { MapViewComponent } from "./MapView";

describe("MapViewComponent", () => {
    it("shows loading state when not ready", () => {
        render(<MapViewComponent />);
        expect(screen.getByText("Loading map…")).toBeDefined();
    });
});

describe("MapPanel", () => {
    it("renders map header and clear button", () => {
        render(<MapPanel />);
        expect(screen.getByText("Map")).toBeDefined();
        expect(screen.getByText("Clear Map")).toBeDefined();
    });
});

describe("LocationPicker", () => {
    it("renders pick button", () => {
        render(
            <LocationPicker getView={() => null} getModules={() => null} />,
        );
        expect(screen.getByText(/Pick/)).toBeDefined();
    });

    it("toggles to Cancel state on click", async () => {
        const user = userEvent.setup();
        render(
            <LocationPicker getView={() => null} getModules={() => null} />,
        );
        await user.click(screen.getByText(/Pick/));
        expect(screen.getByText(/Cancel/)).toBeDefined();
    });
});
