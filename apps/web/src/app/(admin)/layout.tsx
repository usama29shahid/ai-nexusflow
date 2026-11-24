import { type ReactNode } from "react";

import { Footer } from "@/components/admin-layout/Footer";
import { Rightbar } from "@/components/admin-layout/Rightbar";
import { Sidebar } from "@/components/admin-layout/Sidebar";
import { Topbar } from "@/components/admin-layout/Topbar";
import { profileView, shellDisplayName } from "@/lib/profile/profile-view";
import { createClient } from "@/lib/supabase/server";

import { adminMenuItems } from "./menu";

export const dynamic = "force-dynamic";

const Layout = async ({ children }: { children: ReactNode }) => {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    const user = data.user;
    const authEmail = user?.email ?? "";
    let email = authEmail;
    let displayName = "Account";
    if (user) {
        const result = await supabase
            .from("profiles")
            .select("email, display_name, created_at, updated_at")
            .eq("id", user.id)
            .maybeSingle();
        const view = profileView(authEmail, result);
        email = view.email;
        displayName = shellDisplayName(view);
    }

    return (
        <div className="size-full">
            <div className="flex">
                <Sidebar menuItems={adminMenuItems} email={email} displayName={displayName} />
                <div className="flex h-screen min-w-0 grow flex-col overflow-auto">
                    <Topbar email={email} displayName={displayName} />
                    <div id="layout-content">{children}</div>
                    <Footer />
                </div>
            </div>
            <Rightbar />
        </div>
    );
};

export default Layout;
