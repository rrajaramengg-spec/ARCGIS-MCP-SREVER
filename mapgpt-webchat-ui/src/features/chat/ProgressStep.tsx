interface ProgressStepProps {
    step: string;
}

export function ProgressStep({ step }: ProgressStepProps) {
    return (
        <div className="text-xs text-muted self-start px-3 py-1 italic">
            {step}
        </div>
    );
}
