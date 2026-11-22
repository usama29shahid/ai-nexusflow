import { type Metadata } from "next";
import { type ReactNode } from "react";

import { ConfigProvider } from "@/contexts/config";
import "@/styles/app.css";

export const metadata: Metadata = {
    title: {
        template: "%s - Nexus",
        default: "",
    },
    description: "Modern admin and client dashboards built with DaisyUI. Clean, responsive, and fully customizable.",
    icons: {
        icon: [
            {
                url: "/images/favicon-light.png",
                media: "(prefers-color-scheme: light)",
            },
            {
                url: "/images/favicon-dark.png",
                media: "(prefers-color-scheme: dark)",
            },
        ],
    },
};

export default function RootLayout({ children }: { children: ReactNode }) {
    return (
        <html lang="en" suppressHydrationWarning className="group/html">
            <head>
                <link rel="preconnect" href="https://fonts.gstatic.com" />
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                {/* eslint-disable-next-line @next/next/no-sync-scripts */}
                <script type="text/javascript" src="/js/prefetch-config.js"></script>
            </head>
            <body>
                <ConfigProvider>{children}</ConfigProvider>
            </body>
        </html>
    );
}
