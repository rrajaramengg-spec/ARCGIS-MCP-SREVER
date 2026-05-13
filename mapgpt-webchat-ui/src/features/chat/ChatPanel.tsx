import { useChatStore } from "@/stores/chat";
import { useWebSocketStore } from "@/stores/websocket";
import { useCallback } from "react";
import { AssistantMessage } from "./AssistantMessage";
import { ChatInput } from "./ChatInput";
import { CommandDropdown } from "./CommandDropdown";
import { LogsPanel } from "./LogsPanel";
import { MessageBubble } from "./MessageBubble";
import { MessageList } from "./MessageList";
import { ProgressStep } from "./ProgressStep";
import { ThinkingIndicator } from "./ThinkingIndicator";

interface ChatPanelProps {
    onZoomToQuery?: (queryId: string) => void;
    onZoomToLocate?: (x: number, y: number) => void;
}

export function ChatPanel({ onZoomToQuery, onZoomToLocate }: ChatPanelProps) {
    const messages = useChatStore((s) => s.messages);
    const isThinking = useChatStore((s) => s.isThinking);
    const progressStep = useChatStore((s) => s.progressStep);
    const inputText = useChatStore((s) => s.inputText);

    const handleSend = useCallback(
        (text: string) => {
            const send = useWebSocketStore.getState().send;
            const { addUserMessage, setThinking, setSendDisabled } =
                useChatStore.getState();

            addUserMessage(text);
            setThinking(true);
            setSendDisabled(true);
            send(text);
        },
        [],
    );

    return (
        <div className="flex flex-col flex-1 overflow-hidden">
            <MessageList>
                {/* Welcome message */}
                <MessageBubble role="system">
                    Welcome to MapGPT Chat! Type a question about your spatial data.
                </MessageBubble>

                {/* Messages */}
                {messages.map((msg) => {
                    if (msg.role === "assistant") {
                        return (
                            <AssistantMessage
                                key={msg.id}
                                message={msg}
                                onZoomToQuery={onZoomToQuery}
                                onZoomToLocate={onZoomToLocate}
                            />
                        );
                    }
                    return (
                        <MessageBubble key={msg.id} role={msg.role}>
                            {msg.text}
                        </MessageBubble>
                    );
                })}

                {/* Thinking + progress */}
                {isThinking && <ThinkingIndicator />}
                {progressStep && <ProgressStep step={progressStep} />}
            </MessageList>

            {/* Input area with command dropdown */}
            <div className="relative">
                <CommandDropdown inputText={inputText} />
                <ChatInput onSend={handleSend} />
            </div>

            {/* Logs */}
            <LogsPanel />
        </div>
    );
}
