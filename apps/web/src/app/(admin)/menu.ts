import { ISidebarMenuItem } from "@/components/admin-layout/SidebarMenuItem";

export const adminMenuItems: ISidebarMenuItem[] = [
    {
        id: "overview-label",
        isTitle: true,
        label: "Dashboards",
    },
    {
        id: "dashboards-ecommerce",
        label: "Ecommerce",
        url: "/dashboards/ecommerce",
        icon: "lucide--store",
    },
    {
        id: "account-label",
        isTitle: true,
        label: "Account",
    },
    {
        id: "pages-settings",
        label: "Settings",
        url: "/pages/settings",
        icon: "lucide--settings",
    },
];
