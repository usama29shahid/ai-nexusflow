const testimonials = [
    {
        id: "landing-testimonial-1",
        image: "/images/landing/testimonial-avatar-1.jpg",
        name: "Pouya Saadeghi",
        role: "Creator of daisyUI",
        comment:
            "This is the ultimate admin dashboard template, with all the essential blocks and features you need. Save you months of development time and helps you launch your app faster",
    },
    {
        id: "landing-testimonial-3",
        image: "/images/landing/testimonial-avatar-3.png",
        name: "Quinn the explorer",
        role: "Solo Web Developer",
        comment:
            "Beautifully designed dashboard! It provided me with an exceptional starting point and instantly boosted my confidence to successfully complete the project",
    },
    {
        id: "landing-testimonial-4",
        image: "/images/landing/testimonial-avatar-4.png",
        name: "Caygoder",
        role: "Software Developer",
        comment:
            "Landed a 2‑year SaaS contract in under a week! Traditional proposals are table stakes—Nexus’s immersive, interactive visuals brought the wow factor that sealed the deal",
    },

    {
        id: "landing-testimonial-2",
        image: "/images/landing/testimonial-avatar-2.jpg",
        name: "Alexandre Cohen",
        role: "Co-owner / CTO of Disphere",
        comment:
            "Exceptional dashboard with a sleek design and seamless integration of DaisyUI components. Perfect for my existing project !",
    },

    {
        id: "landing-testimonial-5",
        image: "/images/landing/testimonial-avatar-5.png",
        name: "J.C Yuan",
        role: "Freelancer",
        comment:
            "Nexus saved me a tremendous amount of time. It's a highly flexible, user-friendly template with excellent code quality and all the components a website might need. That it's built on daisyUI makes it even better",
    },
] as const;

export const Testimonial = () => {
    return (
        <section id="testimonial" className="relative container py-8 md:py-12 xl:py-16 2xl:py-24">
            <div className="absolute inset-0 bg-[url('/images/landing/testimonial-background.svg')] bg-cover bg-center bg-no-repeat opacity-8 dark:opacity-6"></div>

            <div className="relative">
                <div className="text-center">
                    <div className="rounded-box inline-flex items-center border border-orange-500/10 bg-orange-500/5 p-2">
                        <span className="iconify lucide--sparkles size-5 text-orange-600" />
                    </div>
                    <h2 className="mt-4 text-2xl font-semibold sm:text-3xl">Voices That Matter</h2>
                    <p className="text-base-content/70 mt-3 inline-block max-w-lg max-sm:text-sm">
                        Hear directly from users who’ve successfully transformed their workflow with our dashboard
                        solution.
                    </p>
                </div>
                <div className="mt-8 columns-1 gap-4 space-y-4 md:columns-2 lg:mt-12 lg:columns-3 lg:gap-6 lg:space-y-6 2xl:mt-16">
                    {testimonials.map((testimonial) => (
                        <div
                            key={testimonial.id}
                            className="card bg-base-100/80 group border-base-200 break-inside-avoid border">
                            <div className="relative p-5">
                                <div className="flex items-center gap-4">
                                    <div className="avatar">
                                        <div className="mask mask-squircle bg-base-200 w-16">
                                            <img src={testimonial.image} alt="testimonial" />
                                        </div>
                                    </div>
                                    <div>
                                        <p className="text-lg font-medium">{testimonial.name}</p>
                                        <p className="text-base-content/80 text-sm">{testimonial.role}</p>
                                        <div className="mt-0.5 flex items-start -space-x-0.5 text-orange-500/70 transition-all group-hover:text-orange-500">
                                            {new Array(5).fill(0).map((_, index) => (
                                                <svg key={index} className="size-4.5" viewBox="0 0 24 24">
                                                    <path
                                                        fill="currentColor"
                                                        d="m12 17.275l-4.15 2.5q-.275.175-.575.15t-.525-.2t-.35-.437t-.05-.588l1.1-4.725L3.775 10.8q-.25-.225-.312-.513t.037-.562t.3-.45t.55-.225l4.85-.425l1.875-4.45q.125-.3.388-.45t.537-.15t.537.15t.388.45l1.875 4.45l4.85.425q.35.05.55.225t.3.45t.038.563t-.313.512l-3.675 3.175l1.1 4.725q.075.325-.05.588t-.35.437t-.525.2t-.575-.15z"></path>
                                                </svg>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                                <p className="mt-3 text-sm">{testimonial.comment}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
};
