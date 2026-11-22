import { NextResponse, type NextRequest } from "next/server.js";

import { applyPendingCookies, type PendingCookie } from "./pending-cookies.ts";

export function redirectKeepingCookies(request: NextRequest, pathname: string, pending: PendingCookie[]) {
    const destination = request.nextUrl.clone();
    destination.pathname = pathname;
    const redirectResponse = NextResponse.redirect(destination);
    applyPendingCookies(pending, ({ name, value, options }) => {
        redirectResponse.cookies.set(name, value, options);
    });
    return redirectResponse;
}
