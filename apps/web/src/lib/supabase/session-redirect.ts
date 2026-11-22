const PROTECTED_PREFIXES = ["/dashboards", "/apps", "/pages", "/agentic"];

export function isProtectedPath(pathname: string): boolean {
    return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/** Where middleware should send this request, or null to continue. */
export function sessionRedirectPath(pathname: string, hasUser: boolean): string | null {
    if (!hasUser && isProtectedPath(pathname)) {
        return "/auth/login";
    }
    if (hasUser && (pathname === "/auth/login" || pathname === "/auth/register")) {
        return "/dashboards/ecommerce";
    }
    return null;
}
