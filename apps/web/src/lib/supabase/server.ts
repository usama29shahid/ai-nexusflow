import { createServerClient } from "@supabase/ssr";
import { cookies, headers } from "next/headers";

import { authCookieOptions, isSecureRequest } from "@/lib/supabase/cookie-options";

function supabaseEnv(): { url: string; anonKey: string } {
    const url = process.env.SUPABASE_URL ?? "";
    const anonKey = process.env.SUPABASE_ANON_KEY ?? "";
    if (!url || !anonKey) {
        throw new Error("SUPABASE_URL and SUPABASE_ANON_KEY are required");
    }
    return { url, anonKey };
}

export async function createClient() {
    const cookieStore = await cookies();
    const headerStore = await headers();
    const { url, anonKey } = supabaseEnv();

    return createServerClient(url, anonKey, {
        cookieOptions: authCookieOptions(isSecureRequest(headerStore.get("x-forwarded-proto"))),
        cookies: {
            getAll() {
                return cookieStore.getAll();
            },
            setAll(cookiesToSet) {
                try {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        cookieStore.set(name, value, options);
                    });
                } catch {
                    // Server Components cannot always write cookies. Middleware refreshes the session.
                }
            },
        },
    });
}
