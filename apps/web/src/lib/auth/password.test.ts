import assert from "node:assert/strict";
import test from "node:test";

import { passwordProblems } from "./password.ts";

test("accepts a password with all four classes", () => {
    assert.equal(passwordProblems("Testpass1!"), null);
});

test("rejects a short password and a missing class", () => {
    assert.ok(passwordProblems("short"));
    assert.ok(passwordProblems("longpassword"));
    assert.ok(passwordProblems("Longpassword"));
    assert.ok(passwordProblems("Longpassword1"));
});
