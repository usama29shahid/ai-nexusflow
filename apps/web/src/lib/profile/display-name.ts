export const DISPLAY_NAME_MAX = 80;

export const DISPLAY_NAME_REQUIRED = "Enter a name.";
export const DISPLAY_NAME_TOO_LONG = `Use ${DISPLAY_NAME_MAX} characters or fewer.`;

/** Blank after trim, or longer than the profile column we accept. */
export function displayNameProblems(name: string): string | null {
    const trimmed = name.trim();
    if (!trimmed) {
        return DISPLAY_NAME_REQUIRED;
    }
    if (trimmed.length > DISPLAY_NAME_MAX) {
        return DISPLAY_NAME_TOO_LONG;
    }
    return null;
}

/** Saved name, otherwise the mailbox name, otherwise a generic label. */
export function profileDisplayName(displayName: string | null | undefined, email: string): string {
    const saved = displayName?.trim();
    if (saved) {
        return saved;
    }
    const mailbox = email.split("@")[0]?.trim();
    return mailbox || "Account";
}
