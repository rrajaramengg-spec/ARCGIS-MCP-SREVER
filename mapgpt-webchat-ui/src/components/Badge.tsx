interface BadgeProps {
    children: React.ReactNode;
    color?: "primary" | "parent" | "child" | "result" | "buffer" | "muted";
    className?: string;
}

const colorClasses: Record<NonNullable<BadgeProps["color"]>, string> = {
    primary: "bg-accent/15 text-accent",
    parent: "bg-accent/10 text-accent-hi",
    child: "bg-success/15 text-success",
    result: "bg-accent/15 text-accent",
    buffer: "bg-muted/15 text-muted",
    muted: "bg-muted/10 text-muted",
};

export function Badge({
    children,
    color = "primary",
    className = "",
}: BadgeProps) {
    return (
        <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colorClasses[color]} ${className}`}
        >
            {children}
        </span>
    );
}
