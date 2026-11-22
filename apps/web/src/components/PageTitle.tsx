import Link from "next/link";
import { ReactNode } from "react";

export type IBreadcrumbItem = {
    label: string;
    path?: string;
    active?: boolean;
};

type IPageTitle = {
    items?: IBreadcrumbItem[];
    title: string;
    centerItem?: ReactNode;
};

export const PageTitle = ({ title, items, centerItem }: IPageTitle) => {
    return (
        <div className="flex items-center justify-between">
            <p className="text-lg font-medium">{title}</p>
            {centerItem != null && centerItem}
            <>
                {items && (
                    <div className="breadcrumbs hidden p-0 text-sm sm:inline">
                        <ul>
                            <li>
                                <Link href="/dashboards/ecommerce">Nexus</Link>
                            </li>
                            {items.map((item, index) => {
                                return (
                                    <li key={index} className={`${item.active ? "opacity-80" : ""}`}>
                                        {item.path ? (
                                            <Link key={index + 1} href={item.path}>
                                                {item.label}
                                            </Link>
                                        ) : (
                                            <>{item.label}</>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                )}
            </>
        </div>
    );
};
