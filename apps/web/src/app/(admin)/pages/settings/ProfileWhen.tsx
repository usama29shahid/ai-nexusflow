"use client";

import { useSyncExternalStore } from "react";

import { formatProfileWhen } from "@/lib/profile/profile-time";

const subscribe = () => () => {};

/** Server HTML uses UTC. After hydration the clock is the browser's zone. */
export const ProfileWhen = ({ iso, withTime }: { iso: string | null; withTime: boolean }) => {
    const label = useSyncExternalStore(
        subscribe,
        () => formatProfileWhen(iso, withTime),
        () => formatProfileWhen(iso, withTime, "UTC"),
    );
    return <span>{label}</span>;
};
