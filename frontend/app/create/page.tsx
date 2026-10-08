"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import RepNavbar from "@/components/brand/RepNavbar";
import { createProfile, findProfileByName } from "@/lib/api";
import { saveProfileId } from "@/lib/profileSession";

const features = [
  {
    title: "Share your story",
    body: "Add your profile, skills, experience and more.",
    bubble: "bg-[#F8E4EE] text-[#C45C86]",
    icon: "user" as const,
  },
  {
    title: "Showcase your work",
    body: "Include your projects, achievements and knowledge.",
    bubble: "bg-[#FBF3DC] text-[#C4922A]",
    icon: "star" as const,
  },
  {
    title: "Let it represent you",
    body: "Your MyRep can talk and share information about you.",
    bubble: "bg-[#F0E6F8] text-[#8B6AAE]",
    icon: "chat" as const,
  },
];

export default function CreatePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    setError(null);
    try {
      const existing = await findProfileByName(trimmed);
      const profile = existing ?? (await createProfile({ name: trimmed }));
      saveProfileId(profile.id);
      router.push(`/profile?id=${encodeURIComponent(profile.id)}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create your MyRep.");
      setCreating(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#FBF7F2] text-[#16161D]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -left-24 top-16 h-72 w-72 rounded-full bg-[#F8D5E4]/45 blur-3xl" />
        <div className="absolute right-[6%] top-[4%] h-[28rem] w-[32rem] rounded-full bg-[#E7D4F5]/50 blur-3xl" />
        <div className="absolute bottom-[8%] left-[18%] h-64 w-[36rem] rounded-full bg-[#F8DCC8]/40 blur-3xl" />
        <div className="absolute bottom-[18%] right-[8%] h-56 w-80 rounded-full bg-[#F6E7C8]/35 blur-3xl" />
        <svg className="absolute bottom-0 left-0 h-[34vh] w-full min-h-[180px]" viewBox="0 0 1440 320" preserveAspectRatio="none">
          <path
            d="M0 180C220 240 380 90 700 150C1020 210 1180 80 1440 130V320H0Z"
            fill="#F6D5E4"
            opacity="0.45"
          />
          <path
            d="M0 230C260 150 480 270 820 190C1100 130 1260 230 1440 180V320H0Z"
            fill="#E5D4F6"
            opacity="0.38"
          />
          <path
            d="M0 260C320 220 560 300 900 250C1160 214 1300 270 1440 240V320H0Z"
            fill="#FBE6D4"
            opacity="0.4"
          />
        </svg>
        <Sparkle className="absolute left-[12%] top-[22%] h-3 w-3 text-[#F0D56A] animate-sparkle" />
        <Sparkle className="absolute left-[28%] bottom-[16%] h-2.5 w-2.5 text-[#E7D4F5] animate-sparkle [animation-delay:1.2s]" />
        <Sparkle className="absolute right-[18%] top-[14%] h-3.5 w-3.5 text-[#F0D56A] animate-sparkle [animation-delay:0.6s]" />
        <Sparkle className="absolute right-[8%] top-[42%] h-2 w-2 text-[#F6C6DE] animate-sparkle [animation-delay:1.8s]" />
        <Sparkle className="absolute bottom-[22%] left-[8%] h-2 w-2 text-[#F0D56A] animate-sparkle [animation-delay:0.4s]" />
      </div>

      <RepNavbar />

      <main className="relative z-10 mx-auto flex min-h-[calc(100dvh-4.25rem)] w-full items-center px-[5.5vw] py-10 lg:px-[6.5vw] lg:py-4">
        <div className="grid w-full grid-cols-1 items-center gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(400px,480px)_minmax(240px,0.85fr)] xl:gap-x-10">
          <section className="max-w-[38rem] xl:col-start-1 xl:row-start-1">
            <h1 className="font-display text-[3.15rem] leading-[0.98] tracking-[-0.02em] text-[#16161D] sm:text-[3.7rem] lg:text-[4rem] xl:text-[4.7rem]">
              Create
              <br />
              Your <span className="text-[#9B4D86]">MyRep</span>
            </h1>
            <p className="mt-6 max-w-[26rem] text-[15px] leading-7 text-[#5C5666] sm:text-base">
              Build your personal AI representative.
              <br />
              Add your details, knowledge and work to
              <br className="hidden sm:block" />
              make it truly you.
            </p>

            <ul className="mt-10 space-y-6 sm:mt-12 sm:space-y-7">
              {features.map((feature) => (
                <li key={feature.title} className="flex items-start gap-4">
                  <span
                    className={`mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${feature.bubble}`}
                  >
                    <FeatureIcon name={feature.icon} />
                  </span>
                  <span>
                    <span className="block text-[15px] font-semibold text-[#1C1A22]">{feature.title}</span>
                    <span className="mt-0.5 block max-w-[22rem] text-sm leading-relaxed text-[#6B6574]">
                      {feature.body}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <div className="relative mx-auto flex w-full max-w-[22rem] justify-center xl:col-start-3 xl:row-start-1 xl:mx-0 xl:max-w-none xl:justify-end">
            <div
              className="pointer-events-none absolute top-6 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-[#F4D4EA]/55 blur-3xl lg:top-4 lg:right-0 lg:left-auto lg:h-72 lg:w-80 lg:translate-x-0"
              aria-hidden="true"
            />
            <img
              src="/images/rep-chosen.png?v=2"
              alt="Rep"
              className="pointer-events-none relative z-[1] h-auto w-[min(78vw,300px)] object-contain sm:w-[340px] lg:w-[min(100%,420px)] xl:w-[min(100%,460px)]"
            />
          </div>

          <form
              onSubmit={onSubmit}
              className="relative z-10 mx-auto w-full max-w-[480px] rounded-[22px] border border-[#F3EBE3] bg-white/92 px-7 py-7 shadow-[0_24px_60px_-32px_rgba(70,36,58,0.35)] backdrop-blur-md sm:px-8 xl:col-start-2 xl:row-start-1"
            >
              <h2 className="font-display text-[2rem] leading-none text-[#16161D] sm:text-[2.15rem]">
                Let&apos;s get started
              </h2>
              <p className="mt-3 max-w-[22rem] text-sm leading-relaxed text-[#5C5666]">
                Enter a name for your MyRep. You can add the rest details in your workspace.
              </p>

              <label className="mt-6 block text-sm font-medium text-[#2C2933]" htmlFor="name">
                Name
              </label>
              <div className="relative mt-2">
                <span className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-[#8E8796]">
                  <FeatureIcon name="user" />
                </span>
                <input
                  id="name"
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Maitri, My Professional Rep"
                  className="w-full rounded-full border border-[#E6DFD6] bg-white py-3 pr-4 pl-11 text-sm text-[#16161D] outline-none transition placeholder:text-[#A39EAA] focus:border-[#D4B8D8] focus:ring-4 focus:ring-[#E7D4F5]/70"
                />
              </div>

              {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

              <button
                type="submit"
                disabled={creating || !name.trim()}
                className="mt-5 flex h-[50px] w-full items-center justify-center rounded-full bg-[#1A1A1F] text-sm font-medium text-white transition duration-200 hover:-translate-y-px hover:bg-[#2C2C34] disabled:translate-y-0 disabled:opacity-50"
              >
                {creating ? "Creating…" : "Create MyRep →"}
              </button>

            </form>
        </div>
      </main>
    </div>
  );
}

function FeatureIcon({ name }: { name: "user" | "star" | "chat" }) {
  if (name === "star") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 3.2 14.1 8.7l5.9.5-4.5 3.7 1.4 5.7L12 15.8 7.1 18.6l1.4-5.7L4 9.2l5.9-.5L12 3.2Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (name === "chat") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M7 17.2 4.6 19.5V6.8A2.3 2.3 0 0 1 6.9 4.5h10.2a2.3 2.3 0 0 1 2.3 2.3v7.1a2.3 2.3 0 0 1-2.3 2.3H7Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M5.6 19c1.35-2.5 3.5-3.6 6.4-3.6s5.05 1.1 6.4 3.6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function Sparkle({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0.4 9.15 5.7 14.6 8 9.15 10.3 8 15.6 6.85 10.3 1.4 8l4.45-2.3L8 .4Z" />
    </svg>
  );
}
