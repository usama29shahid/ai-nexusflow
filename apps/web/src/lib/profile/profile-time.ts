export function formatProfileWhen(iso: string | null, withTime: boolean, timeZone?: string): string {
    if (!iso) {
        return "Not recorded";
    }
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
        return "Not recorded";
    }
    return new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: withTime ? "short" : undefined,
        ...(timeZone ? { timeZone } : {}),
    }).format(date);
}
