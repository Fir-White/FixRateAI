import {memo, useId} from 'react';
import {Button} from '@/shared/ui/Button';

export interface WorkflowGoalView {
  id: string;
  title: string;
  status: string;
  reason?: string | null;
  action_id?: string | null;
}

export interface WorkflowStatusView {
  outcome: string;
  goals: readonly WorkflowGoalView[];
}

interface Props {
  workflow?: WorkflowStatusView | null;
  onResume?: () => void;
  disabled?: boolean;
}

const labels: Record<string, string> = {
  planned: 'Запланировано',
  running: 'Выполняется',
  completed: 'Проверено и выполнено',
  failed: 'Не выполнено',
  blocked: 'Есть препятствие',
  partial: 'Выполнено частично',
  skipped: 'Пропущено',
  awaiting_confirmation: 'Ожидает вашего подтверждения',
  uncertain: 'Результат изменения требует проверки',
  cancelled: 'Остановлено',
};

const resumable = new Set(['planned', 'partial', 'blocked', 'failed', 'skipped']);

/**
 * The engineer/executor first sees which requested outcomes remain open, then
 * confirms the separate action card or resumes the saved task. Reply completion
 * never supplies a business-success state. No timers, effects or network calls.
 */
export const WorkflowStatus = memo(function WorkflowStatus({workflow, onResume, disabled = false}: Props) {
  const headingId = useId();
  if (!workflow) return null;

  const goals = workflow.goals.slice(0, 12);
  const completed = goals.filter(goal => goal.status === 'completed').length;
  const stopped = workflow.outcome === 'cancelled' || (goals.length > 0 && goals.every(goal => goal.status === 'cancelled'));
  const finished = workflow.outcome === 'completed' && workflow.goals.length > 0 &&
    workflow.goals.length <= 12 && completed === goals.length;
  const needsConfirmation = goals.some(goal => goal.status === 'awaiting_confirmation');
  const uncertain = goals.some(goal => goal.status === 'uncertain');
  const running = workflow.outcome === 'running' || goals.some(goal => goal.status === 'running');
  const canResume = !stopped && !finished && !running && goals.some(goal => resumable.has(goal.status));
  const summary = finished ? 'Поручение выполнено' : stopped ? 'Поручение остановлено' :
    running ? 'Поручение выполняется' : needsConfirmation ? 'Поручение ожидает подтверждения' : 'Поручение не завершено';

  return <section aria-labelledby={headingId} className="min-w-0 space-y-3 rounded-xl border border-line bg-surface p-3 text-sm sm:p-4">
    <h3 id={headingId} className="font-semibold">Состояние поручения</h3>
    <p role="status" aria-live="polite" aria-atomic="true">
      {summary}. Проверено и выполнено пунктов: {completed} из {workflow.goals.length}.
    </p>
    {goals.length > 0 ? <ol className="space-y-2 pl-5 list-decimal">
      {goals.map(goal => <li key={goal.id} className="min-w-0 pl-1">
        <span className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{goal.title}</span>
        <span className="mt-0.5 block text-xs text-muted">{labels[goal.status] ?? 'Статус требует проверки'}</span>
      </li>)}
    </ol> : <p className="text-muted">Проверенный план пока не получен. Исходное поручение сохранено.</p>}
    {workflow.goals.length > 12 && <p className="text-muted">Показаны первые 12 пунктов из {workflow.goals.length}. Полнота поручения требует проверки.</p>}
    {needsConfirmation && <p className="text-muted">Изменения ещё не выполнены. Проверьте и подтвердите каждую нужную карточку действия отдельно.</p>}
    {uncertain && <p className="text-muted">Ответ о записи потерян. Сначала проверьте состояние данных; повторное изменение не запускается автоматически.</p>}
    {stopped && !finished && <p className="text-muted">Незавершённые пункты сохранены в этом поручении.</p>}
    {onResume && canResume && <Button variant="secondary" disabled={disabled} onClick={onResume}>Продолжить поручение</Button>}
  </section>;
});
