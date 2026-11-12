import { ApiError } from "@/shared/api/request";

export type AuthMode = "login" | "register";
export type AuthField = "full_name" | "email" | "password" | "password_confirmation" | "company_code" | "site_id";
export type AuthValues = Partial<Record<AuthField, string>>;
export type AuthErrors = Partial<Record<AuthField, string>>;
const ORDER: AuthField[] = ["full_name", "email", "password", "password_confirmation", "company_code", "site_id"];

export function validateAuthField(field: AuthField, values: AuthValues, mode: AuthMode): string | undefined {
  const raw = values[field] ?? "", value = raw.trim();
  switch (field) {
    case "full_name": return !value ? "Введите имя и фамилию" : value.length > 256 ? "Имя и фамилия — не более 256 символов" : undefined;
    case "email":
      if (!value) return "Введите email";
      if (value.length > 320) return "Email — не более 320 символов";
      return value.length < 3 || !(mode === "register" ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/ : /^[^\s@]+@[^\s@]+$/).test(value) ? "Введите корректный email" : undefined;
    case "password":
      if (!raw) return "Введите пароль";
      if (mode === "register" && raw.length < 12) return "Пароль должен содержать не менее 12 символов";
      return raw.length > (mode === "register" ? 128 : 1024) ? `Пароль — не более ${mode === "register" ? 128 : 1024} символов` : undefined;
    case "password_confirmation": return !raw ? "Повторите пароль" : raw !== values.password ? "Пароли не совпадают" : undefined;
    case "company_code": return !value ? "Введите код компании" : value.length < 16 ? "Код компании должен содержать не менее 16 символов" : value.length > 128 ? "Код компании — не более 128 символов" : undefined;
    case "site_id": return !value ? "Введите ID объекта" : !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(value) ? "Введите ID объекта в формате UUID" : undefined;
  }
}

export function validateAuth(values: AuthValues, mode: AuthMode): AuthErrors {
  return Object.fromEntries(ORDER.filter(field => field in values).flatMap(field => {
    const error = validateAuthField(field, values, mode);
    return error ? [[field, error]] : [];
  }));
}

export function focusAuthError(form: HTMLFormElement, errors: AuthErrors) {
  const field = ORDER.find(key => errors[key]);
  if (field) (form.elements.namedItem(field) as HTMLInputElement | null)?.focus();
}

const FIELD_REVIEW: Record<AuthField, string> = {
  full_name: "Проверьте имя и фамилию", email: "Проверьте email", password: "Проверьте пароль",
  password_confirmation: "Проверьте подтверждение пароля", company_code: "Проверьте код компании", site_id: "Проверьте ID объекта",
};

export function describeAuthFailure(failure: unknown, mode: AuthMode): { message?: string; fields?: AuthErrors; requiresSite?: boolean } {
  const status = failure instanceof ApiError ? failure.status : undefined;
  const detail = failure instanceof Error ? failure.message : "";
  const russian = /[а-яё]/i.test(detail) && detail.length <= 250 && !/[<>{}\[\]\r\n]/.test(detail) && !/^Ошибка API \(\d+\)$/.test(detail) ? detail : undefined;
  if (typeof navigator !== "undefined" && !navigator.onLine) return { message: "Нет подключения к интернету. Проверьте соединение и повторите попытку." };
  if (failure instanceof TypeError || /failed to fetch|network ?error|load failed/i.test(detail)) return { message: "Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз." };
  if (status === 429) return { message: "Слишком много попыток. Подождите немного и попробуйте ещё раз." };
  if (status !== undefined && status >= 500) return { message: "Сервис временно недоступен. Попробуйте позже." };
  if (mode === "login" && (status === 409 || status === undefined) && /site_id|несколько объектов/i.test(detail)) return { message: "Укажите ID объекта. Его можно получить у администратора.", requiresSite: true };
  if (mode === "register" && /код компании/i.test(detail) && /неверн|недейств|не найден|ист[её]к/i.test(detail)) return { fields: { company_code: russian ?? "Неверный код компании" } };
  if (mode === "register" && /email|почт/i.test(detail) && /уже|существ|занят|already/i.test(detail)) return { fields: { email: "Этот email уже зарегистрирован. Перейдите ко входу." } };
  if (status === 401) return { message: russian ?? "Неверный email или пароль" };
  if (status === 403) return { message: /origin|csrf/i.test(detail) ? "Не удалось подтвердить запрос. Обновите страницу и попробуйте ещё раз." : "Доступ не предоставлен. Обратитесь к администратору." };
  if (status === 422 && failure instanceof ApiError) {
    const fields: AuthErrors = {};
    let unmapped = false;
    if (Array.isArray(failure.details) && failure.details.length) {
      for (const item of failure.details) {
        const field = item && typeof item === "object" ? (typeof item.field === "string" ? item.field.split(".").at(-1) : Array.isArray(item.loc) ? item.loc.at(-1) : undefined) : undefined;
        const allowed = mode === "register" ? ["full_name", "email", "password", "company_code"] : ["email", "password", "site_id"];
        if (allowed.includes(field)) fields[field as AuthField] = FIELD_REVIEW[field as AuthField];
        else unmapped = true;
      }
    } else unmapped = true;
    return { fields, ...(unmapped ? { message: "Не удалось проверить данные. Проверьте заполнение формы и повторите попытку." } : {}) };
  }
  if (status === 409) return { message: "Не удалось сохранить данные из-за конфликта. Проверьте их или обратитесь к администратору." };
  return { message: russian ?? "Не удалось выполнить запрос. Попробуйте ещё раз или обратитесь к администратору." };
}
