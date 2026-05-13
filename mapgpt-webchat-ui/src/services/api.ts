/** HTTP API service — ported from static/js/api.js */

import { API_COMMANDS, API_RESOURCES } from "@/features/map/utils/constants";
import type { Command, Resource } from "@/types/chat";

let cachedCommands: Command[] | null = null;

/** Fetch slash commands from /api/commands. Results are cached after first call. */
export async function fetchCommands(): Promise<Command[]> {
    if (cachedCommands) return cachedCommands;
    try {
        const resp = await fetch(API_COMMANDS);
        const cmds: unknown = await resp.json();
        if (Array.isArray(cmds)) {
            cachedCommands = cmds as Command[];
            return cachedCommands;
        }
    } catch {
        // Silently fail — commands are optional
    }
    return [];
}

/** Fetch resources from /api/resources. */
export async function fetchResources(): Promise<Resource[]> {
    try {
        const resp = await fetch(API_RESOURCES);
        const resources: unknown = await resp.json();
        if (Array.isArray(resources)) return resources as Resource[];
    } catch {
        // Silently fail — resources are optional
    }
    return [];
}

/** Clear the command cache (useful for testing). */
export function clearCommandCache(): void {
    cachedCommands = null;
}
