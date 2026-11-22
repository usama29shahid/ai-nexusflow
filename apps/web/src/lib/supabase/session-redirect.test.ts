import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server.js";

import { isSecureRequest } from "./cookie-options.ts";
import { redirectKeepingCookies } from "./redirect-response.ts";
import { sessionRedirectPath } from "./session-redirect.ts";

test("signed-out visitors are sent to login from a protected page", () => {
    assert.equal(sessionRedirectPath("/dashboards/ecommerce", false), "/auth/login");
    assert.equal(sessionRedirectPath("/apps/chat", false), "/auth/login");
    assert.equal(sessionRedirectPath("/pages/settings", false), "/auth/login");
    assert.equal(sessionRedirectPath("/auth/login", false), null);
});

test("a redirect keeps the refreshed session cookie", () => {
    const request = new NextRequest("http://app.localhost.com/auth/login");
    const response = redirectKeepingCookies(request, "/dashboards/ecommerce", [
        {
            name: "sb-kong-auth-token",
            value: "refreshed",
            options: { httpOnly: true, secure: false, sameSite: "lax", path: "/" },
        },
    ]);
    assert.equal(response.status, 307);
    assert.equal(response.headers.get("location"), "http://app.localhost.com/dashboards/ecommerce");
    const setCookie = response.headers.get("set-cookie") ?? "";
    assert.match(setCookie, /sb-kong-auth-token=refreshed/);
    assert.match(setCookie, /HttpOnly/i);
    assert.doesNotMatch(setCookie, /Secure/i);
});

test("the session cookie is secure only behind HTTPS", () => {
    assert.equal(isSecureRequest(null), false);
    assert.equal(isSecureRequest("http"), false);
    assert.equal(isSecureRequest("HTTPS"), true);
    assert.equal(isSecureRequest("https"), true);
    assert.equal(isSecureRequest("https,http"), true);
});

test("a signed-in visitor leaves login and register for the dashboard", () => {
    assert.equal(sessionRedirectPath("/auth/login", true), "/dashboards/ecommerce");
    assert.equal(sessionRedirectPath("/auth/register", true), "/dashboards/ecommerce");
    assert.equal(sessionRedirectPath("/dashboards/ecommerce", true), null);
    assert.equal(sessionRedirectPath("/auth/forgot-password", true), null);
});
