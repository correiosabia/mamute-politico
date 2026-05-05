import { useCallback, useEffect, useState } from "react";
import axios from "axios";
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
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
  signOut as revokeGhostSessionOnServer,
} from "./fetchCurrentMember";
import { ghostSignOut } from "@/components/auth/ghost-auth/react/useGhostAuth";
import type { CurrentMember } from "./fetchCurrentMember";
import { ACCOUNT_URL } from "./config";

export type AccountModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  launchKey: number;
};

function initialsFromMember(member: CurrentMember | null): string {
  if (!member) return "?";
  const source = (member.name?.trim() || member.email || "?").trim();
  const first = source.charAt(0).toUpperCase();
  const secondChar = source.split(/\s+/)[1]?.charAt(0);
  return secondChar ? (first + secondChar.toUpperCase()).slice(0, 2) : first;
}

export function AccountModal({ open, onOpenChange, launchKey }: AccountModalProps) {
  const [member, setMember] = useState<CurrentMember | null>(null);
  const [loadState, setLoadState] = useState<
    "idle" | "loading" | "error" | "ready"
  >("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

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
      setSigningOut(false);
      setDeletingAccount(false);
      setConfirmDeleteOpen(false);
      return;
    }

    const ac = new AbortController();
    void loadMember(ac.signal);
    return () => ac.abort();
  }, [open, launchKey, loadMember]);

  const handleRetry = () => {
    const ac = new AbortController();
    void loadMember(ac.signal);
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

        {loadState === "ready" && member ? (
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
                <p className="break-all text-base text-[#393939]">{member.email}</p>
              </div>
            </div>
          </div>
        ) : null}

        {loadState === "ready" && member ? (
          <DialogFooter className="gap-2 sm:justify-end">
            {/* Temporarily hidden per request:
            <Button
              type="button"
              variant="outline"
              className="rounded-full border-destructive/50 text-destructive hover:bg-destructive/10"
              disabled={signingOut || deletingAccount}
              onClick={() => setConfirmDeleteOpen(true)}
            >
              Excluir minha conta
            </Button>
            */}
            <Button
              type="button"
              variant="destructive"
              className="rounded-full bg-[#ff0004] hover:bg-[#ff0004]/90"
              disabled={signingOut || deletingAccount}
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
