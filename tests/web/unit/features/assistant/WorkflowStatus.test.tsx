import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, it, vi} from 'vitest';
import {WorkflowStatus, type WorkflowStatusView} from '@/features/assistant/WorkflowStatus';

const workflow = (status: string, outcome = status): WorkflowStatusView => ({
  outcome,
  goals: [{id: 'equipment-name', title: 'Изменить название насоса НС-01', status}],
});

it('shows persisted incomplete goals separately from reply completion', () => {
  render(<WorkflowStatus workflow={{outcome: 'partial', goals: [
    {id: 'registry', title: 'Проверить всё оборудование', status: 'completed'},
    {id: 'history', title: 'Проверить историю обслуживания', status: 'blocked', reason: 'outcome_evidence_missing'},
  ]}} onResume={() => {}}/>);
  const region = screen.getByRole('region', {name: 'Состояние поручения'});
  expect(within(region).getByRole('status')).toHaveTextContent('Поручение не завершено');
  expect(within(region).getByRole('status')).toHaveTextContent('1 из 2');
  expect(within(region).getAllByRole('listitem')).toHaveLength(2);
  expect(within(region).getByText('Есть препятствие')).toBeVisible();
  expect(screen.queryByText('outcome_evidence_missing')).not.toBeInTheDocument();
});

it('never announces completed or offers a repeat write while approval is pending', () => {
  render(<WorkflowStatus workflow={workflow('awaiting_confirmation', 'completed')} onResume={() => {}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение ожидает подтверждения');
  expect(screen.getByRole('status')).not.toHaveTextContent('Поручение выполнено');
  expect(screen.getByText('Ожидает вашего подтверждения')).toBeVisible();
  expect(screen.getByText(/подтвердите каждую нужную карточку/)).toBeVisible();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('announces success only when the saved outcome and every goal agree', () => {
  const {rerender} = render(<WorkflowStatus workflow={workflow('completed', 'partial')} onResume={() => {}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение не завершено');
  rerender(<WorkflowStatus workflow={workflow('completed')} onResume={() => {}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение выполнено');
  expect(screen.getByRole('status')).toHaveTextContent('1 из 1');
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('resumes the saved task only from an explicit keyboard action', async () => {
  const user = userEvent.setup();
  const onResume = vi.fn();
  render(<WorkflowStatus workflow={workflow('partial')} onResume={onResume}/>);
  expect(onResume).not.toHaveBeenCalled();
  await user.tab();
  expect(screen.getByRole('button', {name: 'Продолжить поручение'})).toHaveFocus();
  await user.keyboard('{Enter}');
  expect(onResume).toHaveBeenCalledTimes(1);
});

it('prevents duplicate continuation while the parent is busy', async () => {
  const onResume = vi.fn();
  render(<WorkflowStatus workflow={workflow('blocked')} onResume={onResume} disabled/>);
  const button = screen.getByRole('button', {name: 'Продолжить поручение'});
  expect(button).toBeDisabled();
  await userEvent.click(button);
  expect(onResume).not.toHaveBeenCalled();
});

it('retains stopped goals without offering automatic continuation', () => {
  render(<WorkflowStatus workflow={workflow('cancelled')} onResume={() => {}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение остановлено');
  expect(screen.getByText('Изменить название насоса НС-01')).toBeVisible();
  expect(screen.getByText(/Незавершённые пункты сохранены/)).toBeVisible();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('does not retry uncertain writes but allows independent pending work to continue', () => {
  const {rerender} = render(<WorkflowStatus workflow={workflow('uncertain', 'partial')} onResume={() => {}}/>);
  expect(screen.getByText(/Сначала проверьте состояние данных/)).toBeVisible();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  rerender(<WorkflowStatus workflow={{outcome: 'partial', goals: [
    {id: 'write', title: 'Переименовать насос', status: 'uncertain'},
    {id: 'registry', title: 'Проверить оборудование', status: 'planned'},
  ]}} onResume={() => {}}/>);
  expect(screen.getByRole('button', {name: 'Продолжить поручение'})).toBeEnabled();
});

it('bounds visible goals and renders untrusted titles as plain text', () => {
  render(<WorkflowStatus workflow={{outcome: 'planned', goals: Array.from({length: 20}, (_, index) => ({
    id: String(index), title: index === 0 ? '<img src=x onerror=alert(1)>' : `Пункт ${index + 1}`, status: 'planned',
  }))}}/>);
  expect(screen.getAllByRole('listitem')).toHaveLength(12);
  expect(screen.getByText(/Показаны первые 12 пунктов из 20/)).toBeVisible();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
});

it('handles old turns without a workflow and empty or unknown states honestly', () => {
  const {rerender} = render(<WorkflowStatus/>);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  rerender(<WorkflowStatus workflow={{outcome: 'completed', goals: []}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение не завершено');
  expect(screen.getByText(/Проверенный план пока не получен/)).toBeVisible();
  rerender(<WorkflowStatus workflow={workflow('new-server-state')}/>);
  expect(screen.getByText('Статус требует проверки')).toBeVisible();
  expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  expect(screen.getByRole('status')).toHaveAttribute('aria-atomic', 'true');
});

it('keeps running work visible and does not offer a second execution', () => {
  render(<WorkflowStatus workflow={workflow('running')} onResume={() => {}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение выполняется');
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
