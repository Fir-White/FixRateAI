import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DEMO_MODE, request } from "@/shared/api/request";
import { ROLE_LABELS } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { useAuthValidation } from "@/features/auth/useAuthValidation";
import { AuthPasswordInput } from "@/features/auth/AuthPasswordInput";
import { AiModelSelector } from "@/features/ai/AiModelSelector";
import { getStoredAiSettings, AI_SETTINGS_CHANGE_EVENT } from "@/features/ai/aiSettings";
import { Button } from "@/shared/ui/Button";
import { Card, CardBody, CardHeader } from "@/shared/ui/Card";
import { FormField, Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { PageHeader } from "@/shared/ui/PageHeader";
import "./profile.css";

const AI_PROVIDER_LABELS: Record<string, string> = {
  clip: "⚡ Встроенный CLIP (CPU)",
  ollama: "🖥️ Локальная Ollama",
  aitunnel: "☁️ Облачный AI Tunnel",
};

export function ProfilePage() {
  const { profile, updateEmail, logout } = useSession();
  const navigate = useNavigate();
  const [emailOpen, setEmailOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiSettings, setAiSettings] = useState(getStoredAiSettings);
  const [email, setEmail] = useState(profile?.email ?? "");
  const [emailPassword, setEmailPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState<"email" | "password" | "logout" | null>(null);
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [logoutError, setLogoutError] = useState("");
  const [emailNotice, setEmailNotice] = useState("");
  const [passwordNotice, setPasswordNotice] = useState("");
  const emailValidation = useAuthValidation("register", {email});
  const passwordValidation = useAuthValidation("register", {password, password_confirmation:confirmation});
  useEffect(() => { setEmail(profile?.email ?? ""); }, [profile?.userId]);
  useEffect(() => {
    const handleAiChange = () => setAiSettings(getStoredAiSettings());
    window.addEventListener(AI_SETTINGS_CHANGE_EVENT, handleAiChange);
    window.addEventListener("storage", handleAiChange);
    return () => {
      window.removeEventListener(AI_SETTINGS_CHANGE_EVENT, handleAiChange);
      window.removeEventListener("storage", handleAiChange);
    };
  }, []);
  if (!profile) return null;
  const initials = profile.name.trim().split(/\s+/).slice(0,2).map(part => [...part][0] ?? "").join("").toLocaleUpperCase("ru-RU");
  const signOut = async () => {
    if (pending) return;
    setPending("logout"); setLogoutError("");
    try { await logout(); navigate("/login", {replace:true}); }
    catch (failure) { setLogoutError(failure instanceof Error ? failure.message : "Не удалось выйти"); setPending(null); }
  };
  return <div className="profile-page">
    <PageHeader eyebrow="Учётная запись" title="Мой профиль" description="Управление личными данными, безопасностью и настройками" />
    <div className="profile-grid">
      <Card className="profile-summary"><CardBody><div className="profile-avatar" aria-hidden="true">{initials}</div><h2>{profile.name}</h2><p className="profile-role">{ROLE_LABELS[profile.role]}</p><div className="profile-summary-site"><span>Рабочий объект</span><strong>{profile.siteName}</strong></div><div className="profile-summary-site"><span>Часовой пояс</span><strong>{profile.timezone}</strong></div></CardBody></Card>
      <div className="profile-content"><Card><CardHeader title="Учётная запись" description="Почта используется для входа в систему."/><CardBody>
        <div className="profile-setting"><div><span>Email</span><strong>{profile.email}</strong></div><Button variant="secondary" aria-expanded={emailOpen} aria-controls="profile-email-form" disabled={!!pending || DEMO_MODE} onClick={() => {setEmailOpen(!emailOpen); setEmail(profile.email); setEmailPassword(""); setEmailError(""); emailValidation.reset();}}>{emailOpen ? "Закрыть" : "Изменить"}</Button></div>
        {emailNotice && <p className="profile-notice" role="status">{emailNotice}</p>}
        {emailOpen && <form id="profile-email-form" className="profile-form" aria-label="Изменить email" noValidate onSubmit={async event => {
          event.preventDefault(); if (pending) return; setEmailError(""); setEmailNotice("");
          if (!emailValidation.validate(event.currentTarget)) return;
          if (!emailPassword) {setEmailError("Введите текущий пароль"); event.currentTarget.querySelector<HTMLInputElement>("#profile-email-password")?.focus(); return;}
          setPending("email"); try {await updateEmail(email.trim(),emailPassword);setEmail(email.trim().toLowerCase());setEmailPassword("");setEmailNotice("Email изменён");setEmailOpen(false);}
          catch (failure) {setEmailError(failure instanceof Error ? failure.message : "Не удалось изменить email");} finally {setPending(null);}
        }}>
          <FormField label="Email" htmlFor="profile-email" error={emailValidation.errors.email}><Input id="profile-email" name="email" type="email" autoComplete="email" value={email} maxLength={320} disabled={!!pending || DEMO_MODE} onBlur={event=>emailValidation.blur("email",event)} onChange={event=>{setEmail(event.target.value);emailValidation.change("email");setEmailError("");setEmailNotice("");}} /></FormField>
          <FormField label="Текущий пароль" htmlFor="profile-email-password" hint="Для подтверждения смены почты"><AuthPasswordInput id="profile-email-password" name="current_password" autoComplete="current-password" value={emailPassword} disabled={!!pending || DEMO_MODE} onChange={event=>{setEmailPassword(event.target.value);setEmailError("");}} /></FormField>
          {emailError && <p className="profile-error" role="alert">{emailError}</p>}
          <div className="profile-form-actions"><Button type="submit" disabled={!!pending || DEMO_MODE || email.trim().toLowerCase() === profile.email.toLowerCase()}>{pending === "email" ? "Сохраняем…" : "Сохранить"}</Button><Button variant="ghost" disabled={!!pending} onClick={() => {setEmailOpen(false);setEmail(profile.email);setEmailPassword("");setEmailError("");emailValidation.reset();}}>Отмена</Button></div>
        </form>}
      </CardBody></Card><Card><CardHeader title="Безопасность" description="Управляйте паролем и защитой учётной записи"/><CardBody>
        <div className="profile-setting"><div><span>Пароль</span><strong>••••••••••••</strong></div><Button variant="secondary" disabled={!!pending || DEMO_MODE} aria-expanded={passwordOpen} aria-controls="profile-password-form" onClick={() => {setPasswordOpen(!passwordOpen);setCurrentPassword("");setPassword("");setConfirmation("");setPasswordError("");passwordValidation.reset();}}>{passwordOpen ? "Закрыть" : "Изменить пароль"}</Button></div>
        {passwordNotice && <p className="profile-notice" role="status">{passwordNotice}</p>}
        {passwordOpen && <form id="profile-password-form" className="profile-form" aria-label="Изменить пароль" noValidate onSubmit={async event=>{
          event.preventDefault();if(pending)return;setPasswordError("");setPasswordNotice("");
          if(!currentPassword){setPasswordError("Введите текущий пароль");event.currentTarget.querySelector<HTMLInputElement>("#profile-current-password")?.focus();return;}
          if(!passwordValidation.validate(event.currentTarget))return;
          if(password.length > 64){setPasswordError("Пароль должен содержать не более 64 символов");return;}
          setPending("password");try{const result=await request<{updated:boolean}>("/api/v1/maintenance/users/me/password",{method:"POST",body:JSON.stringify({current_password:currentPassword,new_password:password,password_confirmation:confirmation})});if(!result.updated)throw new Error("Не удалось изменить пароль");setCurrentPassword("");setPassword("");setConfirmation("");passwordValidation.reset();setPasswordNotice("Пароль изменён");setPasswordOpen(false);}
          catch(failure){setPasswordError(failure instanceof Error?failure.message:"Не удалось изменить пароль");}finally{setPending(null);}
        }}>
          <FormField label="Старый пароль" htmlFor="profile-current-password"><AuthPasswordInput id="profile-current-password" name="current_password" visibilityLabel="старый пароль" autoComplete="current-password" value={currentPassword} disabled={!!pending || DEMO_MODE} onChange={e=>{setCurrentPassword(e.target.value);setPasswordError("");}} /></FormField>
          <FormField label="Новый пароль" htmlFor="profile-new-password" error={passwordValidation.errors.password}><AuthPasswordInput id="profile-new-password" name="password" visibilityLabel="новый пароль" autoComplete="new-password" value={password} maxLength={64} disabled={!!pending || DEMO_MODE} onBlur={e=>passwordValidation.blur("password",e)} onChange={e=>{setPassword(e.target.value);passwordValidation.change("password");setPasswordError("");setPasswordNotice("");}} /></FormField>
          <FormField label="Подтвердите новый пароль" htmlFor="profile-confirm-password" error={passwordValidation.errors.password_confirmation}><AuthPasswordInput id="profile-confirm-password" name="password_confirmation" visibilityLabel="подтверждение пароля" autoComplete="new-password" value={confirmation} maxLength={64} disabled={!!pending || DEMO_MODE} onBlur={e=>passwordValidation.blur("password_confirmation",e)} onChange={e=>{setConfirmation(e.target.value);passwordValidation.change("password_confirmation");setPasswordError("");}} /></FormField>
          {passwordError && <p className="profile-error" role="alert">{passwordError}</p>}
          <p className={`profile-requirement${password.length >= 12 ? " is-met" : ""}`}>От 12 до 64 символов</p><div className="profile-form-actions"><Button type="submit" disabled={!!pending || DEMO_MODE}>{pending === "password" ? "Сохраняем…" : "Сохранить пароль"}</Button><Button variant="ghost" disabled={!!pending} onClick={() => {setPasswordOpen(false);setCurrentPassword("");setPassword("");setConfirmation("");setPasswordError("");passwordValidation.reset();}}>Отмена</Button></div>
        </form>}
      </CardBody></Card><Card><CardHeader title="Нейросети и анализ фото (AI / LLM)" description="Выбор модели для проверки фотоотчётов и детекции дефектов"/><CardBody>
        <div className="profile-setting"><div><span>Активная модель</span><strong>{AI_PROVIDER_LABELS[aiSettings.provider] ?? aiSettings.provider}{aiSettings.model ? ` · ${aiSettings.model}` : ""}</strong></div><Button variant="secondary" aria-expanded={aiOpen} aria-controls="profile-ai-form" onClick={() => setAiOpen(!aiOpen)}>{aiOpen ? "Закрыть" : "Настроить"}</Button></div>
        {aiOpen && <div id="profile-ai-form" className="profile-form"><AiModelSelector variant="card" autoFetch={aiOpen} /></div>}
      </CardBody></Card><Card><CardBody><div className="profile-session"><div><h2>Текущий сеанс</h2><p>Завершить работу на этом устройстве.</p></div><Button variant="danger" disabled={!!pending} onClick={() => void signOut()}><Icon name="logout" size={16}/>{pending === "logout" ? "Выходим…" : "Выйти из аккаунта"}</Button></div>{logoutError && <p className="profile-error" role="alert">{logoutError}</p>}</CardBody></Card></div>
    </div>
  </div>;
}
