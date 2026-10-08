"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import RepAvatar from "./RepAvatar";
import { getSavedProfileId } from "@/lib/profileSession";

interface RepNavbarProps {
  chatHref?: string;
  profileHref?: string;
}

export default function RepNavbar({ chatHref, profileHref }: RepNavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);

  useEffect(() => {
    setSavedId(getSavedProfileId());
  }, []);

  const chat =
    chatHref ??
    (savedId ? `/profile/chat?id=${encodeURIComponent(savedId)}` : "/create");
  const profile =
    profileHref ??
    (savedId ? `/profile?id=${encodeURIComponent(savedId)}` : "/create");

  return (
    <header className="app-header border-b border-[#E6DFD4] bg-[#FBF8F4]/95 backdrop-blur-sm">
      <div className="flex h-16 w-full max-w-none items-center justify-between px-6 md:h-[4.25rem] md:px-8 lg:px-10">
        <Link href="/" className="flex items-center gap-2.5" aria-label="MyRep home">
          <RepAvatar size="sm" state="idle" interactive={false} />
          <span className="font-display text-[1.65rem] leading-none tracking-tight text-[#16161D]">
            MyRep
          </span>
        </Link>

        <nav className="hidden items-center gap-2 md:flex" aria-label="Account">
          <Link
            href={chat}
            aria-label="Chat"
            title="Chat"
            className="flex h-10 w-10 items-center justify-center rounded-full text-[#3D3A45] transition-colors hover:bg-white hover:text-[#16161D]"
          >
            <ChatIcon />
          </Link>
          <Link
            href={profile}
            aria-label="Profile"
            title="Profile"
            className="flex h-10 w-10 items-center justify-center rounded-full text-[#3D3A45] transition-colors hover:bg-white hover:text-[#16161D]"
          >
            <ProfileIcon />
          </Link>
        </nav>

        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full text-[#16161D] md:hidden"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <MenuIcon open={menuOpen} />
        </button>
      </div>

      {menuOpen && (
        <div className="border-t border-[#E6DFD4] px-6 py-3 md:hidden">
          <Link
            href={chat}
            className="block py-2.5 text-sm text-[#16161D]"
            onClick={() => setMenuOpen(false)}
          >
            Chat
          </Link>
          <Link
            href={profile}
            className="block py-2.5 text-sm text-[#16161D]"
            onClick={() => setMenuOpen(false)}
          >
            Profile
          </Link>
        </div>
      )}
    </header>
  );
}

function ChatIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 17.5 4.5 20V6.5A2.5 2.5 0 0 1 7 4h10a2.5 2.5 0 0 1 2.5 2.5v8A2.5 2.5 0 0 1 17 17H7Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ProfileIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M5.5 19.2c1.4-2.6 3.6-3.7 6.5-3.7s5.1 1.1 6.5 3.7"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
        <path d="M4 4l10 10M14 4 4 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
