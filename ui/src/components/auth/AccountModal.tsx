import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { z } from "zod";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import logoMamute from "@/assets/logo-mamute.png";
import {
  deleteMyAccount,
  fetchCurrentMember,
  isDeleteAccountNotSupportedError,
  requestMemberEmailChange,
  signOut as revokeGhostSessionOnServer,
  updateMemberNewsletterSubscription,
  updateMemberProfile,
} from "./fetchCurrentMember";
import { ghostSignOut } from "@/components/auth/ghost-auth/react/useGhostAuth";
import type { CurrentMember } from "./fetchCurrentMember";
import { ACCOUNT_URL } from "./config";
import {
  getMemberPlanDetails,
  isMemberSubscribedToNewsletter,
} from "./memberAccountDetails";

export type AccountModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  launchKey: number;
};

const emailSchema = z.string().trim().email({ message: "E-mail inválido" });

const nameSchema = z
  .string()
  .trim()
  .max(120, { message: "Nome muito longo" })
  .optional();

function initialsFromMember(member: CurrentMember | null): string {
  if (!member) return "?";
  const source = (member.name?.trim() || member.email || "?").trim();
  const first = source.charAt(0).toUpperCase();
  const secondChar = source.split(/\s+/)[1]?.charAt(0);
  return secondChar ? (first + secondChar.toUpperCase()).slice(0, 2) : first;
}

function formatErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && !error.response) {
    return "Não foi possível conectar. Verifique sua rede.";
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Algo deu errado. Tente novamente em instantes.";
}

