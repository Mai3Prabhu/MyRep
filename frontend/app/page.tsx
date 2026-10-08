"use client";

import Link from "next/link";
import RepNavbar from "@/components/brand/RepNavbar";

export default function Home() {
  return (
    <div className="min-h-screen bg-[#FBF8F4] text-[#16161D]">
      <RepNavbar />

      <main className="mx-auto flex min-h-[calc(100vh-4.25rem)] w-full max-w-6xl flex-col items-center justify-center px-6 py-16 md:px-10 lg:flex-row lg:items-center lg:justify-between lg:gap-16 lg:py-20">
        <div className="max-w-xl text-center lg:text-left">
          <p className="text-sm tracking-wide text-[#6B6574]">MyRep</p>
          <h1 className="font-display mt-4 text-[3.1rem] leading-[1.02] text-[#16161D] sm:text-6xl lg:text-[4.4rem]">
            Your professional
            <br />
            identity, <span className="italic text-[#3C3450]">powered by AI.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-md text-base leading-relaxed text-[#5C5666] lg:mx-0">
            Create an AI representative that knows your work, understands your
            experience, and can talk about it for you.
          </p>
          <div className="mt-9 flex flex-col items-center gap-4 lg:items-start">
            <Link
              href="/create"
              className="inline-flex items-center gap-2 rounded-full bg-[#16161D] px-5 py-2.5 text-sm text-white transition-colors hover:bg-[#2A2A33]"
            >
              Create MyRep
              <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>

        <div className="relative mt-16 flex flex-col items-center lg:mt-0">
          <div className="pointer-events-none absolute -top-6 left-6 h-3 w-3 rounded-full bg-[#F0D56A] animate-sparkle" />
          <div className="pointer-events-none absolute top-10 -right-2 h-2 w-2 rounded-full bg-[#E7D4F5] animate-sparkle [animation-delay:1s]" />
          <div className="relative h-[440px] w-[300px] sm:h-[520px] sm:w-[360px]">
            <img
              src="/images/rep-chosen.png?v=2"
              alt="Rep"
              className="h-full w-full object-contain"
            />
          </div>
          <p className="font-handwriting -mt-2 text-3xl text-[#6D5A86]">Hi, I&apos;m Rep.</p>
        </div>
      </main>
    </div>
  );
}
