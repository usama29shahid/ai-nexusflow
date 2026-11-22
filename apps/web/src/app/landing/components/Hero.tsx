"use client";

import Link from "next/link";
import "swiper/css";
import { Autoplay, Navigation, Pagination } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";

const pages = [
    {
        title: "Ecommerce Dashboard",
        image: "dashboard-ecommerce.jpg",
        link: "/dashboards/ecommerce",
    },
];

export const Hero = () => {
    return (
        <div className="relative">
            <div className="absolute inset-0 -top-2 h-400 bg-[url(/images/landing/hero-bg-gradient.png)] bg-size-[200%_60%] bg-no-repeat opacity-12 [background-position-x:center] sm:bg-size-[100%_100%] dark:opacity-12" />

            <div className="relative z-10 container py-20 sm:py-28 xl:py-40">
                <div className="flex flex-col items-center">
                    <Link
                        className="flex items-center gap-1.5 rounded-full border border-white/60 bg-white/40 py-0.5 ps-1 pe-2 text-sm transition-all hover:bg-white/60 dark:border-white/5 dark:bg-white/5 dark:hover:bg-white/10"
                        href="/dashboards/ecommerce"
                        target="_blank">
                        <div className="bg-primary/10 border-primary/10 text-primary flex items-center justify-center rounded-full border px-1.5 py-0 text-xs font-medium dark:border-white/5 dark:bg-white/5 dark:text-white">
                            v4
                        </div>{" "}
                        Dashboards & Angular
                    </Link>
                    <div className="mt-4 max-w-280 transition-all duration-1000 starting:scale-125 starting:opacity-0 starting:blur-sm">
                        <p className="text-center text-2xl leading-snug font-bold tracking-[-0.25px] sm:text-3xl md:text-4xl lg:text-5xl 2xl:text-[66px]">
                            Turbocharge Your Project with Beautiful & Premium{" "}
                            <span className="text-rotate duration-18000">
                                <span className="">
                                    <span className="animated-text bg-linear-to-r from-purple-500 to-blue-500 bg-clip-text text-transparent dark:from-purple-400 dark:to-blue-400">
                                        Dashboards
                                    </span>
                                    <span className="animated-text bg-linear-to-r from-purple-500 to-blue-500 bg-clip-text text-transparent dark:from-purple-400 dark:to-blue-400">
                                        Applications
                                    </span>
                                    <span className="animated-text bg-linear-to-r from-purple-500 to-blue-500 bg-clip-text text-transparent dark:from-purple-400 dark:to-blue-400">
                                        Components
                                    </span>
                                    <span className="animated-text bg-linear-to-r from-purple-500 to-blue-500 bg-clip-text text-transparent dark:from-purple-400 dark:to-blue-400">
                                        Interfaces
                                    </span>
                                </span>
                            </span>
                        </p>
                    </div>
                    <div className="mt-4 max-w-220 text-center transition-all duration-1000 sm:mt-6 xl:mt-8 starting:opacity-0 starting:blur-sm">
                        <p className="text-balance max-sm:text-sm md:text-lg">
                            Everything you need to ship faster. Access customizable dashboards, apps, blocks, and
                            integrations.{" "}
                            <span className="max-sm:hidden">
                                Built for peak performance and seamlessly supported across all major meta frameworks
                            </span>
                        </p>
                    </div>

                    <div className="mt-6 inline-flex items-center gap-2.5 transition-all delay-300 duration-1000 sm:gap-5 xl:mt-10 starting:opacity-0 starting:blur-sm">
                        <Link href="/dashboards/ecommerce" className="btn btn-primary btn-lg gap-2.5">
                            <span className="iconify lucide--monitor-dot size-5 sm:size-6" />
                            <div className="text-start">
                                <p className="text-base/none">Dashboard</p>
                                <p className="text-primary-content/70 mt-0.5 text-[11px]/none">Preview</p>
                            </div>
                        </Link>
                    </div>
                    <div className="group relative mt-8 max-w-full md:mt-16 md:max-w-xl lg:max-w-3xl xl:mt-20 xl:max-w-5xl 2xl:max-w-6xl">
                        <div className="border-base-100/20 bg-base-100/30 dark:border-px relative rounded-lg border-2 py-2 dark:border-white/2 dark:bg-white/4">
                            <Swiper
                                slidesPerView={1}
                                cardsEffect={{
                                    rotate: false,
                                    perSlideOffset: 10,
                                    slideShadows: false,
                                }}
                                loop
                                speed={1500}
                                autoplay={{
                                    delay: 5000,
                                }}
                                spaceBetween={0}
                                navigation={{
                                    prevEl: ".hero-swiper-button-prev",
                                    nextEl: ".hero-swiper-button-next",
                                }}
                                modules={[Navigation, Pagination, Autoplay]}>
                                {pages.map((page, index) => (
                                    <SwiperSlide key={index}>
                                        <div className="mx-2 cursor-pointer">
                                            <Link className="relative" href={page.link}>
                                                <img
                                                    src={`/images/landing/light/${page.image}`}
                                                    className="h-full w-full rounded-lg dark:hidden"
                                                    alt="hero-landing"
                                                />
                                                <img
                                                    src={`/images/landing/dark/${page.image}`}
                                                    className="hidden h-full w-full rounded-lg dark:block"
                                                    alt="hero-landing"
                                                />
                                                <div className="absolute inset-0 flex items-end justify-center rounded-lg bg-linear-to-b from-transparent from-50% via-black/20 via-80% to-black/80 opacity-0 transition-all duration-300 group-hover:opacity-100">
                                                    <div className="rounded-box mb-8 gap-2.5 bg-white px-4 py-2 text-sm font-medium text-black/80">
                                                        {page.title}
                                                    </div>
                                                </div>
                                            </Link>
                                        </div>
                                    </SwiperSlide>
                                ))}
                            </Swiper>
                        </div>
                        <div className="absolute z-1 flex justify-between opacity-0 transition-all duration-300 group-hover:opacity-100 max-md:inset-s-1/2 max-md:-bottom-12 max-md:-translate-x-1/2 max-md:gap-3 md:-inset-x-24 md:top-1/2 md:-translate-y-1/2">
                            <button className="hero-swiper-button-prev border-base-200 flex size-8 cursor-pointer items-center justify-center rounded-full bg-white shadow-xs transition-all hover:shadow-md max-md:shadow-sm md:size-10 dark:border-white/10 dark:bg-white/10 dark:hover:bg-white/20">
                                <span className="iconify lucide--chevron-left size-5"></span>
                            </button>
                            <button className="hero-swiper-button-next border-base-200 flex size-8 cursor-pointer items-center justify-center rounded-full bg-white shadow-xs transition-all hover:shadow-md max-md:shadow-sm md:size-10 dark:border-white/10 dark:bg-white/10 dark:hover:bg-white/20">
                                <span className="iconify lucide--chevron-right size-5"></span>
                            </button>
                        </div>
                    </div>

                    <div className="mt-8 text-center sm:mt-12 lg:mt-16">
                        <p className="text-base-content/60 font-medium">Available In</p>
                        <div className="mt-4 flex flex-wrap items-center justify-center gap-6">
                            <div className="tooltip" data-tip="Tailwind CSS 4">
                                <img
                                    src="/images/landing/logo-tailwind.svg"
                                    className="size-7 sm:size-9"
                                    alt="Tailwind CSS"
                                />
                            </div>
                            <div className="tooltip" data-tip="daisyUI 5 - Component Library">
                                <img
                                    src="/images/landing/logo-daisyui.svg"
                                    className="size-7 sm:size-9"
                                    alt="DaisyUI"
                                />
                            </div>
                            <div className="tooltip" data-tip="Alpine.js">
                                <img
                                    src="/images/landing/logo-alpinejs.svg"
                                    className="size-8 sm:size-11"
                                    alt="Alpine.js"
                                />
                            </div>

                            <div className="tooltip" data-tip="Typescript">
                                <img src="/images/landing/logo-ts.svg" className="size-7 sm:size-9" alt="Typescript" />
                            </div>
                            <div className="tooltip" data-tip="Vite">
                                <img src="/images/landing/logo-vite.svg" className="size-7 sm:size-9" alt="Vite" />
                            </div>

                            <div className="tooltip" data-tip="React 19">
                                <img src="/images/landing/logo-react.svg" className="size-7 sm:size-9" alt="React" />
                            </div>

                            <div className="tooltip" data-tip="Next.JS 15">
                                <img
                                    src="/images/landing/logo-next.svg"
                                    className="size-7 sm:size-9 dark:invert"
                                    alt="Next.JS"
                                />
                            </div>
                            <div className="tooltip" data-tip="SvelteKit 2">
                                <img
                                    src="/images/landing/logo-svelte.svg"
                                    className="size-7 sm:size-9"
                                    alt="SvelteKit 2"
                                />
                            </div>
                            <div className="tooltip" data-tip="Nuxt 4">
                                <img src="/images/landing/logo-nuxt.svg" className="size-8 sm:size-10" alt="Nuxt 4" />
                            </div>
                            <div className="tooltip" data-tip="Laravel 12">
                                <img
                                    src="/images/landing/logo-laravel.svg"
                                    className="size-7 sm:size-8"
                                    alt="Laravel 12"
                                />
                            </div>
                            <div className="tooltip" data-tip="Phoenix">
                                <img
                                    src="/images/landing/logo-phoenix.svg"
                                    className="size-9 sm:size-11"
                                    alt="Phoenix"
                                />
                            </div>
                            <div className="tooltip" data-tip="ROR">
                                <img src="/images/landing/logo-ror.svg" className="h-7 sm:h-6" alt="Ruby on Rails" />
                            </div>
                            <div className="tooltip" data-tip="Angular (New)">
                                <img
                                    src="/images/landing/logo-angular.svg"
                                    className="size-6.5 sm:size-8"
                                    alt="Angular"
                                />
                            </div>
                        </div>
                    </div>
                </div>
                <div className="absolute inset-e-0 top-100 max-xl:hidden">
                    <div className="bg-base-100/60 rounded-box border-base-100 relative w-50 cursor-pointer border px-5 py-3 text-lg dark:border-white/5 dark:bg-white/5">
                        <span className="iconify lucide--sparkles text-base-content/20 absolute inset-e-3 top-2.5 size-8"></span>
                        <p>
                            <span className="text-primary font-semibold">5</span> Apps
                        </p>
                        <p>
                            <span className="text-primary font-semibold">6</span> Dashboards
                        </p>
                        <p>
                            <span className="text-primary font-semibold">200+</span> Components
                        </p>
                    </div>
                </div>
                <div className="absolute -inset-s-8 top-60 max-xl:hidden">
                    <div className="bg-base-100/60 rounded-box border-base-100 relative w-42 cursor-pointer border px-5 py-3 dark:border-white/5 dark:bg-white/5">
                        <span className="iconify lucide--trophy text-base-content/20 absolute inset-e-3 top-2.5 size-8"></span>
                        <p className="text-primary text-xl font-semibold">1000+</p>
                        <p className="font-medium">Licenses Sold</p>
                    </div>
                </div>
            </div>
        </div>
    );
};
