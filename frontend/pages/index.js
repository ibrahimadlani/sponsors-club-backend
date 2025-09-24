import Head from 'next/head';
import Link from 'next/link';

export default function Home() {
  return (
    <>
      <Head>
        <title>Sponsors Club &bull; Plateforme partenariats</title>
      </Head>
      <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 py-16 text-slate-100">
        <div className="w-full max-w-4xl rounded-3xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-12 shadow-2xl shadow-slate-950/60">
          <div className="grid gap-12 lg:grid-cols-[1.35fr_1fr] lg:items-center">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
                Sponsors Club
              </p>
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-white sm:text-5xl">
                Pilotez vos collaborations athlètes depuis un hub unique.
              </h1>
              <p className="mt-6 text-lg text-slate-300">
                Connectez-vous à l&apos;API Sponsors Club pour gérer vos comptes agents, collaborer avec votre équipe et suivre vos campagnes en temps réel.
              </p>
              <div className="mt-10 flex flex-col gap-4 sm:flex-row">
                <Link
                  href="/login"
                  className="inline-flex items-center justify-center rounded-xl bg-cyan-500 px-6 py-3 text-sm font-semibold text-cyan-950 shadow-lg shadow-cyan-500/25 transition hover:bg-cyan-400"
                >
                  Se connecter
                </Link>
                <Link
                  href="/register"
                  className="inline-flex items-center justify-center rounded-xl border border-slate-600 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:border-cyan-400 hover:text-cyan-200"
                >
                  Créer un compte
                </Link>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-6">
              <h2 className="text-base font-semibold text-slate-200">
                Pile technologique prête pour la production
              </h2>
              <ul className="mt-4 space-y-3 text-sm text-slate-400">
                <li className="flex items-start gap-3">
                  <span className="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" aria-hidden />
                  <span>Authentification JWT via <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-100">/api/users/login/</code>.</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" aria-hidden />
                  <span>Inscription des agents et collaborateurs directement sur <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-100">/api/users/register/</code>.</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" aria-hidden />
                  <span>Base configurable via <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-100">NEXT_PUBLIC_API_BASE_URL</code>.</span>
                </li>
              </ul>
              <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900/80 p-4 text-xs text-slate-400">
                Besoin d&apos;un environnement local ? Lancez <code className="font-semibold text-slate-200">docker compose up</code> puis ouvrez <code className="font-semibold text-slate-200">http://localhost:3000</code>.
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
