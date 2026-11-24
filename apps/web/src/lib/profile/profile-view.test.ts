import assert from "node:assert/strict";
import test from "node:test";

import { profileView, shellDisplayName } from "./profile-view.ts";

const row = {
    email: "ada@example.com",
    display_name: "Ada Lovelace",
    created_at: "2026-11-23T20:00:00.000Z",
    updated_at: "2026-11-23T21:00:00.000Z",
};

test("a failed profile read does not invent a name that can be saved", () => {
    const view = profileView("ada@example.com", { data: null, error: { message: "timeout" } });
    assert.equal(view.loadError, true);
    assert.equal(view.displayName, "");
    assert.equal(shellDisplayName(view), "Account");
    assert.equal(view.createdAt, null);
    assert.equal(view.updatedAt, null);
});

test("a missing profile row uses the mailbox name", () => {
    const view = profileView("ada@example.com", { data: null, error: null });
    assert.equal(view.loadError, false);
    assert.equal(view.displayName, "ada");
    assert.equal(view.email, "ada@example.com");
});

test("a loaded profile keeps the saved name in the shell", () => {
    const view = profileView("ada@example.com", { data: row, error: null });
    assert.equal(shellDisplayName(view), "Ada Lovelace");
});

test("a loaded profile keeps the saved name and timestamps", () => {
    const view = profileView("other@example.com", { data: row, error: null });
    assert.equal(view.loadError, false);
    assert.equal(view.displayName, "Ada Lovelace");
    assert.equal(view.email, "ada@example.com");
    assert.equal(view.createdAt, row.created_at);
    assert.equal(view.updatedAt, row.updated_at);
});
