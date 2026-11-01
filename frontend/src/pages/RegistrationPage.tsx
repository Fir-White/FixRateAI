import { useState } from "react";
import { Link } from "react-router-dom";
import { managementApi } from "@/shared/api/management";
import { Input } from "@/shared/ui/Form";
import { Button,buttonClassName } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";

export function RegistrationPage() {
  const [name,setName]=useState("");const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [code,setCode]=useState("");
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [done,setDone]=useState("");
  return <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center space-y-5 p-6"><h1 className="text-3xl font-semibold">Регистрация сотрудника</h1>
    <p className="text-sm text-muted">Получите код компании у администратора. После регистрации администратор выдаст роль и доступ к объекту.</p>
    {done ? <Callout tone="success">{done}</Callout> : <Card className="p-5"><form className="space-y-4" onSubmit={async event=>{
      event.preventDefault();if(busy)return;setBusy(true);setError("");try{const result=await managementApi.register({full_name:name,email,password,company_code:code});setPassword("");setDone(result.message);}catch(failure){setError(failure instanceof Error?failure.message:"Регистрация не удалась");}finally{setBusy(false);}
    }}><fieldset disabled={busy} className="space-y-4"><label className="block text-sm">Имя и фамилия<Input aria-label="Имя и фамилия" required autoComplete="name" value={name} onChange={e=>setName(e.target.value)}/></label>
      <label className="block text-sm">Email<Input aria-label="Email" type="email" required autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label className="block text-sm">Пароль<Input aria-label="Пароль" type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/><span className="text-xs text-muted">От 12 символов</span></label>
      <label className="block text-sm">Код компании<Input aria-label="Код компании" required minLength={16} value={code} onChange={e=>setCode(e.target.value)}/></label>
      {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}<Button type="submit" disabled={busy}>{busy?"Регистрация…":"Зарегистрироваться"}</Button>
    </fieldset></form></Card>}
    <Link to="/login" className={buttonClassName("secondary")}>Перейти ко входу</Link>
  </main>;
}
