import { fetchCommands, fetchResources } from "@/services/api";
import { useChatStore } from "@/stores/chat";
import type { Command, Resource } from "@/types/chat";
import { useEffect, useState } from "react";

interface CommandDropdownProps {
    inputText: string;
}

type DropdownItem = { label: string; value: string };

export function CommandDropdown({ inputText }: CommandDropdownProps) {
    const [items, setItems] = useState<DropdownItem[]>([]);
    const [visible, setVisible] = useState(false);
    const setInputText = useChatStore((s) => s.setInputText);

    useEffect(() => {
        let cancelled = false;

        async function sync() {
            if (inputText.startsWith("/")) {
                const cmds: Command[] = await fetchCommands();
                if (cancelled) return;
                const typed = inputText.toLowerCase();
                const filtered = cmds.filter(
                    (c) =>
                        c.name.toLowerCase().startsWith(typed) || typed === "/",
                );
                if (filtered.length > 0) {
                    setItems(
                        filtered.map((c) => ({
                            label: `${c.name} — ${c.description}`,
                            value: c.name + " ",
                        })),
                    );
                    setVisible(true);
                } else {
                    setVisible(false);
                }
            } else if (inputText === "@") {
                const resources: Resource[] = await fetchResources();
                if (cancelled) return;
                if (resources.length > 0) {
                    setItems(
                        resources.map((r) => ({
                            label: r.name || r.uri || String(r),
                            value: inputText + (r.uri || r.name || ""),
                        })),
                    );
                    setVisible(true);
                } else {
                    setVisible(false);
                }
            } else {
                setVisible(false);
            }
        }

        sync();
        return () => {
            cancelled = true;
        };
    }, [inputText]);

    const handleSelect = (item: DropdownItem) => {
        setInputText(item.value);
        setVisible(false);
    };

    if (!visible || items.length === 0) return null;

    return (
        <div className="absolute bottom-full left-0 right-0 bg-surface border border-border rounded-xl shadow-lg max-h-48 overflow-y-auto z-20">
            {items.map((item, i) => (
                <button
                    key={i}
                    className="w-full text-left px-3 py-2 text-sm text-text hover:bg-accent/10 cursor-pointer border-none bg-transparent"
                    onClick={() => handleSelect(item)}
                >
                    {item.label}
                </button>
            ))}
        </div>
    );
}
