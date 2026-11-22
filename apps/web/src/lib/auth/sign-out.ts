export const SIGN_OUT_FAILED = "Sign out did not finish. Try again.";

type SignOutClient = {
    auth: {
        signOut: () => Promise<{ error: unknown }>;
    };
};

/** Return the drawer message when Auth refuses sign-out. Redirect only after the session is cleared. */
export async function finishSignOut(
    client: SignOutClient,
    redirectToLogin: () => never,
): Promise<{ error: string }> {
    const { error } = await client.auth.signOut();
    if (error) {
        return { error: SIGN_OUT_FAILED };
    }
    redirectToLogin();
}
