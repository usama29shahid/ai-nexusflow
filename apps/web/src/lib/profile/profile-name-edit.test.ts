import assert from "node:assert/strict";
import test from "node:test";

import { DISPLAY_NAME_REQUIRED, DISPLAY_NAME_TOO_LONG } from "./display-name.ts";
import { profileNameEdit } from "./profile-name-edit.ts";

test("a clean name has nothing to cancel or save", () => {
    const edit = profileNameEdit("Ada", "Ada");
    assert.equal(edit.changed, false);
    assert.equal(edit.canSave, false);
    assert.equal(edit.problem, null);
});

test("spaces around the same name can be cancelled and are not a save", () => {
    const edit = profileNameEdit("Ada", "  Ada  ");
    assert.equal(edit.changed, true);
    assert.equal(edit.canSave, false);
    assert.equal(edit.next, "Ada");
});

test("a new name can be saved", () => {
    const edit = profileNameEdit("Ada", "  Grace Hopper  ");
    assert.equal(edit.changed, true);
    assert.equal(edit.canSave, true);
    assert.equal(edit.next, "Grace Hopper");
    assert.equal(edit.problem, null);
});

test("clearing the name is a change that cannot be saved", () => {
    const edit = profileNameEdit("Ada", "   ");
    assert.equal(edit.changed, true);
    assert.equal(edit.canSave, false);
    assert.equal(edit.problem, DISPLAY_NAME_REQUIRED);
});

test("a name past the limit cannot be saved", () => {
    const edit = profileNameEdit("Ada", "a".repeat(81));
    assert.equal(edit.canSave, false);
    assert.equal(edit.problem, DISPLAY_NAME_TOO_LONG);
});
