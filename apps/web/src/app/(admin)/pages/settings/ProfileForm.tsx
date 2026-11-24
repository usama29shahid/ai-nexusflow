"use client";

import React, { useActionState, useRef, useState } from "react";

import { ProfileWhen } from "@/app/(admin)/pages/settings/ProfileWhen";
import { type ProfileFormState, updateDisplayName } from "@/lib/profile/actions";
import { DISPLAY_NAME_MAX } from "@/lib/profile/display-name";
import { profileNameEdit } from "@/lib/profile/profile-name-edit";

const initial: ProfileFormState = { error: "", saved: false };

export const ProfileForm = ({
    loadError,
    loadErrorMessage,
    displayName,
    email,
    memberSince,
}: {
    loadError: boolean;
    loadErrorMessage: string;
    displayName: string;
    email: string;
    memberSince: string | null;
}) => {
    const [state, formAction, pending] = useActionState(updateDisplayName, initial);
    const [draft, setDraft] = useState(displayName);
    const [baseline, setBaseline] = useState(displayName);
    const formRef = useRef<HTMLFormElement>(null);
    const dialogRef = useRef<HTMLDialogElement>(null);
    const allowSubmit = useRef(false);

    if (baseline !== displayName) {
        setBaseline(displayName);
        setDraft(displayName);
    }

    const edit = profileNameEdit(displayName, draft);

    const openConfirm = () => {
        if (!edit.canSave || loadError) {
            return;
        }
        dialogRef.current?.showModal();
    };

    const cancelEdit = () => {
        setDraft(displayName);
        dialogRef.current?.close();
    };

    const confirmSave = () => {
        if (!edit.canSave || loadError) {
            return;
        }
        allowSubmit.current = true;
        formRef.current?.requestSubmit();
        allowSubmit.current = false;
    };

    return (
        <>
            <form
                ref={formRef}
                action={loadError ? undefined : formAction}
                onSubmit={(event) => {
                    if (allowSubmit.current) {
                        dialogRef.current?.close();
                        return;
                    }
                    event.preventDefault();
                    openConfirm();
                }}
            >
                <div className="card bg-base-100 card-border mt-6">
                    <div className="card-body sm:p-8">
                        <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
                            <div className="xl:col-span-2">
                                <div className="flex items-center gap-2">
                                    <span className="iconify lucide--id-card size-5" />
                                    <p className="text-lg font-medium">User Profile</p>
                                </div>
                                <p className="text-base-content/60">Your account name and email</p>
                            </div>
                            <div className="flex gap-5 max-lg:flex-col xl:col-span-3">
                                <div className="avatar">
                                    <div className="bg-base-200 size-24 min-w-24 overflow-hidden rounded-full p-1 pb-0">
                                        <img src="/images/avatars/1.png" alt="" />
                                    </div>
                                </div>
                                <div className="fieldset grid grow grid-cols-1 gap-5 lg:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="fieldset-label" htmlFor="display-name">
                                            Display name
                                        </label>
                                        <label className="input w-full">
                                            <span className="iconify lucide--user text-base-content/60 size-4.5"></span>
                                            <input
                                                type="text"
                                                className="grow"
                                                placeholder="Name"
                                                id="display-name"
                                                name="display_name"
                                                autoComplete="name"
                                                required={!loadError}
                                                maxLength={DISPLAY_NAME_MAX}
                                                value={draft}
                                                onChange={(event) => setDraft(event.target.value)}
                                                disabled={loadError}
                                            />
                                        </label>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="fieldset-label" htmlFor="email">
                                            Email
                                        </label>
                                        <label className="input w-full">
                                            <span className="iconify lucide--mail text-base-content/60 size-4.5"></span>
                                            <input
                                                type="email"
                                                className="grow"
                                                id="email"
                                                value={email}
                                                readOnly
                                                aria-readonly="true"
                                            />
                                        </label>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="fieldset-label" htmlFor="member-since">
                                            Member since
                                        </label>
                                        <label className="input w-full">
                                            <span className="iconify lucide--calendar text-base-content/60 size-4.5"></span>
                                            <span className="grow" id="member-since">
                                                <ProfileWhen iso={memberSince} withTime={false} />
                                            </span>
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        {loadError ? (
                            <p className="text-error mt-4 text-sm" role="alert">
                                {loadErrorMessage}
                            </p>
                        ) : null}
                        {edit.problem ? (
                            <p className="text-error mt-4 text-sm" role="alert">
                                {edit.problem}
                            </p>
                        ) : null}
                        {state.error ? (
                            <p className="text-error mt-4 text-sm" role="alert">
                                {state.error}
                            </p>
                        ) : null}
                        {state.saved && !edit.changed ? <p className="text-success mt-4 text-sm">Name saved.</p> : null}
                    </div>
                </div>
                <div className="mt-6 flex justify-end gap-3">
                    {edit.changed ? (
                        <button className="btn btn-sm btn-ghost" type="button" onClick={cancelEdit} disabled={pending}>
                            <span className="iconify lucide--x size-4" />
                            Cancel
                        </button>
                    ) : null}
                    <button
                        className="btn btn-sm btn-primary"
                        type="button"
                        onClick={openConfirm}
                        disabled={pending || loadError || !edit.canSave}
                    >
                        <span className="iconify lucide--arrow-up-from-line size-4" />
                        {pending ? "Saving" : "Update"}
                    </button>
                </div>
            </form>
            <dialog ref={dialogRef} className="modal" aria-labelledby="confirm-display-name">
                <div className="modal-box">
                    <h3 id="confirm-display-name" className="text-lg font-medium">
                        Save this name?
                    </h3>
                    <p className="py-4">
                        Your display name will change to <span className="font-medium">{edit.next}</span>. Email stays
                        the same.
                    </p>
                    <div className="modal-action">
                        <button
                            className="btn btn-sm btn-ghost"
                            type="button"
                            onClick={() => dialogRef.current?.close()}
                        >
                            Go back
                        </button>
                        <button
                            className="btn btn-sm btn-primary"
                            type="button"
                            onClick={confirmSave}
                            disabled={pending}
                        >
                            Save name
                        </button>
                    </div>
                </div>
                <form method="dialog" className="modal-backdrop">
                    <button>close</button>
                </form>
            </dialog>
        </>
    );
};
