"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AudioLines, Loader2 } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/Button";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@leadaro.io");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post<{ token: string; user: { name: string } }>(
        "/auth/login",
        { email, password },
      );
      setToken(r.token);
      router.push("/voice");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-page px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-[360px] rounded-card border border-line bg-surface p-7 shadow-card"
      >
        <div className="mb-6 flex items-center gap-2">
          <span className="grid size-7 place-items-center rounded-md bg-gradient-to-br from-primary-deep to-c5">
            <AudioLines size={15} strokeWidth={2.5} className="text-white" />
          </span>
          <span className="text-lg font-semibold tracking-tight text-ink">Leadaro</span>
        </div>

        <h1 className="text-lg font-semibold text-ink">Sign in</h1>
        <p className="mt-1 text-base text-muted">
          Manage your voice and call outreach campaigns.
        </p>

        <label className="mt-5 block">
          <span className="text-sm font-medium text-ink">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 h-9 w-full rounded-pill border border-line-strong bg-surface px-3 text-base outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
          />
        </label>

        <label className="mt-3 block">
          <span className="text-sm font-medium text-ink">Password</span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 h-9 w-full rounded-pill border border-line-strong bg-surface px-3 text-base outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
          />
        </label>

        {error && (
          <p className="mt-3 rounded-md bg-neg-wash px-2.5 py-2 text-sm text-neg">
            {error}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          size="md"
          disabled={busy}
          className="mt-5 w-full"
        >
          {busy && <Loader2 size={14} className="animate-spin" />}
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
