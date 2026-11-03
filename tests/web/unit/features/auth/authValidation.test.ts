import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api/request";
import { describeAuthFailure, validateAuthField, type AuthField, type AuthMode } from "@/features/auth/authValidation";

afterEach(()=>vi.restoreAllMocks());
it.each<[AuthField,string,AuthMode,string|undefined]>([
  ["full_name","   ","register","Введите имя и фамилию"],
  ["full_name","И".repeat(257),"register","Имя и фамилия — не более 256 символов"],
  ["email","bad","login","Введите корректный email"],
  ["email","a@b","login",undefined],
  ["email","a@b","register","Введите корректный email"],
  ["email","a".repeat(315)+"@b.com","register","Email — не более 320 символов"],
  ["password"," ","login",undefined],
  ["password"," ".repeat(12),"register",undefined],
  ["password","short","register","Пароль должен содержать не менее 12 символов"],
  ["password","x".repeat(129),"register","Пароль — не более 128 символов"],
  ["password","x".repeat(1025),"login","Пароль — не более 1024 символов"],
  ["company_code","  ","register","Введите код компании"],
  ["company_code","code","register","Код компании должен содержать не менее 16 символов"],
  ["company_code","x".repeat(129),"register","Код компании — не более 128 символов"],
  ["company_code","  words-not-hex-code  ","register",undefined],
  ["site_id","site-id","login","Введите ID объекта в формате UUID"],
  ["site_id"," 00000000-0000-0000-0000-000000000001 ","login",undefined],
])("validates %s against the actual %s contract",(field,value,mode,error)=>{
  expect(validateAuthField(field,{[field]:value},mode)).toBe(error);
});

it.each([
  [new ApiError(401,"Неверный email или пароль"),"Неверный email или пароль"],
  [new ApiError(403,"Нет доступа к объекту"),"Доступ не предоставлен"],
  [new ApiError(403,"Недопустимый origin"),"Обновите страницу"],
  [new ApiError(429,"Too Many Requests"),"Слишком много попыток"],
  [new ApiError(500,"Internal Server Error"),"Сервис временно недоступен"],
  [new ApiError(503,"База данных недоступна"),"Сервис временно недоступен"],
  [new TypeError("Failed to fetch"),"Не удалось связаться с сервером"],
  [new Error("Unexpected failure"),"Не удалось выполнить запрос"],
  [new ApiError(400,"Ошибка API (400)"),"Не удалось выполнить запрос"],
  [new ApiError(404,"Ошибка API (404)"),"Не удалось выполнить запрос"],
  [{detail:"raw object"},"Не удалось выполнить запрос"],
])("formats a safe Russian auth error for %s",(failure,message)=>{
  expect(describeAuthFailure(failure,"login").message).toContain(message);
});

it("preserves the site-required flow, maps a rejected company code and never invents an email conflict",()=>{
  expect(describeAuthFailure(new ApiError(409,"Укажите site_id: у пользователя несколько объектов"),"login")).toMatchObject({requiresSite:true});
  expect(describeAuthFailure(new ApiError(422,"Неверный код компании"),"register").fields).toEqual({company_code:"Неверный код компании"});
  expect(describeAuthFailure(new ApiError(409,"Email уже зарегистрирован"),"register").fields?.email).toContain("уже зарегистрирован");
  expect(describeAuthFailure(new ApiError(409,"Конфликт с сохранёнными данными"),"register").fields).toBeUndefined();
});

it("maps both validation formats and keeps an explicit fallback for unknown fields",()=>{
  const actual=describeAuthFailure(new ApiError(422,"Проверьте заполнение полей формы",[{field:"body.email",issue:"Value error"}]),"register");
  expect(actual).toEqual({fields:{email:"Проверьте email"}});
  const fastapi=describeAuthFailure(new ApiError(422,"Ошибка API (422)",[{loc:["body","password"],msg:"String too short"},{loc:["body","unrecognized"],msg:"unknown"}]),"login");
  expect(fastapi.fields).toEqual({password:"Проверьте пароль"});
  expect(fastapi.message).toContain("Проверьте заполнение формы");
  expect(JSON.stringify(fastapi)).not.toMatch(/String too short|unrecognized/);
});

it("explains offline mode without exposing browser fetch text",()=>{
  vi.spyOn(navigator,"onLine","get").mockReturnValue(false);
  expect(describeAuthFailure(new TypeError("Failed to fetch"),"register").message).toContain("Нет подключения к интернету");
});
