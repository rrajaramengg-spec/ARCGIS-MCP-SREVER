import { type ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "ghost" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
    primary:
        "bg-accent text-white px-4 py-2 rounded-[24px] shadow-sm hover:bg-accent-hi disabled:opacity-50 disabled:cursor-not-allowed",
    ghost:
        "bg-transparent text-accent px-3 py-1.5 rounded-lg hover:bg-accent-soft disabled:opacity-50 disabled:cursor-not-allowed",
    icon: "bg-transparent text-muted p-1.5 rounded-lg hover:text-text hover:bg-surface-alt disabled:opacity-50 disabled:cursor-not-allowed",
};

export function Button({
    variant = "primary",
    className = "",
    children,
    ...props
}: ButtonProps) {
    return (
        <button
            className={`${variantClasses[variant]} transition-all duration-150 cursor-pointer text-sm font-medium ${className}`}
            {...props}
        >
            {children}
        </button>
    );
}
