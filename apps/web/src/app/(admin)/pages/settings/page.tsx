import React from "react";

import { PROFILE_LOAD_FAILED, profileView } from "@/lib/profile/profile-view";
import { createClient } from "@/lib/supabase/server";

import { ProfileForm } from "./ProfileForm";
import { ProfileWhen } from "./ProfileWhen";

const SettingsPage = async () => {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    const user = data.user;
    const authEmail = user?.email ?? "";
    let view = profileView(authEmail, { data: null, error: null });

    if (!user) {
        view = profileView(authEmail, { data: null, error: { message: "signed out" } });
    } else {
        const result = await supabase
            .from("profiles")
            .select("email, display_name, created_at, updated_at")
            .eq("id", user.id)
            .maybeSingle();
        view = profileView(authEmail, result);
    }

    return (
        <div className="sm:container">
            <div className="bg-primary/10 rounded-box relative w-full overflow-hidden p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <div className="flex items-center gap-1">
                            <p className="text-base-content/80 text-sm">Pages</p>
                            <span className="iconify lucide--chevron-right text-base-content/80 size-3.5"></span>
                            <p className="text-sm">Settings</p>
                        </div>
                        <p className="text-primary mt-4 text-xl font-medium">My Profile</p>
                        <p className="text-base-content/80">Your name and the email you use to sign in.</p>
                    </div>
                    {view.loadError ? null : (
                        <div className="text-base-content/60 flex items-center gap-2">
                            <span className="iconify lucide--clock size-4"></span>
                            <p className="text-sm">
                                Changed <ProfileWhen iso={view.updatedAt} withTime />
                            </p>
                        </div>
                    )}
                </div>
                <span className="iconify lucide--settings text-primary/5 absolute inset-s-1/2 -bottom-12 size-44 -rotate-25"></span>
            </div>
            <ProfileForm
                loadError={view.loadError}
                loadErrorMessage={PROFILE_LOAD_FAILED}
                displayName={view.displayName}
                email={view.email}
                memberSince={view.createdAt}
            />
        </div>
    );
};

export default SettingsPage;
