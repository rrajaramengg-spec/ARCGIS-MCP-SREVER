export function ThinkingIndicator() {
    return (
        <div className="flex gap-1 items-center self-start px-3 py-2" aria-label="Thinking">
            <span className="w-2 h-2 rounded-full bg-muted animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 rounded-full bg-muted animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 rounded-full bg-muted animate-bounce [animation-delay:300ms]" />
        </div>
    );
}