function normalizeName(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function AccountModal({ open, onOpenChange, launchKey }: AccountModalProps) {
  const [member, setMember] = useState<CurrentMember | null>(null);
  const [loadState, setLoadState] = useState<
    "idle" | "loading" | "error" | "ready"
  >("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draftName, setDraftName] = useState("");
  const [draftEmail, setDraftEmail] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string;
    email?: string;
  }>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [emailChangeNotice, setEmailChangeNotice] = useState<string | null>(
    null
  );
  const [signingOut, setSigningOut] = useState(false);
  const [updatingNewsletter, setUpdatingNewsletter] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  const resetEditState = useCallback(() => {
    setMode("view");
    setDraftName("");
    setDraftEmail("");
    setFieldErrors({});
    setSaveError(null);
    setIsSaving(false);
    setEmailChangeNotice(null);
  }, []);

  const loadMember = useCallback(
    async (signal: AbortSignal) => {
      setLoadState("loading");
      setLoadError(null);
      try {
        const data = await fetchCurrentMember(signal);
        if (signal.aborted) return;
        if (data === null) {
          ghostSignOut();
          onOpenChange(false);
          return;
        }
        setMember(data);
        setLoadState("ready");
      } catch (e) {
        if (
          signal.aborted ||
          (axios.isAxiosError(e) && e.code === "ERR_CANCELED")
        ) {
          return;
        }
        if (axios.isAxiosError(e) && e.response?.status === 401) {
          ghostSignOut();
          onOpenChange(false);
          return;
        }
        setLoadState("error");
        setLoadError(
          axios.isAxiosError(e) && !e.response
            ? "Não foi possível conectar. Verifique sua rede."
            : "Não foi possível carregar sua conta."
        );
      }
    },
    [onOpenChange]
  );

  useEffect(() => {
    if (!open) {
      setMember(null);
      setLoadState("idle");
      setLoadError(null);
      resetEditState();
      setSigningOut(false);
      setUpdatingNewsletter(false);
      setDeletingAccount(false);
      setConfirmDeleteOpen(false);
      return;
    }

    const ac = new AbortController();
    void loadMember(ac.signal);
    return () => ac.abort();
  }, [open, launchKey, loadMember, resetEditState]);

  const handleRetry = () => {
    const ac = new AbortController();
    void loadMember(ac.signal);
  };

  const handleStartEdit = () => {
    if (!member) return;
    setDraftName(member.name ?? "");
    setDraftEmail(member.email);
    setFieldErrors({});
    setSaveError(null);
    setMode("edit");
  };

  const handleCancelEdit = () => {
    setMode("view");
    setDraftName("");
    setDraftEmail("");
    setFieldErrors({});
    setSaveError(null);
    setIsSaving(false);
  };

  const validateFields = (): boolean => {
    const next: typeof fieldErrors = {};
    const nameResult = nameSchema.safeParse(draftName || undefined);
    if (!nameResult.success) {
      next.name = nameResult.error.flatten().formErrors[0];
    }
    const emailResult = emailSchema.safeParse(draftEmail);
    if (!emailResult.success) {
      next.email =
        emailResult.error.flatten().formErrors[0] ?? "E-mail inválido";
    }
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSave = async () => {
    if (!member) return;
    if (!validateFields()) return;

    const nextName = normalizeName(draftName);
    const nextEmail = emailSchema.parse(draftEmail);
    const nameChanged = nextName !== member.name;
    const emailChanged =
      nextEmail.toLowerCase() !== member.email.toLowerCase();

    if (!nameChanged && !emailChanged) {
      setMode("view");
      return;
    }

    setSaveError(null);
    setIsSaving(true);

    let updatedMember = member;
    let nameSaved = false;

    try {
      if (nameChanged) {
        updatedMember = await updateMemberProfile({ name: nextName });
        setMember(updatedMember);
        nameSaved = true;
      }

      if (emailChanged) {
        try {
          await requestMemberEmailChange({ email: nextEmail });
          setEmailChangeNotice(
            `Enviamos um link de confirmação para ${nextEmail}. Seu e-mail só muda depois que você clicar no link.`
          );
        } catch (emailError) {
          if (nameSaved) {
            setSaveError(
              `Nome atualizado, mas não foi possível solicitar a alteração de e-mail: ${formatErrorMessage(emailError)}`
            );
            setMode("view");
            toast.success("Nome atualizado");
            return;
          }
          throw emailError;
        }
      }

      if (nameChanged && !emailChanged) {
        toast.success("Perfil atualizado");
      } else if (emailChanged && !nameChanged) {
        toast.success("Link de confirmação enviado");
      } else {
        toast.success("Nome atualizado e link de confirmação enviado");
      }

      setMode("view");
    } catch (e) {
      setSaveError(formatErrorMessage(e));
    } finally {
      setIsSaving(false);
    }
  };

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await revokeGhostSessionOnServer();
      ghostSignOut();
      toast.success("Sessão encerrada");
      onOpenChange(false);
    } catch {
      toast.error("Não foi possível encerrar a sessão. Tente novamente.");
    } finally {
      setSigningOut(false);
    }
  };

  const handleNewsletterChange = async (subscribed: boolean) => {
    setUpdatingNewsletter(true);
    try {
      const updatedMember = await updateMemberNewsletterSubscription({
        subscribed,
      });
      setMember((current) =>
        current ? { ...current, ...updatedMember } : updatedMember
      );
      toast.success(
        subscribed
          ? "Newsletter por e-mail ativada"
          : "Newsletter por e-mail desativada"
      );
    } catch (error) {
      toast.error(formatErrorMessage(error));
    } finally {
      setUpdatingNewsletter(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeletingAccount(true);
    try {
      await deleteMyAccount();
      ghostSignOut();
      setConfirmDeleteOpen(false);
      onOpenChange(false);
      toast.success("Conta excluída com sucesso");
    } catch (error) {
      if (isDeleteAccountNotSupportedError(error)) {
        toast.info(
          "Seu Ghost não suporta exclusão de conta por API. Abrindo a página de conta…"
        );
        window.location.href = ACCOUNT_URL;
        return;
      }
      toast.error("Não foi possível excluir sua conta. Tente novamente.");
    } finally {
      setDeletingAccount(false);
    }
  };

  const actionsDisabled =
    signingOut || deletingAccount || isSaving || updatingNewsletter;

  const planDetails = member ? getMemberPlanDetails(member) : null;
  const newsletterSubscribed = member
    ? isMemberSubscribedToNewsletter(member)
    : false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-black/10 sm:rounded-2xl">
        <DialogHeader className="space-y-3 text-left">
          <div className="flex flex-col items-start gap-3 pr-8">
            <img
              src={logoMamute}
              alt=""
              className="mt-0.5 h-9 w-auto shrink-0"
            />
            <div>
              <DialogTitle className="text-lg font-bold text-[#393939]">
                Sua conta
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                Dados da sua assinatura no Mamute Político.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {loadState === "loading" || loadState === "idle" ? (
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-3">
              <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-[200px] max-w-full" />
                <Skeleton className="h-4 w-[260px] max-w-full" />
              </div>
            </div>
            <Skeleton className="h-4 w-[140px] max-w-full" />
          </div>
        ) : null}

        {loadState === "error" ? (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>{loadError}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0 rounded-full border-destructive/40"
                onClick={handleRetry}
              >
                Tentar de novo
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {loadState === "ready" && member && mode === "view" ? (
          <>
            {emailChangeNotice ? (
              <p className="text-sm text-muted-foreground">{emailChangeNotice}</p>
            ) : null}
            {saveError ? (
              <p className="text-sm text-destructive">{saveError}</p>
            ) : null}
            <div className="flex flex-col gap-4 py-1 sm:flex-row sm:items-start sm:gap-5">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#ff0004] text-sm font-bold text-white"
                aria-hidden
              >
                {initialsFromMember(member)}
              </div>
              <div className="min-w-0 flex-1 space-y-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Nome
                  </p>
                  <p className="text-base text-[#393939]">
                    {member.name?.trim() ? (
                      member.name
                    ) : (
                      <span className="text-muted-foreground">Sem nome</span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    E-mail
                  </p>
                  <p className="break-all text-base text-[#393939]">
                    {member.email}
                  </p>
                </div>
              </div>
            </div>
            <div className="divide-y overflow-hidden rounded-xl border border-black/10">
              <div className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="font-semibold text-[#393939]">
                    {planDetails?.name}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {planDetails?.description}
                  </p>
                </div>
                <Button
                  asChild
                  variant="ghost"
                  className="shrink-0 rounded-full text-[#ff0004] hover:bg-[#ff0004]/10 hover:text-[#ff0004]"
                >
                  <a href={ACCOUNT_URL}>Alterar</a>
                </Button>
              </div>
              <div className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <Label
                    htmlFor="account-newsletter"
                    className="font-semibold text-[#393939]"
                  >
                    Newsletter por e-mail
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    {newsletterSubscribed ? "Inscrito" : "Não inscrito"}
                  </p>
                  <a
                    href={ACCOUNT_URL}
                    className="text-sm font-medium text-[#ff0004] hover:underline"
                  >
                    Não está recebendo e-mails?
                  </a>
                </div>
                <Switch
                  id="account-newsletter"
                  aria-label="Newsletter por e-mail"
                  checked={newsletterSubscribed}
                  disabled={actionsDisabled}
                  onCheckedChange={(checked) =>
                    void handleNewsletterChange(checked)
                  }
                  className="data-[state=checked]:bg-[#ff0004]"
                />
              </div>
            </div>
          </>
        ) : null}

        {loadState === "ready" && member && mode === "edit" ? (
          <form
            className="space-y-4 py-1"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSave();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="account-name">Nome</Label>
              <Input
                id="account-name"
                autoComplete="name"
                placeholder="Como devemos chamar você"
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                aria-invalid={Boolean(fieldErrors.name)}
              />
              {fieldErrors.name ? (
                <p className="text-sm text-destructive">{fieldErrors.name}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="account-email">E-mail</Label>
              <Input
                id="account-email"
                type="email"
                autoComplete="email"
                placeholder="voce@exemplo.com"
                value={draftEmail}
                onChange={(e) => setDraftEmail(e.target.value)}
                aria-invalid={Boolean(fieldErrors.email || saveError)}
              />
              {fieldErrors.email ? (
                <p className="text-sm text-destructive">{fieldErrors.email}</p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Alterações de e-mail exigem confirmação por link enviado ao novo
                endereço.
              </p>
            </div>
            {saveError ? (
              <p className="text-sm text-destructive">{saveError}</p>
            ) : null}
            <DialogFooter className="gap-2 px-0 sm:justify-end">
              <Button
                type="button"
                variant="outline"
                className="rounded-full"
                disabled={actionsDisabled}
                onClick={handleCancelEdit}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                className="rounded-full bg-[#ff0004] text-white hover:bg-[#ff0004]/90"
                disabled={actionsDisabled}
              >
                {isSaving ? "Salvando…" : "Salvar"}
              </Button>
            </DialogFooter>
          </form>
        ) : null}

        {loadState === "ready" && member && mode === "view" ? (
          <DialogFooter className="gap-2 sm:justify-end">
            {/* Temporarily hidden per request:
            <Button
              type="button"
              variant="outline"
              className="rounded-full border-destructive/50 text-destructive hover:bg-destructive/10"
              disabled={actionsDisabled}
              onClick={() => setConfirmDeleteOpen(true)}
            >
              Excluir minha conta
            </Button>
            */}
            <Button
              type="button"
              variant="outline"
              className="rounded-full"
              disabled={actionsDisabled}
              onClick={handleStartEdit}
            >
              Editar
            </Button>
            <Button
              type="button"
              variant="destructive"
              className="rounded-full bg-[#ff0004] hover:bg-[#ff0004]/90"
              disabled={actionsDisabled}
              onClick={() => void handleSignOut()}
            >
              {signingOut ? "Saindo…" : "Sair"}
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir minha conta?</AlertDialogTitle>
            <AlertDialogDescription>
              Essa ação é permanente e removerá seu acesso ao Mamute Político.
              Você poderá criar uma nova conta depois, mas os dados atuais
              poderão ser perdidos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingAccount}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={deletingAccount}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault();
                void handleDeleteAccount();
              }}
            >
              {deletingAccount ? "Excluindo…" : "Sim, excluir conta"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
