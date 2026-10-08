"use client";

import RepAvatar from "../brand/RepAvatar";

interface Props {
  onSelect: (question: string) => void;
  personName?: string;
}

export default function SuggestedQuestions({ onSelect, personName }: Props) {
  const question = personName
    ? `What projects has ${personName} built?`
    : "What projects have they built?";

  return (
    <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
      <RepAvatar size="lg" state="idle" interactive={false} />
      <p className="font-handwriting mt-4 text-3xl text-[#6D5A86]">Hi, I&apos;m Rep.</p>
      <button
        type="button"
        onClick={() => onSelect(question)}
        className="mt-6 text-sm text-[#16161D] underline-offset-4 hover:underline"
      >
        {question}
      </button>
    </div>
  );
}
