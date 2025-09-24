import { useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';

import { apiRequest, extractErrorMessage } from '../utils/api';

const ACCOUNT_TYPES = [
  { label: 'Agent', value: 'AGENT' },
  { label: 'Collaborateur', value: 'COLLABORATOR' },
];

const initialFormState = {
  account_type: ACCOUNT_TYPES[0].value,
  email: '',
  password: '',
  confirmPassword: '',
  display_name: '',
  first_name: '',
  last_name: '',
  phone_number: '',
  organisation_name: '',
  job_title: '',
};

const cleanPayload = (data) => {
  const payload = { ...data };
  Object.keys(payload).forEach((key) => {
    if (payload[key] === '' || payload[key] === null || payload[key] === undefined) {
      delete payload[key];
    }
  });
  return payload;
};

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState(initialFormState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isAgent = form.account_type === 'AGENT';

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    setSuccess('');

    if (form.password !== form.confirmPassword) {
      setError('Les mots de passe ne correspondent pas.');
      setSubmitting(false);
      return;
    }

    const payload = cleanPayload({
      account_type: form.account_type,
      email: form.email.trim(),
      password: form.password,
      display_name: isAgent ? form.display_name.trim() : undefined,
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone_number: form.phone_number.trim(),
      organisation_name: !isAgent ? form.organisation_name.trim() : undefined,
      job_title: !isAgent ? form.job_title.trim() : undefined,
    });

    try {
      await apiRequest('/users/register/', {
        method: 'POST',
        body: payload,
      });
      setSuccess('Compte créé avec succès. Vous pouvez maintenant vous connecter.');
      setTimeout(() => {
        router.push('/login');
      }, 1000);
    } catch (apiError) {
      setError(extractErrorMessage(apiError, 'Impossible de créer le compte.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Head>
        <title>Inscription &bull; Sponsors Club</title>
      </Head>
      <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-12 text-slate-100">
        <div className="w-full max-w-2xl rounded-2xl bg-slate-900 px-8 py-10 shadow-2xl shadow-slate-900/50">
          <h1 className="text-3xl font-semibold tracking-tight text-white">Créer un compte</h1>
          <p className="mt-2 text-sm text-slate-400">
            Rejoignez Sponsors Club pour piloter vos partenariats et vos relations athlètes.
          </p>

          <form className="mt-8 grid gap-6" onSubmit={handleSubmit}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="account_type">
                  Type de compte
                </label>
                <select
                  id="account_type"
                  name="account_type"
                  value={form.account_type}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                >
                  {ACCOUNT_TYPES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

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
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="password">
                  Mot de passe
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={form.password}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  placeholder="••••••••"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="confirmPassword">
                  Confirmation du mot de passe
                </label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={form.confirmPassword}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  placeholder="••••••••"
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="first_name">
                  Prénom
                </label>
                <input
                  id="first_name"
                  name="first_name"
                  type="text"
                  value={form.first_name}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  placeholder="Ada"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="last_name">
                  Nom
                </label>
                <input
                  id="last_name"
                  name="last_name"
                  type="text"
                  value={form.last_name}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  placeholder="Lovelace"
                />
              </div>
            </div>

            {isAgent ? (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-200" htmlFor="display_name">
                  Nom public de l'agent
                </label>
                <input
                  id="display_name"
                  name="display_name"
                  type="text"
                  required
                  value={form.display_name}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  placeholder="Votre nom professionnel"
                />
                <p className="text-xs text-slate-500">
                  Ce nom sera visible par les athlètes et les partenaires.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-slate-200" htmlFor="organisation_name">
                    Organisation
                  </label>
                  <input
                    id="organisation_name"
                    name="organisation_name"
                    type="text"
                    value={form.organisation_name}
                    onChange={handleChange}
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                    placeholder="Votre société"
                  />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-slate-200" htmlFor="job_title">
                    Intitulé de poste
                  </label>
                  <input
                    id="job_title"
                    name="job_title"
                    type="text"
                    value={form.job_title}
                    onChange={handleChange}
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                    placeholder="Responsable marketing"
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-200" htmlFor="phone_number">
                Numéro de téléphone
              </label>
              <input
                id="phone_number"
                name="phone_number"
                type="tel"
                value={form.phone_number}
                onChange={handleChange}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                placeholder="+33 6 12 34 56 78"
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
              {submitting ? 'Création du compte…' : "S'inscrire"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Déjà inscrit ?{' '}
            <Link href="/login" className="font-medium text-cyan-300 hover:text-cyan-200">
              Se connecter
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}
