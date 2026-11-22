import { type ReactNode } from "react";

import { Footer } from "@/components/admin-layout/Footer";
import { Rightbar } from "@/components/admin-layout/Rightbar";
import { Sidebar } from "@/components/admin-layout/Sidebar";
import { Topbar } from "@/components/admin-layout/Topbar";
import { createClient } from "@/lib/supabase/server";

import { adminMenuItems } from "./menu";

export const dynamic = "force-dynamic";

const Layout = async ({ children }: { children: ReactNode }) => {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    const user = data.user;
    let email = user?.email ?? "";
    let displayName = email.split("@")[0] || "Account";
    if (user) {
        const { data: profile } = await supabase
            .from("profiles")
            .select("email, display_name")
            .eq("id", user.id)
            .maybeSingle();
        if (profile?.email) {
            email = profile.email;
        }
        if (profile?.display_name) {
            displayName = profile.display_name;
        } else if (email.includes("@")) {
            displayName = email.split("@")[0];
        }
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
