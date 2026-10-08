import RepNavbar from "@/components/brand/RepNavbar";

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-[#FBF8F4] text-[#16161D]">
      <RepNavbar />
      <main className="flex min-h-[calc(100vh-4.25rem)] flex-col items-center justify-center px-6 py-16 text-center">
        <div className="h-[420px] w-[280px] sm:h-[480px] sm:w-[320px]">
          <img
            src="/images/rep-chosen.png?v=2"
            alt="Rep"
            className="h-full w-full object-contain"
          />
        </div>
        <p className="font-handwriting text-4xl text-[#6D5A86]">Hi, I&apos;m Rep.</p>
      </main>
    </div>
  );
}
