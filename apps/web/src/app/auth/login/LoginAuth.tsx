"use client";

import Link from "next/link";
import React, { useActionState, useState } from "react";

import { signIn, type AuthFormState } from "@/lib/auth/actions";

const initial: AuthFormState = { error: "" };

export const LoginAuth = () => {
    const [showPassword, setShowPassword] = useState(false);
    const [state, formAction, pending] = useActionState(signIn, initial);

    return (
        <form action={formAction}>
            <fieldset className="fieldset">
                <legend className="fieldset-legend">Email Address</legend>
                <label className="input w-full focus:outline-0">
                    <span className="iconify lucide--mail text-base-content/80 size-5"></span>
                    <input
                        className="grow focus:outline-0"
                        placeholder="Email Address"
                        type="email"
                        name="email"
                        autoComplete="email"
                        required
                    />
                </label>
            </fieldset>

            <fieldset className="fieldset">
                <legend className="fieldset-legend">Password</legend>
                <label className="input w-full focus:outline-0">
                    <span className="iconify lucide--key-round text-base-content/80 size-5"></span>
                    <input
                        className="grow focus:outline-0"
                        placeholder="Password"
                        name="password"
                        autoComplete="current-password"
                        required
                        type={showPassword ? "text" : "password"}
                    />
                    <button
                        className="btn btn-xs btn-ghost btn-circle"
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        aria-label="Password">
                        {showPassword ? (
                            <span className="iconify lucide--eye-off size-4" />
                        ) : (
                            <span className="iconify lucide--eye size-4" />
                        )}
                    </button>
                </label>
            </fieldset>

            <div className="text-end">
                <Link className="label-text text-base-content/80 text-xs" href="/auth/forgot-password">
                    Forgot Password?
                </Link>
            </div>

            {state.error ? <p className="text-error mt-3 text-sm">{state.error}</p> : null}

            <button className="btn btn-primary btn-wide mt-4 max-w-full gap-3 md:mt-6" type="submit" disabled={pending}>
                <span className="iconify lucide--log-in size-4" />
                Login
            </button>

            <button className="btn btn-ghost btn-wide border-base-300 mt-4 max-w-full gap-3" type="button" disabled>
                <img src="/images/brand-logo/google-mini.svg" className="size-6" alt="" />
                Login with Google
            </button>

            <p className="text-base-content/80 mt-4 text-center text-sm md:mt-6">
                Haven&apos;t account
                <Link className="text-primary ms-1 hover:underline" href="/auth/register">
                    Create One
                </Link>
            </p>
        </form>
    );
};
