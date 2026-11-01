import { Eye, EyeOff, Loader2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ApiError } from "@/api";
import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/utils";

type Mode = "login" | "register";

const inputClass =
  "h-10 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-zinc-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-zinc-800 dark:bg-zinc-900";

interface PasswordFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  placeholder?: string;
  visible: boolean;
  onToggle: () => void;
  invalid?: boolean;
}

function PasswordField({ label, value, onChange, autoComplete, placeholder, visible, onToggle, invalid }: PasswordFieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">{label}</span>
      <div className="relative">
        <input
          className={cn(inputClass, "pr-10", invalid && "border-red-400 focus:border-red-400 focus:ring-red-400/20")}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={invalid}
          required
        />
        <button
          type="button"
          onClick={onToggle}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-xl text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </label>
  );
}

export function AuthPage() {
  const login = useAuth((s) => s.login);
  const register = useAuth((s) => s.register);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const isRegister = mode === "register";
  const mismatch = isRegister && confirm.length > 0 && password !== confirm;

  const switchMode = (next: Mode) => {
    setMode(next);
    setPassword("");
    setConfirm("");
    setError("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (isRegister && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setPending(true);
    setError("");
    try {
      if (isRegister) await register(email, password, confirm);
      else await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Please try again.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex flex-col items-center text-center">
          <Logo className="h-10 w-10" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">
            {isRegister ? "Create your account" : "Log in to ResearchOps"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">Technical research with evidence you can inspect.</p>
        </div>

        <div className="mt-6 grid grid-cols-2 rounded-xl bg-zinc-100 p-1 text-sm dark:bg-zinc-900">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => switchMode(m)}
              aria-pressed={mode === m}
              className={cn(
                "h-8 rounded-lg font-medium transition-colors",
                mode === m
                  ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
              )}
            >
              {m === "login" ? "Log in" : "Register"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">Email</span>
            <input
              className={inputClass}
              type="email"
              autoComplete={isRegister ? "email" : "username"}
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <PasswordField
            label={isRegister ? "New password" : "Password"}
            value={password}
            onChange={setPassword}
            autoComplete={isRegister ? "new-password" : "current-password"}
            placeholder={isRegister ? "At least 8 characters, a letter and a number" : "Your password"}
            visible={showPassword}
            onToggle={() => setShowPassword((v) => !v)}
          />
          {isRegister && (
            <>
              <PasswordField
                label="Confirm new password"
                value={confirm}
                onChange={setConfirm}
                autoComplete="new-password"
                placeholder="Enter the same password again"
                visible={showConfirm}
                onToggle={() => setShowConfirm((v) => !v)}
                invalid={mismatch}
              />
              {mismatch && <p className="text-xs text-red-600 dark:text-red-400">Passwords do not match.</p>}
            </>
          )}

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-400">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" className="w-full" disabled={pending || mismatch}>
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRegister ? "Create account" : "Log in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
