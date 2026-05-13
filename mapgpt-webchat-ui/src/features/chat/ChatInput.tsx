import { Button } from "@/components/Button";
import { useChatStore } from "@/stores/chat";
import { Send } from "lucide-react";

interface ChatInputProps {
    onSend: (text: string) => void;
    onInputChange?: (text: string) => void;
}

export function ChatInput({ onSend, onInputChange }: ChatInputProps) {
    const inputText = useChatStore((s) => s.inputText);
    const isSendDisabled = useChatStore((s) => s.isSendDisabled);
    const setInputText = useChatStore((s) => s.setInputText);

    const handleSend = () => {
        const text = inputText.trim();
        if (!text || isSendDisabled) return;
        onSend(text);
        setInputText("");
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setInputText(val);
        onInputChange?.(val);
    };

    return (
        <div className="flex items-center gap-2 p-3 border-t border-border">
            <input
                type="text"
                value={inputText}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your spatial data... (type / for commands)"
                autoComplete="off"
                className="flex-1 px-4 py-2 bg-bg border border-border rounded-[24px] text-sm text-text placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent shadow-sm focus:shadow-md transition-shadow"
                aria-label="Chat input"
            />
            <Button
                onClick={handleSend}
                disabled={isSendDisabled || !inputText.trim()}
                className="!rounded-full !p-2.5"
                aria-label="Send"
            >
                <Send size={18} />
            </Button>
        </div>
    );
}
