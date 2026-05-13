import { Button } from "@/components/Button";
import { Modal } from "@/components/Modal";
import type { ExecuteResponse } from "@/types/api";
import hljs from "highlight.js/lib/core";
import json from "highlight.js/lib/languages/json";
import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";

hljs.registerLanguage("json", json);

interface RawResponseModalProps {
    open: boolean;
    onClose: () => void;
    data: ExecuteResponse | null;
}

export function RawResponseModal({
    open,
    onClose,
    data,
}: RawResponseModalProps) {
    const [copied, setCopied] = useState(false);

    const jsonStr = data ? JSON.stringify(data, null, 2) : "";
    const highlighted = useMemo(
        () => (jsonStr ? hljs.highlight(jsonStr, { language: "json" }).value : ""),
        [jsonStr],
    );

    if (!data) return null;

    const action = data.action || "response";
    const layer = data.tool_name || "";
    const title = `Raw Response — ${action}${layer ? " · " + layer : ""}`;

    const handleCopy = () => {
        navigator.clipboard.writeText(jsonStr).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        });
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            title={title}
            actions={
                <Button variant="ghost" onClick={handleCopy}>
                    {copied ? <><Check size={16} className="inline mr-1" /> Copied</> : <><Copy size={16} className="inline mr-1" /> Copy</>}
                </Button>
            }
        >
            <pre className="whitespace-pre-wrap break-words text-xs font-mono">
                <code
                    className="hljs language-json"
                    dangerouslySetInnerHTML={{ __html: highlighted }}
                />
            </pre>
        </Modal>
    );
}
