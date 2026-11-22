"use client";

import Link from "next/link";
import React, { useActionState, useState } from "react";

import { signUp, type AuthFormState } from "@/lib/auth/actions";
import { PASSWORD_RULE } from "@/lib/auth/password";

const initial: AuthFormState = { error: "" };

export const RegisterAuth = () => {
    const [showPassword, setShowPassword] = useState(false);
    const [state, formAction, pending] = useActionState(signUp, initial);

    return (
        <form className="min-w-0" action={formAction}>
            <div className="grid grid-cols-1 gap-x-4 xl:grid-cols-2">
                <fieldset className="fieldset">
                    <legend className="fieldset-legend">First Name</legend>
                    <label className="input w-full focus:outline-0">
                        <span className="iconify lucide--user text-base-content/80 size-5"></span>
                        <input className="grow focus:outline-0" placeholder="First Name" type="text" name="first_name" />
                    </label>
                </fieldset>
                <fieldset className="fieldset">
                    <legend className="fieldset-legend">Last Name</legend>
                    <label className="input w-full focus:outline-0">
                        <span className="iconify lucide--user text-base-content/80 size-5"></span>
                        <input className="grow focus:outline-0" placeholder="Last Name" type="text" name="last_name" />
                    </label>
                </fieldset>
            </div>
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
                        autoComplete="new-password"
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
                <p className="text-base-content/60 mt-2 text-sm text-wrap">{PASSWORD_RULE}</p>
            </fieldset>

            {state.error ? <p className="text-error mt-3 text-sm">{state.error}</p> : null}

            <button className="btn btn-primary btn-wide mt-4 max-w-full gap-3 md:mt-6" type="submit" disabled={pending}>
                <span className="iconify lucide--user-plus size-4" />
                Register
            </button>

            <button className="btn btn-ghost btn-wide border-base-300 mt-4 max-w-full gap-3" type="button" disabled>
                <img src="/images/brand-logo/google-mini.svg" className="size-6" alt="" />
                Register with Google
            </button>
            <p className="text-base-content/80 mt-4 text-center text-sm md:mt-6">
                I have already to
                <Link className="text-primary ms-1 hover:underline" href="/auth/login">
                    Login
                </Link>
            </p>
        </form>
    );
};
