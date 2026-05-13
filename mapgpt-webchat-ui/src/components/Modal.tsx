import { X } from "lucide-react";
import { useCallback, useEffect, type ReactNode } from "react";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    actions?: ReactNode;
    children: ReactNode;
    fullScreen?: boolean;
}

export function Modal({ open, onClose, title, actions, children, fullScreen }: ModalProps) {
    const handleKeyDown = useCallback(
        (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        },
        [onClose],
    );

    useEffect(() => {
        if (open) {
            document.addEventListener("keydown", handleKeyDown);
            return () => document.removeEventListener("keydown", handleKeyDown);
        }
    }, [open, handleKeyDown]);

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <div className={fullScreen
                ? "bg-surface border border-border rounded-xl shadow-lg w-[96vw] h-[92vh] flex flex-col"
                : "bg-surface border border-border rounded-xl shadow-lg max-w-3xl w-[90vw] max-h-[80vh] flex flex-col"
            }>
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                    <span className="font-semibold text-text">{title}</span>
                    <div className="flex items-center gap-2">
                        {actions}
                        <button
                            onClick={onClose}
                            className="text-muted hover:text-text cursor-pointer bg-transparent border-none p-1 rounded-lg hover:bg-surface-alt transition-all duration-150"
                            aria-label="Close"
                        >
                            <X size={18} />
                        </button>
                    </div>
                </div>
                <div className={`${fullScreen ? "flex-1 overflow-hidden" : "overflow-auto"} p-4 text-sm`}>{children}</div>
            </div>
        </div>
    );
}
