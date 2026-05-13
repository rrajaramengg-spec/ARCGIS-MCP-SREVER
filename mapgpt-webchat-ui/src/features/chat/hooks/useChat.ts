import { useChatStore } from "@/stores/chat";

/** Thin convenience hook wrapping useChatStore selectors. */
export function useChat() {
    const messages = useChatStore((s) => s.messages);
    const isThinking = useChatStore((s) => s.isThinking);
    const progressStep = useChatStore((s) => s.progressStep);
    const inputText = useChatStore((s) => s.inputText);
    const isSendDisabled = useChatStore((s) => s.isSendDisabled);

    const {
        addUserMessage,
        addAssistantMessage,
        addErrorMessage,
        clearMessages,
        setThinking,
        setProgressStep,
        setInputText,
        appendInputText,
        setSendDisabled,
    } = useChatStore.getState();

    return {
        messages,
        isThinking,
        progressStep,
        inputText,
        isSendDisabled,
        addUserMessage,
        addAssistantMessage,
        addErrorMessage,
        clearMessages,
        setThinking,
        setProgressStep,
        setInputText,
        appendInputText,
        setSendDisabled,
    };
}
