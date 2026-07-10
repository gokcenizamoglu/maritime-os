import { SITE_NAME } from "@/config/site";

export function SiteHeader() {
  return (
    <header className="border-b border-black/[.08] dark:border-white/[.145]">
      <div className="mx-auto flex w-full max-w-5xl items-center px-6 py-4">
        <span className="text-lg font-semibold tracking-tight">
          {SITE_NAME}
        </span>
      </div>
    </header>
  );
}
