import { useCallback, useState, type ReactNode } from "react";
import { Header } from "./Header";
import { PanelLayout, type LayoutMode } from "./PanelLayout";

interface AppShellProps {
    chatPanel: ReactNode;
    mapPanel: ReactNode;
}

export function AppShell({ chatPanel, mapPanel }: AppShellProps) {
    const [layoutMode, setLayoutMode] = useState<LayoutMode>("default");

    const toggleChat = useCallback(() => {
        setLayoutMode((m) => (m === "chat-max" ? "default" : "chat-max"));
    }, []);

    const toggleMap = useCallback(() => {
        setLayoutMode((m) => (m === "map-max" ? "default" : "map-max"));
    }, []);

    return (
        <div className="flex flex-col h-screen bg-bg text-text">
            <Header />
            <PanelLayout
                mode={layoutMode}
                onToggleChat={toggleChat}
                onToggleMap={toggleMap}
                chatPanel={chatPanel}
                mapPanel={mapPanel}
            />
        </div>
    );
}
