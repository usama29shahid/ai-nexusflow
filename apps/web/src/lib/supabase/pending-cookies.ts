export type PendingCookie = {
    name: string;
    value: string;
    options?: {
        httpOnly?: boolean;
        secure?: boolean;
        sameSite?: boolean | "lax" | "strict" | "none";
        path?: string;
        maxAge?: number;
    };
};

/** Copy a refreshed session onto the response that the browser will actually receive. */
export function applyPendingCookies(pending: PendingCookie[], setCookie: (cookie: PendingCookie) => void) {
    for (const cookie of pending) {
        setCookie(cookie);
    }
}
