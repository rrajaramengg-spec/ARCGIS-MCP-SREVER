import { useWebSocketStore } from "@/stores/websocket";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

interface FeedbackButtonsProps {
    queryId: string;
}

export function FeedbackButtons({ queryId }: FeedbackButtonsProps) {
    const [submitted, setSubmitted] = useState<"up" | "down" | null>(null);
    const [disabled, setDisabled] = useState(false);

    const handleFeedback = async (feedback: "up" | "down") => {
        setDisabled(true);
        setSubmitted(feedback);

        try {
            const sessionId = useWebSocketStore.getState().sessionId;
            const resp = await fetch("/api/user-feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    query_id: String(queryId),
                    feedback,
                }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        } catch {
            // Revert on failure
            setDisabled(false);
            setSubmitted(null);
        }
    };

    return (
        <div className="flex items-center gap-1 mt-1">
            <button
                onClick={() => handleFeedback("up")}
                disabled={disabled}
                className={`text-sm px-1.5 py-0.5 rounded cursor-pointer border-none bg-transparent hover:bg-success/10 disabled:cursor-not-allowed ${submitted === "up" ? "bg-success/20" : ""
                    }`}
                title="Helpful response"
                aria-label="Thumbs up"
            >
                <ThumbsUp size={14} />
            </button>
            <button
                onClick={() => handleFeedback("down")}
                disabled={disabled}
                className={`text-sm px-1.5 py-0.5 rounded cursor-pointer border-none bg-transparent hover:bg-error-bg disabled:cursor-not-allowed ${submitted === "down" ? "bg-error-bg" : ""
                    }`}
                title="Not helpful"
                aria-label="Thumbs down"
            >
                <ThumbsDown size={14} />
            </button>
        </div>
    );
}
