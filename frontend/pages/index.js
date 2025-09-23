export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 p-8 text-slate-100">
      <div className="w-full max-w-2xl rounded-2xl bg-slate-900 p-10 shadow-2xl shadow-slate-900/50">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Sponsors Club</h1>
        <p className="mt-4 text-lg text-slate-300">
          Frontend Next.js + Tailwind starter ready to consume the Sponsors Club API.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <a
            className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-center font-semibold transition hover:-translate-y-0.5 hover:border-cyan-400 hover:text-cyan-200 hover:shadow-lg hover:shadow-cyan-500/20"
            href="https://nextjs.org/docs"
            target="_blank"
            rel="noreferrer"
          >
            Next.js Documentation
          </a>
          <a
            className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-center font-semibold transition hover:-translate-y-0.5 hover:border-emerald-400 hover:text-emerald-200 hover:shadow-lg hover:shadow-emerald-500/20"
            href="https://tailwindcss.com/docs"
            target="_blank"
            rel="noreferrer"
          >
            Tailwind CSS Docs
          </a>
        </div>
      </div>
    </main>
  );
}
