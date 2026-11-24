import { displayNameProblems } from "./display-name.ts";

export type ProfileNameEdit = {
    changed: boolean;
    canSave: boolean;
    problem: string | null;
    next: string;
};

/** Cancel when the field differs. Save only when the trimmed name is a real change. */
export function profileNameEdit(saved: string, draft: string): ProfileNameEdit {
    const next = draft.trim();
    const changed = draft !== saved;
    const problem = changed ? displayNameProblems(draft) : null;
    return {
        changed,
        canSave: problem === null && next !== saved.trim(),
        problem,
        next,
    };
}
