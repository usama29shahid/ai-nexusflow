import assert from "node:assert/strict";
import test from "node:test";

import { formatProfileWhen } from "./profile-time.ts";

const iso = "2026-11-23T20:00:00.000Z";

test("member since uses the requested zone's calendar day", () => {
    assert.equal(formatProfileWhen(iso, false, "UTC"), "23 Nov 2026");
    assert.equal(formatProfileWhen(iso, false, "Asia/Kolkata"), "24 Nov 2026");
});

test("a missing timestamp stays empty", () => {
    assert.equal(formatProfileWhen(null, true), "Not recorded");
    assert.equal(formatProfileWhen("not-a-date", false), "Not recorded");
});
