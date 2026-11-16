import {act, fireEvent, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, it} from 'vitest';
import {SavedAnswer} from '@/features/assistant/SavedAnswer';

const answer = '### Сохранённая инструкция\n\n' + '- Исходное поле: полный текст без выдуманных единиц.\n'.repeat(80);

it('renders the newest long answer eagerly and preserves already visible content when it becomes older', () => {
  const {container, rerender} = render(<SavedAnswer answer={answer}/>);
  expect(screen.getByRole('heading', {name: 'Сохранённая инструкция'})).toBeVisible();
  expect(container.querySelector('details')).toHaveAttribute('open');
  const body=container.querySelector('.assistant-answer');
  rerender(<SavedAnswer answer={answer} older/>);
  expect(container.querySelector('details')).toHaveAttribute('open');
  expect(screen.getByRole('heading', {name: 'Сохранённая инструкция'})).toBeVisible();
  expect(container.querySelector('.assistant-answer')).toBe(body);
});

it('keeps the original saved source in the DOM without parsing closed long history', () => {
  const {container} = render(<><p>Поручение ещё не выполнено</p><SavedAnswer answer={answer} older/><button>Подтвердить действие</button></>);
  expect(container.querySelector('details')).not.toHaveAttribute('open');
  expect(container.querySelector('.assistant-saved-plain')!.textContent).toBe(answer);
  expect(container.querySelector('.assistant-answer')).toBeNull();
  expect(screen.getByRole('button', {name: 'Подтвердить действие'})).toBeVisible();
  expect(screen.getByText('Поручение ещё не выполнено')).toBeVisible();
});

it('retains the native summary and focus after explicit open hydrates all original fields', async () => {
  const user = userEvent.setup();
  const {container} = render(<SavedAnswer answer={answer} older facts/>);
  const summary = container.querySelector('summary')!;
  await user.click(summary);
  expect(container.querySelector('summary')).toBe(summary);
  expect(summary).toHaveFocus();
  expect(screen.getByRole('heading', {name: 'Сохранённая инструкция'})).toBeVisible();
  expect(screen.getAllByRole('listitem')).toHaveLength(80);
});

it('does not replace the original text when the browser opens details without a summary click', () => {
  const {container} = render(<SavedAnswer answer={answer} older/>);
  const details = container.querySelector('details')!, original = container.querySelector('.assistant-saved-plain');
  act(() => {details.open = true; fireEvent(details, new Event('toggle'));});
  expect(container.querySelector('.assistant-saved-plain')).toBe(original);
  expect(original!.textContent).toBe(answer);
  expect(container.querySelector('.assistant-answer')).toBeNull();
});

it('treats unformatted saved source as React text and keeps short older replies expanded', () => {
  const unsafe = '<script>alert(1)</script><img src=https://external.test/secret>\n' + answer;
  const first = render(<SavedAnswer answer={unsafe} older/>);
  expect(first.container.querySelector('script,img')).toBeNull();
  expect(first.container.querySelector('.assistant-saved-plain')!.textContent).toBe(unsafe);
  first.unmount();
  const second = render(<SavedAnswer answer="Короткий ответ" older/>);
  expect(second.container.querySelector('details')).toBeNull();
  expect(screen.getByText('Короткий ответ')).toBeVisible();
});

it('exposes a native beforematch result without replacing the original searchable text', () => {
  const {container} = render(<SavedAnswer answer={answer} older/>);
  const details = container.querySelector('details')!, original = container.querySelector('.assistant-saved-plain')!;
  act(() => {original.dispatchEvent(new Event('beforematch', {bubbles: true}));});
  expect(details.open).toBe(true);
  expect(container.querySelector('.assistant-saved-plain')).toBe(original);
  expect(original.textContent).toBe(answer);
});
