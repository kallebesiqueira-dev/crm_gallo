"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ContractForm } from "@/components/contract-form";
import { api, type Contract, type ContractCreate } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function EditContractPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("contracts");
  const locale = useLocale();
  const router = useRouter();
  const [contract, setContract] = useState<Contract | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getContract(token, id).then(setContract).catch((e) => setError(String(e)));
  }, [id]);

  async function save(payload: ContractCreate) {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateContract(token, id, payload);
      router.push(`/${locale}/contracts/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  if (error && !contract) return <p className="text-sm text-destructive">{error}</p>;
  if (!contract) return <p className="text-sm text-muted-foreground">…</p>;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">
        {t("edit")} · {contract.number} {t("version", { n: contract.version })}
      </h1>
      <ContractForm
        initial={contract}
        submitLabel={t("save")}
        busy={busy}
        error={error}
        onSubmit={save}
      />
    </div>
  );
}
