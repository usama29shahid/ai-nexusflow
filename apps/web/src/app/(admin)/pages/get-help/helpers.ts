import { IHelpTopic } from "./HelpTopic";

export type IFAQs = {
    question: string;
    answer: string;
};

export const helpTopics: IHelpTopic[] = [
    {
        title: "Getting started",
        description: "This article will be added later.",
    },
    {
        title: "Your account",
        description: "This article will be added later.",
    },
    {
        title: "The dashboard",
        description: "This article will be added later.",
    },
    {
        title: "Passwords",
        description: "This article will be added later.",
    },
];

export const accountFaqs: IFAQs[] = [
    {
        question: "How do I sign in?",
        answer: "This answer will be added later.",
    },
];

export const dashboardFaqs: IFAQs[] = [
    {
        question: "Where is the catalog dashboard?",
        answer: "This answer will be added later.",
    },
];
