import {expect, it} from 'vitest';
import {render, screen, within} from '@testing-library/react';
import {FactsAnswer} from '@/features/assistant/FactsAnswer';

it('renders server headings, nested factual lists and literal values without changing units', () => {
  render(<FactsAnswer answer={'### Сотрудник\n\n- ФИО: Анна Петрова.\n\n  - Доступ действует: нет.\n  - Норма: 0.\n  - Единица: не указано.\n  - Смены: записей 0.\nИсточник: staff_read.'}/>);
  expect(screen.getByRole('heading', {name: 'Сотрудник', level: 3})).toBeVisible();
  expect(screen.getAllByRole('list')).toHaveLength(2);
  expect(screen.getByText('Доступ действует: нет.')).toBeVisible();
  expect(screen.getByText('Норма: 0.')).toBeVisible();
  expect(screen.getByText('Единица: не указано.')).toBeVisible();
  expect(screen.getByText('Смены: записей 0.')).toBeVisible();
});

it('never interprets raw HTML, Markdown images, external URLs or escaped data as links', () => {
  const {container} = render(<FactsAnswer answer={[
    '### <img src=x onerror=alert(1)>', '<script>alert(1)</script>',
    '![secret](https://external.test/secret)', '[external](https://external.test/file).',
    '[unsafe](javascript:alert(1)).',
    '\\[data\\](/api/v1/maintenance/management/workforce).',
    '- Значение: [inline](/api/v1/maintenance/management/workforce).',
    '- ФИО: Иван\\_Петров \\[источник\\] \\*значение\\*.',
  ].join('\n')}/>);
  expect(container.querySelector('script,img')).toBeNull();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByText('ФИО: Иван_Петров [источник] *значение*.')).toBeVisible();
  expect(screen.getByText('[data](/api/v1/maintenance/management/workforce).')).toBeVisible();
});

it('recognizes an entire server internal detail-link stanza before unescaping', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  render(<FactsAnswer answer={[
    `[Текущий сотрудник](/api/v1/assistant/workspace/staff/${id}).`,
    `[Текущий отчёт](/api/v1/maintenance/ui/tasks/${id}).`,
    '[Текущая команда](/api/v1/maintenance/management/workforce).',
    `[Изменения версий](/api/v1/assistant/workspace/draft-changes?identity=${id}&before_revision=2&after_revision=3).`,
    '[Несуществующий маршрут](/api/v1/maintenance/users/me).',
    `[Повтор параметра](/api/v1/assistant/workspace/draft-changes?identity=${id}&before_revision=2&after_revision=3&after_revision=4).`,
  ].join('\n')}/>);
  expect(screen.getAllByRole('link')).toHaveLength(4);
  expect(screen.getByRole('link', {name: 'Текущая команда'})).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.queryByRole('link', {name: 'Повтор параметра'})).not.toBeInTheDocument();
});

it('keeps unknown grammar literal and exposes every one of 140 factual rows immediately', () => {
  const answer = '### Полный результат\n' + Array.from({length: 140}, (_, i) => '- Уникальное поле ' + i + ': сохранено.').join('\n') + '\n   - Неподдержанный отступ: сохранён.';
  const {container} = render(<FactsAnswer answer={answer} historical/>);
  expect(screen.getAllByRole('listitem')).toHaveLength(140);
  expect(within(container).getByText('Уникальное поле 139: сохранено.')).toBeVisible();
  expect(container.textContent).toContain('Неподдержанный отступ: сохранён.');
  expect(container.querySelector('.assistant-facts-history')).not.toBeNull();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
