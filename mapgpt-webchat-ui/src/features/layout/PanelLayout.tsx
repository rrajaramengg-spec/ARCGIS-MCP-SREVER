import { Maximize2, Minimize2 } from "lucide-react";
import type { ReactNode } from "react";

export type LayoutMode = "default" | "chat-max" | "map-max";

interface PanelLayoutProps {
    mode: LayoutMode;
    onToggleChat: () => void;
    onToggleMap: () => void;
    chatPanel: ReactNode;
    mapPanel: ReactNode;
}

export function PanelLayout({
    mode,
    onToggleChat,
    onToggleMap,
    chatPanel,
    mapPanel,
}: PanelLayoutProps) {
    const chatHidden = mode === "map-max";
    const mapHidden = mode === "chat-max";

    return (
        <div className="flex flex-1 overflow-hidden">
            {/* Chat panel */}
            <div
                className={`relative flex flex-col border-r border-border transition-all ${chatHidden
                    ? "w-0 overflow-hidden"
                    : mapHidden
                        ? "w-full"
                        : "w-1/2"
                    }`}
            >
                <button
                    className="absolute top-1 right-1 z-10 text-muted hover:text-text cursor-pointer bg-transparent border-none p-1 rounded-lg hover:bg-surface-alt transition-all duration-150"
                    onClick={onToggleChat}
                    title={mode === "chat-max" ? "Restore panels" : "Maximize chat"}
                    aria-label={mode === "chat-max" ? "Restore panels" : "Maximize chat"}
                >
                    {mode === "chat-max" ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                </button>
                {chatPanel}
            </div>

            {/* Map panel */}
            <div
                className={`relative flex flex-col transition-all ${mapHidden
                    ? "w-0 overflow-hidden"
                    : chatHidden
                        ? "w-full"
                        : "w-1/2"
                    }`}
            >
                <button
                    className="absolute top-1 left-1 z-10 text-muted hover:text-text cursor-pointer bg-transparent border-none p-1 rounded-lg hover:bg-surface-alt transition-all duration-150"
                    onClick={onToggleMap}
                    title={mode === "map-max" ? "Restore panels" : "Maximize map"}
                    aria-label={mode === "map-max" ? "Restore panels" : "Maximize map"}
                >
                    {mode === "map-max" ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                </button>
                {mapPanel}
            </div>
        </div>
    );
}
