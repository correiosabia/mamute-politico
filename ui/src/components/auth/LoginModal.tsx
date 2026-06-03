import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import logoMamute from "@/assets/logo-mamute.png";
import {
  sendMagicLink,
  sendMagicLinkUnified,
  type MagicLinkEmailType,
} from "./sendMagicLink";

const emailSchema = z.string().trim().email({ message: "E-mail inválido" });

const RESEND_COOLDOWN_MS = 45_000;

export type LoginModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Bump when `openLogin` is invoked so the form resets even if the dialog was already closed. */
  launchKey: number;
  initialEmail: string;
};

function formatErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && !error.response) {
    return "Não foi possível conectar. Verifique sua rede.";
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Algo deu errado. Tente novamente em instantes.";
}

export function LoginModal({
  open,
  onOpenChange,
  launchKey,
  initialEmail,
}: LoginModalProps) {
  const [email, setEmail] = useState(initialEmail);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState<{
    email: string;
    emailType: MagicLinkEmailType;
  } | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setEmail(initialEmail);
    setFieldErrors({});
    setError(null);
    setSuccess(null);
    setIsSubmitting(false);
    setCooldownUntil(0);
    setNow(Date.now());
  }, [open, launchKey, initialEmail]);

  useEffect(() => {
    if (open && !success) {
      const id = window.requestAnimationFrame(() => {
        emailInputRef.current?.focus();
      });
      return () => window.cancelAnimationFrame(id);
    }
  }, [open, success, launchKey]);

  const bumpCooldown = useCallback(() => {
    const nextNow = Date.now();
    setNow(nextNow);
    setCooldownUntil(nextNow + RESEND_COOLDOWN_MS);
  }, []);

  useEffect(() => {
    if (!open || !success || cooldownUntil <= now) {
      return;
    }
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 1_000);
    return () => window.clearInterval(id);
  }, [cooldownUntil, now, open, success]);

  const validateEmail = (): boolean => {
    const emailResult = emailSchema.safeParse(email);
    if (!emailResult.success) {
      setFieldErrors({
        email:
          emailResult.error.flatten().formErrors[0] ?? "E-mail inválido",
      });
      return false;
    }
    setFieldErrors({});
    return true;
  };

  const submit = async () => {
    if (!validateEmail()) {
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const { emailType } = await sendMagicLinkUnified({
        email: emailSchema.parse(email),
      });
      setSuccess({ email: email.trim(), emailType });
      bumpCooldown();
    } catch (e) {
      setError(formatErrorMessage(e));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (!success || Date.now() < cooldownUntil || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await sendMagicLink({
        email: success.email,
        emailType: success.emailType,
      });
      bumpCooldown();
    } catch (e) {
      setError(formatErrorMessage(e));
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetToForm = () => {
    setSuccess(null);
    setError(null);
    setFieldErrors({});
  };

  const cooldownRemaining = Math.max(
    0,
    Math.ceil((cooldownUntil - now) / 1000)
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-black/10 sm:rounded-2xl">
        <DialogHeader className="space-y-3 text-left">
          <div className="flex flex-col items-center gap-3 pr-8">
            <img
              src={logoMamute}
              alt="Mamute Político"
              className="h-9 w-auto"
            />
            <div className="w-full">
              <DialogTitle className="text-lg font-bold text-[#393939]">
                {success ? "Verifique seu e-mail" : "Acesso à conta"}
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {success
                  ? `Enviamos um link para ${success.email}. Verifique sua caixa de entrada (e o spam).`
                  : "Enviaremos um link de acesso para seu e-mail."}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {success ? (
          <div className="space-y-4 pt-1">
            {error ? (
              <p className="text-sm text-destructive">{error}</p>
            ) : null}
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                className="rounded-full"
                onClick={resetToForm}
              >
                Trocar e-mail
              </Button>
              <Button
                type="button"
                className="rounded-full bg-[#ff0004] text-white hover:bg-[#ff0004]/90"
                onClick={handleResend}
                disabled={isSubmitting || cooldownRemaining > 0}
              >
                {cooldownRemaining > 0
                  ? `Reenviar link (${cooldownRemaining}s)`
                  : "Reenviar link"}
              </Button>
            </div>
          </div>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="login-email">E-mail</Label>
              <Input
                id="login-email"
                ref={emailInputRef}
                type="email"
                autoComplete="email"
                placeholder="voce@exemplo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={Boolean(fieldErrors.email || error)}
              />
              {fieldErrors.email ? (
                <p className="text-sm text-destructive">{fieldErrors.email}</p>
              ) : null}
              {error ? (
                <p className="pt-3 text-sm text-destructive">{error}</p>
              ) : null}
            </div>

            <Button
              type="submit"
              className="w-full rounded-full bg-[#ff0004] text-white hover:bg-[#ff0004]/90"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Enviando…" : "Enviar link de acesso"}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
