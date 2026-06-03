"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ContractForm } from "@/components/contract-form";
import { api, type ContractCreate } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function NewContractPage() {
  const t = useTranslations("contracts");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(payload: ContractCreate) {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const contract = await api.createContract(token, payload);
      router.push(`/${locale}/contracts/${contract.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">{t("create")}</h1>
      <ContractForm submitLabel={t("create")} busy={busy} error={error} onSubmit={create} />
    </div>
  );
}
