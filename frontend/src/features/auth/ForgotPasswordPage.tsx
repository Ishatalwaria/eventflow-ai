import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertCircle, ArrowLeft, CheckCircle2, Mail } from "lucide-react";
import { authService } from "../../api/services/auth";
import { apiErrorMessage } from "../../api/client";
import { Button, Input, Label } from "../../components/ui";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email) {
      setError("Please enter your email address.");
      return;
    }

    setLoading(true);
    try {
      await authService.requestPasswordReset(email);
      setSubmitted(true);
    } catch (err: unknown) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 text-slate-100 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-blue-600 text-white shadow-xl shadow-blue-500/25 ring-1 ring-white/20">
            <Activity size={26} strokeWidth={2.5} />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white sm:text-3xl">
            EventFlow <span className="text-blue-400">AI</span>
          </h1>
          <h2 className="mt-4 text-lg font-medium text-slate-200">
            Reset your password
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Enter your email to receive password reset instructions
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl backdrop-blur-xl">
          {submitted ? (
            <div className="space-y-6 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-emerald-400">
                <CheckCircle2 size={28} />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-bold text-white">Check your email</h3>
                <p className="text-xs leading-relaxed text-slate-400">
                  If an account exists for <span className="text-white">{email}</span>, password reset instructions have been generated.
                </p>
              </div>
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-400 hover:text-blue-300"
              >
                <ArrowLeft size={14} /> Back to Sign In
              </Link>
            </div>
          ) : (
            <>
              {error && (
                <div className="mb-6 flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300">
                  <AlertCircle size={16} className="mt-0.5 shrink-0 text-rose-400" />
                  <div className="leading-relaxed">{error}</div>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-300">Email Address</Label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                      <Mail size={16} />
                    </div>
                    <Input
                      type="email"
                      required
                      autoComplete="email"
                      placeholder="admin@eventflow.local"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="border-white/10 bg-slate-800/80 pl-9 text-white placeholder:text-slate-500 focus-visible:ring-blue-500"
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-blue-600 font-semibold text-white shadow-lg shadow-blue-600/30 hover:bg-blue-500"
                >
                  {loading ? "Sending Instructions…" : "Send Reset Link"}
                </Button>
              </form>

              <div className="mt-6 border-t border-white/10 pt-6 text-center text-xs text-slate-400">
                Remembered your password?{" "}
                <Link to="/login" className="font-semibold text-blue-400 hover:text-blue-300">
                  Sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
