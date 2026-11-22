export function isSecureRequest(forwardedProto: string | null): boolean {
    return forwardedProto?.split(",")[0]?.trim().toLowerCase() === "https";
}

export function authCookieOptions(secure: boolean) {
    return {
        path: "/",
        sameSite: "lax" as const,
        httpOnly: true,
        secure,
    };
}
