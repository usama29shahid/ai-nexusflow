const CLASSES = [
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "0123456789",
    "!@#%^&*()_+-=",
] as const;

export const PASSWORD_RULE =
    "Use at least 8 characters with a lowercase letter, an uppercase letter, a digit, and a symbol.";

export function passwordProblems(password: string): string | null {
    if (password.length < 8) {
        return PASSWORD_RULE;
    }
    for (const chars of CLASSES) {
        if (![...chars].some((char) => password.includes(char))) {
            return PASSWORD_RULE;
        }
    }
    return null;
}
