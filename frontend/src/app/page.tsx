import { SITE_DESCRIPTION, SITE_NAME } from "@/config/site";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-start justify-center px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        {SITE_NAME}
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-7 text-zinc-600 dark:text-zinc-400">
        {SITE_DESCRIPTION}
      </p>
    </main>
  );
}
