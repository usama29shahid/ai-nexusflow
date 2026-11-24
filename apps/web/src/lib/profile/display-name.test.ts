import assert from "node:assert/strict";
import test from "node:test";

import {
    DISPLAY_NAME_MAX,
    DISPLAY_NAME_REQUIRED,
    DISPLAY_NAME_TOO_LONG,
    displayNameProblems,
    profileDisplayName,
} from "./display-name.ts";

test("accepts a trimmed display name", () => {
    assert.equal(displayNameProblems("  Ada Lovelace  "), null);
});

test("rejects a blank name", () => {
    assert.equal(displayNameProblems("   "), DISPLAY_NAME_REQUIRED);
    assert.equal(displayNameProblems(""), DISPLAY_NAME_REQUIRED);
    assert.equal(displayNameProblems("\t\n\u00a0"), DISPLAY_NAME_REQUIRED);
});

test("trims the same surrounding whitespace the database removes", () => {
    assert.equal(displayNameProblems("\tAda\n"), null);
    assert.equal(profileDisplayName("\tAda\u00a0", "temp@gmail.com"), "Ada");
});

test("rejects a name longer than the limit", () => {
    assert.equal(displayNameProblems("a".repeat(DISPLAY_NAME_MAX + 1)), DISPLAY_NAME_TOO_LONG);
    assert.equal(displayNameProblems("a".repeat(DISPLAY_NAME_MAX)), null);
});

test("falls back to the mailbox name when no display name is saved", () => {
    assert.equal(profileDisplayName("  Denish  ", "temp@gmail.com"), "Denish");
    assert.equal(profileDisplayName("  ", "temp@gmail.com"), "temp");
    assert.equal(profileDisplayName(null, ""), "Account");
});
