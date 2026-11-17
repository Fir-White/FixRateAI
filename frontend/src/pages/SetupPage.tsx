import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/shared/ui/Button";
import { FormField, Input } from "@/shared/ui/Form";

export function SetupPage() {
  const [required, setRequired] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [complete, setComplete] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/setup", { signal: controller.signal, cache: "no-store" })
      .then(async response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(data => setRequired(data.required === true))
      .catch(() => { if (!controller.signal.aborted) setError("Не удалось проверить состояние установки. Обновите страницу."); });
    return () => controller.abort();
  }, []);
  return <>
    <h1 id="setup-title">Первоначальная настройка</h1>
    {complete || required === false ? <><p>{complete ? "Администратор создан. Войдите с указанными реквизитами." : "Первоначальная настройка недоступна или уже завершена."}</p><Link to="/login">Перейти ко входу</Link></> : required === null ? <p role="status">{error || "Проверка установки…"}</p> : <>
      <p>Создайте администратора и первое здание. Одноразовый код находится в файле bootstrap-token.txt в каталоге установки.</p>
      <form className="auth-form" aria-label="Создание первого администратора" onSubmit={async event => {
        event.preventDefault(); if (pending) return;
        const form = event.currentTarget;
        const values = new FormData(form);
        setPending(true); setError("");
        try {
          const response = await fetch("/api/setup", { method: "POST", headers: { "Content-Type": "application/json", "X-FixRate-Setup-Token": String(values.get("token")) }, body: JSON.stringify(Object.fromEntries([...values.entries()].filter(([key]) => key !== "token"))) });
          if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === "string" ? body.detail : "Проверьте заполнение полей."); }
          form.reset(); setComplete(true);
        } catch (failure) { setError(failure instanceof Error ? failure.message : "Не удалось завершить настройку."); }
        finally { setPending(false); }
      }}>
        <fieldset disabled={pending}>
          <FormField label="Одноразовый установочный код" htmlFor="setup-token"><Input id="setup-token" name="token" type="password" autoComplete="off" required maxLength={256} /></FormField>
          <FormField label="Организация" htmlFor="setup-org"><Input id="setup-org" name="organization_name" required maxLength={200} /></FormField>
          <FormField label="Первое здание" htmlFor="setup-site"><Input id="setup-site" name="site_name" required maxLength={200} /></FormField>
          <FormField label="Имя администратора" htmlFor="setup-name"><Input id="setup-name" name="full_name" autoComplete="name" required maxLength={200} /></FormField>
          <FormField label="Email" htmlFor="setup-email"><Input id="setup-email" name="email" type="email" autoComplete="username" required maxLength={320} /></FormField>
          <FormField label="Пароль (от 12 символов)" htmlFor="setup-password"><Input id="setup-password" name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} /></FormField>
          {error && <p role="alert">{error}</p>}
          <Button type="submit" disabled={pending}>{pending ? "Создание…" : "Создать администратора"}</Button>
        </fieldset>
      </form>
    </>}
  </>;
}
