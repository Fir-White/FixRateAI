import { useFeedbackMotion } from "@/shared/motion/useFeedbackMotion";

export function AuthFormError({ id, message }: { id: string; message: string }) {
  const feedback = useFeedbackMotion(message || undefined);
  return <div ref={feedback} className="form-feedback">{message && <p id={id} role="alert" className="auth-error">{message}</p>}</div>;
}
