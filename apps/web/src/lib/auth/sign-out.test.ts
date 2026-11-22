import assert from "node:assert/strict";
import test from "node:test";

import { SIGN_OUT_FAILED, finishSignOut } from "./sign-out.ts";

test("a failed sign-out keeps the session and returns the message", async () => {
    let redirected = false;
    const result = await finishSignOut(
        {
            auth: {
                signOut: async () => ({ error: { message: "fetch failed" } }),
            },
        },
        () => {
            redirected = true;
            throw new Error("redirect");
        },
    );
    assert.equal(redirected, false);
    assert.deepEqual(result, { error: SIGN_OUT_FAILED });
    assert.equal(result.error, "Sign out did not finish. Try again.");
});

test("a successful sign-out redirects to login", async () => {
    let redirected = false;
    await assert.rejects(
        finishSignOut(
            {
                auth: {
                    signOut: async () => ({ error: null }),
                },
            },
            () => {
                redirected = true;
                throw new Error("redirect");
            },
        ),
        /redirect/,
    );
    assert.equal(redirected, true);
});
