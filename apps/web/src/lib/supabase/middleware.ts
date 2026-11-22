import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { authCookieOptions, isSecureRequest } from "@/lib/supabase/cookie-options";
import { type PendingCookie } from "@/lib/supabase/pending-cookies";
import { redirectKeepingCookies } from "@/lib/supabase/redirect-response";
import { sessionRedirectPath } from "@/lib/supabase/session-redirect";

export async function updateSession(request: NextRequest) {
    const url = process.env.SUPABASE_URL ?? "";
    const anonKey = process.env.SUPABASE_ANON_KEY ?? "";
    const secure = isSecureRequest(request.headers.get("x-forwarded-proto"));
    let response = NextResponse.next({ request });
    let pendingCookies: PendingCookie[] = [];

    const redirectTo = (pathname: string) => redirectKeepingCookies(request, pathname, pendingCookies);

    if (!url || !anonKey) {
        const pathname = sessionRedirectPath(request.nextUrl.pathname, false);
        return pathname ? redirectTo(pathname) : response;
    }

    const supabase = createServerClient(url, anonKey, {
        cookieOptions: authCookieOptions(secure),
        cookies: {
            getAll() {
                return request.cookies.getAll();
            },
            setAll(cookiesToSet) {
                pendingCookies = cookiesToSet;
                cookiesToSet.forEach(({ name, value }) => {
                    request.cookies.set(name, value);
                });
                response = NextResponse.next({ request });
                cookiesToSet.forEach(({ name, value, options }) => {
                    response.cookies.set(name, value, options);
                });
            },
        },
    });

    const { data } = await supabase.auth.getUser();
    const pathname = sessionRedirectPath(request.nextUrl.pathname, Boolean(data.user));
    if (pathname) {
        return redirectTo(pathname);
    }

    return response;
}
