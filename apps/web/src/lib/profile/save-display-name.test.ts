import assert from "node:assert/strict";
import test from "node:test";

import { DISPLAY_NAME_REQUIRED, DISPLAY_NAME_TOO_LONG } from "./display-name.ts";
import { SAVE_FAILED, SIGN_IN_AGAIN, applyDisplayName, saveProfileDisplayName } from "./save-display-name.ts";

test("a signed-out save does not write", async () => {
    let called = false;
    const state = await applyDisplayName(
        {
            userId: null,
            save: async () => {
                called = true;
                return { ok: true };
            },
        },
        "Ada",
    );
    assert.equal(called, false);
    assert.deepEqual(state, { error: SIGN_IN_AGAIN, saved: false });
});

test("a blank name is rejected before a write", async () => {
    let called = false;
    const state = await applyDisplayName(
        {
            userId: "user-1",
            save: async () => {
                called = true;
                return { ok: true };
            },
        },
        "   ",
    );
    assert.equal(called, false);
    assert.equal(state.error, DISPLAY_NAME_REQUIRED);
    assert.equal(state.saved, false);
});

test("an over-long name is rejected before a write", async () => {
    const state = await applyDisplayName(
        {
            userId: "user-1",
            save: async () => ({ ok: true }),
        },
        "a".repeat(81),
    );
    assert.equal(state.error, DISPLAY_NAME_TOO_LONG);
    assert.equal(state.saved, false);
});

test("a successful save writes the trimmed name and not a timestamp", async () => {
    let saved: { userId: string; displayName: string } | null = null;
    const state = await applyDisplayName(
        {
            userId: "user-1",
            save: async (userId, displayName) => {
                saved = { userId, displayName };
                return { ok: true };
            },
        },
        "  Ada Byron  ",
    );
    assert.deepEqual(saved, { userId: "user-1", displayName: "Ada Byron" });
    assert.deepEqual(state, { error: "", saved: true });
});

test("the profile update sends only the trimmed display name", async () => {
    let patch: Record<string, unknown> | null = null;
    const state = await saveProfileDisplayName(
        {
            auth: {
                getUser: async () => ({ data: { user: { id: "user-1" } } }),
            },
            from: () => ({
                update: (values) => {
                    patch = values;
                    return {
                        eq: () => ({
                            select: async () => ({ data: [{ id: "user-1" }], error: null }),
                        }),
                    };
                },
            }),
        },
        "  Ada Byron  ",
    );
    assert.deepEqual(patch, { display_name: "Ada Byron" });
    assert.equal(Object.hasOwn(patch ?? {}, "updated_at"), false);
    assert.deepEqual(state, { error: "", saved: true });
});

test("zero updated rows is a failed save", async () => {
    const state = await applyDisplayName(
        {
            userId: "user-1",
            save: async () => ({ ok: false }),
        },
        "Ada",
    );
    assert.deepEqual(state, { error: SAVE_FAILED, saved: false });
});
