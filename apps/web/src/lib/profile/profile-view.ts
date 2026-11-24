import { profileDisplayName } from "./display-name.ts";

export const PROFILE_LOAD_FAILED = "Your profile could not be loaded. Refresh the page and try again.";

export type ProfileRow = {
    email: string | null;
    display_name: string | null;
    created_at: string | null;
    updated_at: string | null;
};

export type ProfileView = {
    loadError: boolean;
    email: string;
    displayName: string;
    createdAt: string | null;
    updatedAt: string | null;
};

/** Shell label when the profile row could not be read. */
export function shellDisplayName(view: ProfileView): string {
    if (view.loadError) {
        return "Account";
    }
    return view.displayName;
}

/** A failed read must not look like an empty profile that Update can save over. */
export function profileView(authEmail: string, result: { data: ProfileRow | null; error: unknown }): ProfileView {
    if (result.error) {
        return {
            loadError: true,
            email: authEmail,
            displayName: "",
            createdAt: null,
            updatedAt: null,
        };
    }
    const email = result.data?.email || authEmail;
    return {
        loadError: false,
        email,
        displayName: profileDisplayName(result.data?.display_name, email),
        createdAt: result.data?.created_at ?? null,
        updatedAt: result.data?.updated_at ?? null,
    };
}
