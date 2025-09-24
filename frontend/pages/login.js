import { useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';

import { apiRequest, extractErrorMessage, storeTokens } from '../utils/api';

const initialFormState = {
  email: '',
  password: '',
};

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState(initialFormState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const payload = await apiRequest('/users/login/', {
        method: 'POST',
        body: {
          email: form.email.trim(),
          password: form.password,
        },
      });
      storeTokens(payload);
      setSuccess('Connexion réussie. Redirection en cours...');
      setTimeout(() => {
        router.push('/');
      }, 800);
    } catch (apiError) {
      setError(extractErrorMessage(apiError, 'Identifiants invalides.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Head>
        <title>Connexion &bull; Sponsors Club</title>
      </Head>
      <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-12 text-slate-100">
        <div className="w-full max-w-md rounded-2xl bg-slate-900 px-8 py-10 shadow-2xl shadow-slate-900/50">
          <h1 className="text-3xl font-semibold tracking-tight text-white">Connexion</h1>
          <p className="mt-2 text-sm text-slate-400">
            Accédez à votre compte Sponsors Club pour gérer vos collaborations.
          </p>

          <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-200" htmlFor="email">
                Adresse e-mail
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={form.email}
                onChange={handleChange}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                placeholder="vous@example.com"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-200" htmlFor="password">
                Mot de passe
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={form.password}
                onChange={handleChange}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                placeholder="••••••••"
                minLength={8}
              />
            </div>

            {error ? (
              <div className="rounded-lg border border-rose-500/60 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {error}
              </div>
            ) : null}

            {success ? (
              <div className="rounded-lg border border-emerald-500/60 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                {success}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-cyan-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {submitting ? 'Connexion en cours…' : 'Se connecter'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Pas encore de compte ?{' '}
            <Link href="/register" className="font-medium text-cyan-300 hover:text-cyan-200">
              Créer un compte
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}
