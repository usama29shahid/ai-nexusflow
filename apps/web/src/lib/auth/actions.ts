"use server";

import { redirect } from "next/navigation";

import { passwordProblems } from "@/lib/auth/password";
import { createClient } from "@/lib/supabase/server";

export type AuthFormState = { error: string };

const SIGN_IN_FAILED = "That email and password were not accepted.";
const SIGN_UP_FAILED = "That account could not be created. Check the email and password.";

export async function signIn(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    if (!email.includes("@") || !password) {
        return { error: "Enter an email address and a password." };
    }

    const supabase = await createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
        return { error: SIGN_IN_FAILED };
    }
    redirect("/dashboards/ecommerce");
}

export async function signUp(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const displayName = [formData.get("first_name"), formData.get("last_name")]
        .map((part) => String(part ?? "").trim())
        .filter(Boolean)
        .join(" ");

    if (!email.includes("@") || !password) {
        return { error: "Enter an email address and a password." };
    }
    const weak = passwordProblems(password);
    if (weak) {
        return { error: weak };
    }

    const supabase = await createClient();
    const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: displayName ? { data: { display_name: displayName } } : undefined,
    });
    if (error || !data.user) {
        return { error: SIGN_UP_FAILED };
    }
    if (!data.session) {
        return { error: "Account created. Sign in with the same email." };
    }
    redirect("/dashboards/ecommerce");
}

const SIGN_OUT_FAILED = "Sign out did not finish. Try again.";

export async function signOut(_prev: AuthFormState, _formData: FormData): Promise<AuthFormState> {
    const supabase = await createClient();
    const { error } = await supabase.auth.signOut();
    if (error) {
        return { error: SIGN_OUT_FAILED };
    }
    redirect("/auth/login");
}
