import React from "react";

import { HelpTopic } from "./HelpTopic";
import { accountFaqs, dashboardFaqs, helpTopics } from "./helpers";

const GetHelpPage = () => {
    return (
        <>
            <div className="sm:container">
                <div className="bg-primary/10 rounded-box relative w-full overflow-hidden p-6">
                    <div>
                        <div>
                            <div className="flex items-center gap-1">
                                <p className="text-base-content/80 text-sm">Pages</p>
                                <span className="iconify lucide--chevron-right text-base-content/80 size-3.5"></span>
                                <p className="text-sm">Support</p>
                            </div>
                            <p className="text-primary mt-4 text-xl font-medium">Get Help</p>
                            <p className="text-base-content/80">
                                Find answers to common questions and learn how to use the platform effectively
                            </p>
                        </div>
                    </div>
                    <span className="iconify lucide--badge-help text-primary/5 absolute inset-s-1/2 -bottom-12 size-44 -rotate-25"></span>
                </div>
                <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
                    {helpTopics.map((topic, i) => (
                        <HelpTopic {...topic} key={i} />
                    ))}
                </div>
                <p className="mt-12 text-center text-2xl font-medium">Frequently Asked Questions</p>
                <p className="text-base-content/80 text-center">
                    Find answers to common questions about system features, settings, and troubleshooting.
                </p>
                <div className="mt-8 grid gap-8 md:grid-cols-2">
                    <div className="card bg-base-100 h-fit shadow-sm">
                        <div className="card-body pb-0">
                            <div className="badge badge-sm badge-ghost">Account</div>
                            <p className="text-lg font-medium">Account</p>
                            <div className="-mx-4 mt-2">
                                {accountFaqs.map((faq, i) => (
                                    <div className="collapse-plus collapse" key={i}>
                                        <input
                                            type="radio"
                                            aria-label={faq.question}
                                            className="cursor-pointer"
                                            name="faq-account"
                                        />
                                        <div className="collapse-title cursor-pointer">{faq.question}</div>
                                        <div className="collapse-content">{faq.answer}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                    <div className="card bg-base-100 h-fit shadow-sm">
                        <div className="card-body pb-0">
                            <div className="badge badge-sm badge-ghost">Dashboard</div>
                            <p className="text-lg font-medium">Dashboard</p>
                            <div className="-mx-4 mt-2">
                                {dashboardFaqs.map((faq, i) => (
                                    <div className="collapse-plus collapse" key={i}>
                                        <input
                                            type="radio"
                                            aria-label={faq.question}
                                            className="cursor-pointer"
                                            name="faq-dashboard"
                                        />
                                        <div className="collapse-title cursor-pointer">{faq.question}</div>
                                        <div className="collapse-content">{faq.answer}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
};

export default GetHelpPage;
