import { SITE_NAME } from "@/config/site";

export function SiteFooter() {
  return (
    <footer className="border-t border-black/[.08] dark:border-white/[.145]">
      <div className="mx-auto w-full max-w-5xl px-6 py-6 text-sm text-zinc-600 dark:text-zinc-400">
        &copy; {new Date().getFullYear()} {SITE_NAME}
      </div>
    </footer>
  );
}
