import { displayNameProblems } from "./display-name.ts";

export type ProfileFormState = { error: string; saved: boolean };

export const SAVE_FAILED = "The name could not be saved. Try again.";
export const SIGN_IN_AGAIN = "Sign in again to update your profile.";

export type DisplayNameUpdate = {
    userId: string | null;
    save: (userId: string, displayName: string) => Promise<{ ok: boolean }>;
};

export type ProfileNameClient = {
    auth: {
        getUser: () => Promise<{ data: { user: { id: string } | null } }>;
    };
    from: (table: "profiles") => {
        update: (values: { display_name: string }) => {
            eq: (
                column: "id",
                value: string,
            ) => {
                select: (columns: "id") => PromiseLike<{ data: { id: string }[] | null; error: unknown }>;
            };
        };
    };
};

/** The only column a profile save may send. The database sets updated_at. */
export function profileNamePatch(displayName: string): { display_name: string } {
    return { display_name: displayName };
}

export async function saveProfileDisplayName(client: ProfileNameClient, raw: string): Promise<ProfileFormState> {
    const { data } = await client.auth.getUser();
    return applyDisplayName(
        {
            userId: data.user?.id ?? null,
            save: async (userId, displayName) => {
                const { data: updated, error } = await client
                    .from("profiles")
                    .update(profileNamePatch(displayName))
                    .eq("id", userId)
                    .select("id");
                return { ok: !error && Boolean(updated?.length) };
            },
        },
        raw,
    );
}

/** Writes the trimmed name only. The database sets updated_at. */
export async function applyDisplayName(update: DisplayNameUpdate, raw: string): Promise<ProfileFormState> {
    const problem = displayNameProblems(raw);
    if (problem) {
        return { error: problem, saved: false };
    }
    if (!update.userId) {
        return { error: SIGN_IN_AGAIN, saved: false };
    }
    const savedName = raw.trim();
    const result = await update.save(update.userId, savedName);
    if (!result.ok) {
        return { error: SAVE_FAILED, saved: false };
    }
    return { error: "", saved: true };
}
