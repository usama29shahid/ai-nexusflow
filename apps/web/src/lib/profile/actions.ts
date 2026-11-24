"use server";

import { revalidatePath } from "next/cache";

import { type ProfileFormState, saveProfileDisplayName } from "@/lib/profile/save-display-name";
import { createClient } from "@/lib/supabase/server";

export type { ProfileFormState };

export async function updateDisplayName(_prev: ProfileFormState, formData: FormData): Promise<ProfileFormState> {
    const raw = String(formData.get("display_name") ?? "");
    const supabase = await createClient();
    const state = await saveProfileDisplayName(supabase, raw);
    if (state.saved) {
        revalidatePath("/pages/settings", "layout");
    }
    return state;
}
