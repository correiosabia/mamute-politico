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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import logoMamute from "@/assets/logo-mamute.png";
import {
  isMemberNotFoundError,
  sendMagicLink,
  type MagicLinkEmailType,
} from "./sendMagicLink";

const emailSchema = z.string().trim().email({ message: "E-mail inválido" });

const nameSchema = z
  .string()
  .trim()
  .max(120, { message: "Nome muito longo" })
  .optional();

const RESEND_COOLDOWN_MS = 45_000;

export type LoginModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Bump when `openLogin` is invoked so the form resets even if the dialog was already closed. */
  launchKey: number;
  initialTab: "signin" | "signup";
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
  initialTab,
  initialEmail,
}: LoginModalProps) {
  const [tab, setTab] = useState<"signin" | "signup">(initialTab);
  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    name?: string;
  }>({});
  const [error, setError] = useState<string | null>(null);
  const [showMemberHint, setShowMemberHint] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState<{
    email: string;
    emailType: MagicLinkEmailType;
  } | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState(0);

  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setTab(initialTab);
    setEmail(initialEmail);
    setName("");
    setFieldErrors({});
    setError(null);
    setShowMemberHint(false);
    setSuccess(null);
    setIsSubmitting(false);
    setCooldownUntil(0);
  }, [open, launchKey, initialTab, initialEmail]);

  useEffect(() => {
    if (open && !success) {
      const id = window.requestAnimationFrame(() => {
        emailInputRef.current?.focus();
      });
      return () => window.cancelAnimationFrame(id);
    }
  }, [open, success, launchKey]);

  const bumpCooldown = useCallback(() => {
    setCooldownUntil(Date.now() + RESEND_COOLDOWN_MS);
  }, []);

  const validateFields = (mode: MagicLinkEmailType): boolean => {
    const next: typeof fieldErrors = {};
    const emailResult = emailSchema.safeParse(email);
    if (!emailResult.success) {
      next.email = emailResult.error.flatten().formErrors[0] ?? "E-mail inválido";
    }
    if (mode === "signup") {
      const nameResult = nameSchema.safeParse(name || undefined);
      if (!nameResult.success) {
        next.name = nameResult.error.flatten().formErrors[0];
      }
    }
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = async (emailType: MagicLinkEmailType) => {
    if (!validateFields(emailType)) {
      return;
    }
    setError(null);
    setShowMemberHint(false);
    setIsSubmitting(true);
    try {
      await sendMagicLink({
        email: emailSchema.parse(email),
        emailType,
        name: emailType === "signup" ? name.trim() || undefined : undefined,
      });
      setSuccess({ email: email.trim(), emailType });
      bumpCooldown();
    } catch (e) {
      if (emailType === "signin" && isMemberNotFoundError(e)) {
        setError(
          "Não encontramos uma conta com esse e-mail. Quer criar uma?"
        );
        setShowMemberHint(true);
      } else {
        setError(formatErrorMessage(e));
      }
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
        name:
          success.emailType === "signup"
            ? name.trim() || undefined
            : undefined,
      });
      bumpCooldown();
    } catch (e) {
      setError(formatErrorMessage(e));
    } finally {
      setIsSubmitting(false);
    }
  };

  const switchToSignup = () => {
    setTab("signup");
    setShowMemberHint(false);
    setError(null);
  };

  const resetToForm = () => {
    setSuccess(null);
    setError(null);
    setShowMemberHint(false);
    setFieldErrors({});
  };

  const cooldownRemaining = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));

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
            <div>
              <DialogTitle className="text-lg font-bold text-[#393939]">
                {success ? "Verifique seu e-mail" : "Acesso à conta"}
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {success
                  ? `Enviamos um link para ${success.email}. Verifique sua caixa de entrada (e o spam).`
                  : "Enviaremos um link mágico para entrar ou criar sua conta."}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {success ? (
          <div className="space-y-4 pt-1">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
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
                disabled={
                  isSubmitting || cooldownRemaining > 0
                }
              >
                {cooldownRemaining > 0
                  ? `Reenviar link (${cooldownRemaining}s)`
                  : "Reenviar link"}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {error ? (
              <Alert variant="destructive">
                <AlertDescription className="space-y-2">
                  <p>{error}</p>
                  {showMemberHint ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-1 rounded-full border-destructive/40"
                      onClick={switchToSignup}
                    >
                      Criar conta com este e-mail
                    </Button>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}

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
                aria-invalid={Boolean(fieldErrors.email)}
              />
              {fieldErrors.email ? (
                <p className="text-sm text-destructive">{fieldErrors.email}</p>
              ) : null}
            </div>

            <Tabs
              value={tab}
              onValueChange={(v) => {
                setTab(v as "signin" | "signup");
                setFieldErrors({});
                setError(null);
                setShowMemberHint(false);
              }}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-2 rounded-full bg-black/5 p-1">
                <TabsTrigger value="signin" className="rounded-full">
                  Entrar
                </TabsTrigger>
                <TabsTrigger value="signup" className="rounded-full">
                  Criar conta
                </TabsTrigger>
              </TabsList>

              <TabsContent value="signin" className="mt-4 space-y-4">
                <Button
                  type="button"
                  className="w-full rounded-full bg-[#ff0004] text-white hover:bg-[#ff0004]/90"
                  disabled={isSubmitting}
                  onClick={() => void submit("signin")}
                >
                  {isSubmitting && tab === "signin"
                    ? "Enviando…"
                    : "Enviar link de acesso"}
                </Button>
              </TabsContent>

              <TabsContent value="signup" className="mt-4 space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="login-name">Nome (opcional)</Label>
                  <Input
                    id="login-name"
                    autoComplete="name"
                    placeholder="Como devemos chamar você"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    aria-invalid={Boolean(fieldErrors.name)}
                  />
                  {fieldErrors.name ? (
                    <p className="text-sm text-destructive">{fieldErrors.name}</p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  className="w-full rounded-full bg-[#ff0004] text-white hover:bg-[#ff0004]/90"
                  disabled={isSubmitting}
                  onClick={() => void submit("signup")}
                >
                  {isSubmitting && tab === "signup"
                    ? "Enviando…"
                    : "Enviar link de acesso"}
                </Button>
              </TabsContent>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
