const features = [
    {
        icon: "lucide--layers",
        title: "Framework Flexibility",
        description: "Use across popular stacks with clean, adaptable structure for rapid prototyping",
        iconClass: "text-blue-500 bg-blue-500/5 group-hover:bg-blue-500/10",
        cardClass: "hover:bg-blue-500/5 hover:text-blue-500",
    },
    {
        icon: "lucide--monitor-dot",
        title: "Dashboard View",
        description: "Includes a polished admin layout with sections for stats, content, and user activity",
        iconClass: "text-violet-500 bg-violet-500/5 group-hover:bg-violet-500/10",
        cardClass: "hover:bg-violet-500/5 hover:text-violet-500",
    },
    {
        icon: "lucide--package",
        title: "Design-Ready UI",
        description: "Speed up design flow with pre-built elements like buttons, tables, and forms",
        iconClass: "text-cyan-600 bg-cyan-600/5 group-hover:bg-cyan-600/10",
        cardClass: "hover:bg-cyan-600/5 hover:text-cyan-600",
    },
    {
        icon: "lucide--line-chart",
        title: "Visual Chart Blocks",
        description: "Sketch trends and metrics using built-in chart layouts for fast mockups",
        iconClass: "text-fuchsia-500 bg-fuchsia-500/5 group-hover:bg-fuchsia-500/10",
        cardClass: "hover:bg-fuchsia-500/5 hover:text-fuchsia-500",
    },
    {
        icon: "lucide--wand-sparkles",
        title: "LLM-Ready Support",
        description: "Comes with prompt files for teams exploring text-generation workflows",
        iconClass: "text-orange-400 bg-orange-500/5 group-hover:bg-orange-400/10",
        cardClass: "hover:bg-orange-400/5 hover:text-orange-400",
    },
    {
        icon: "lucide--clock",
        title: "Quick Start Setup",
        description: "Well-structured layout helps teams kick off designs without starting from scratch",
        iconClass: "text-teal-500 bg-teal-500/5 group-hover:bg-teal-500/10",
        cardClass: "hover:bg-teal-500/5 hover:text-teal-500",
    },
    {
        icon: "lucide--monitor-smartphone",
        title: "Adaptive by Design",
        description: "Built to look great on every device, with theme options that fit any brand or user preference",
        iconClass: "text-blue-500 bg-blue-500/5 group-hover:bg-blue-500/10",
        cardClass: "hover:bg-blue-500/5 hover:text-blue-500",
    },
    {
        icon: "lucide--pencil-line",
        title: "Flexible Structure",
        description: "Easy to tweak, rearrange, or build on top—ideal for teams that need room to grow",
        iconClass: "text-violet-500 bg-violet-500/5 group-hover:bg-violet-500/10",
        cardClass: "hover:bg-violet-500/5 hover:text-violet-500",
    },
] as const;

export const Features = () => {
    return (
        <div className="container py-8 md:py-12 xl:py-16 2xl:py-24">
            <div className="text-center">
                <div className="rounded-box inline-flex items-center border border-indigo-500/10 bg-indigo-500/5 p-2">
                    <span className="iconify lucide--wand-2 size-5 text-indigo-600" />
                </div>
                <p id="fade-in" className="custom-fade-in mt-4 text-2xl font-semibold sm:text-3xl">
                    Designed for Impact
                </p>
                <p className="text-base-content/70 mt-3 inline-block max-w-lg max-sm:text-sm">
                    From layouts to interactions, every detail is built to deliver clarity, speed, and a seamless user
                    experience.
                </p>
            </div>

            <div className="mt-8 grid grid-cols-1 gap-0 -space-y-px -space-x-px sm:grid-cols-2 xl:mt-16 xl:grid-cols-4 2xl:mt-20">
                {features.map((feature, index) => {
                    return (
                        <div
                            className={`card group border-base-300 cursor-pointer rounded-none border border-dashed transition-all duration-300 ${feature.cardClass}`}
                            key={index}>
                            <div className="card-body 2xl:p-6">
                                <div>
                                    <div
                                        className={`inline-flex items-center p-2 transition-all duration-300 ${feature.iconClass} rounded`}>
                                        <span className={`iconify ${feature.icon} size-6`} />
                                    </div>
                                    <p className="mt-3 text-lg font-medium">{feature.title}</p>
                                    <p className="text-base-content/80 mt-0.5 line-clamp-2 text-sm text-ellipsis">
                                        {feature.description}
                                    </p>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
