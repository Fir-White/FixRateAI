import {beforeEach, expect, it, vi} from 'vitest';
import {render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter, useNavigate} from 'react-router-dom';
import {AssistantPage} from '@/pages/AssistantPage';
import {WorkflowStatus, type WorkflowGoalView} from '@/features/assistant/WorkflowStatus';
import {assistantApi as api, type ChatAction, type ChatAttachment, type ChatCapabilities, type ChatView} from '@/shared/api/assistant';
import {WorkspaceStateScope} from '@/shared/lib/workspaceState';

const session = vi.hoisted(() => ({profile: {userId: 'QA-USER', siteId: 'QA-SITE', role: 'chief_engineer'}}));
vi.mock('@/shared/session/SessionContext', () => ({useSession: () => session}));

interface PhaseGoal extends WorkflowGoalView {
  kind: 'change';
  pending_action_id: string | null;
  phase_action_ids: string[];
}

const capabilities: ChatCapabilities = {
  available: true, model_ref: 'TEST-ONLY', prompt_version: 'TEST-ONLY',
  agents: [{id: 'assistant', title: 'Помощник', description: 'TEST ONLY'}],
  tools: {assistant: [{name: 'draft_save', title: 'Сохранить черновик', requires_confirmation: true}], planner: [], photo: []},
};
const conversation = {conversation_id: 'macro-chat', title: 'Многошаговое поручение', agent: 'assistant' as const, created_at: '2026-11-16', updated_at: '2026-11-16'};
const pendingFile: ChatAttachment = {attachment_id: 'next-file', original_name: 'Next-private.xlsx', mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', size_bytes: 512, sha256: 'a'.repeat(64), created_at: '2026-11-16T09:00:00Z'};
const proposal: ChatAction = {
  action_id: 'phase-1', conversation_id: conversation.conversation_id, turn_id: 'macro-turn', tool_name: 'draft_save',
  arguments: {body: {title: 'TEST reviewed draft'}}, payload_sha256: 'b'.repeat(64), before_snapshot: null,
  explanation: 'Подготовить черновик; расчёт и выпуск требуют отдельных шагов.', status: 'proposed', result: null,
  expires_at: '2099-01-01T00:00:00Z', created_at: '2026-11-16T09:00:00Z',
};

function goal(status = 'planned'): PhaseGoal {
  return {id: 'plan-optimize', title: 'Подготовить и проверить новый график', status, kind: 'change',
    action_id: null, pending_action_id: status === 'awaiting_confirmation' ? 'phase-1' : null,
    phase_action_ids: status === 'awaiting_confirmation' ? [] : ['phase-1']};
}

function view(status = 'planned', action?: ChatAction, files: ChatAttachment[] = []): ChatView {
  return {conversation, total: 1, actions: action ? [action] : [], attachments: files, pending_attachments: files,
    turns: [{turn_id: 'macro-turn', content: 'Подготовь график, запусти расчёт и проверь его', answer: 'Ответ подготовлен; поручение продолжается.',
      status: 'completed', error_code: null, trace: [], model_ref: 'TEST-ONLY', created_at: '2026-11-16T09:00:00Z', finished_at: '2026-11-16T09:00:10Z',
      workflow: {outcome: status === 'awaiting_confirmation' ? 'awaiting_confirmation' : status === 'completed' ? 'completed' : 'partial', goals: [goal(status)]}}]};
}

beforeEach(() => {
  vi.restoreAllMocks();
  session.profile = {userId: 'QA-USER', siteId: 'QA-SITE', role: 'chief_engineer'};
  vi.spyOn(api, 'capabilities').mockResolvedValue(capabilities);
  vi.spyOn(api, 'list').mockResolvedValue({items: [conversation], total: 1});
  vi.spyOn(api, 'read').mockResolvedValue(view());
  vi.spyOn(api, 'send').mockResolvedValue({turn_id: 'continued-turn', status: 'running'});
});

function RouteControls() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate(-1)}>QA Back</button><button onClick={() => navigate(1)}>QA Forward</button></>;
}

function Page({entries = ['/assistant?chat=macro-chat']}: {entries?: string[]}) {
  return <WorkspaceStateScope.Provider value={`${session.profile.userId}:${session.profile.siteId}:${session.profile.role}`}>
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}><RouteControls/><AssistantPage/></MemoryRouter>
  </WorkspaceStateScope.Provider>;
}

it('uses persisted goal status rather than a completed phase receipt to announce business completion', () => {
  const onResume = vi.fn();
  const {rerender} = render(<WorkflowStatus workflow={{outcome: 'awaiting_confirmation', goals: [goal('awaiting_confirmation')]}} onResume={onResume}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение ожидает подтверждения');
  expect(screen.queryByRole('button', {name: 'Продолжить поручение'})).not.toBeInTheDocument();
  rerender(<WorkflowStatus workflow={{outcome: 'partial', goals: [goal('planned')]}} onResume={onResume}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Поручение не завершено');
  expect(screen.getByRole('status')).toHaveTextContent('0 из 1');
  expect(screen.getByRole('button', {name: 'Продолжить поручение'})).toBeEnabled();
  expect(onResume).not.toHaveBeenCalled();
});

it('labels prose-only responses without counting them as verified business outcomes', () => {
  const onResume = vi.fn();
  render(<WorkflowStatus workflow={{outcome: 'response_only', goals: [
    {id: 'reply', title: 'Объяснить возможности помощника', status: 'answered'},
  ]}} onResume={onResume}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Ответ подготовлен');
  expect(screen.getByRole('status')).toHaveTextContent('0 из 1');
  expect(screen.getByText('Ответ подготовлен; результат не проверен')).toBeVisible();
  expect(screen.queryByText('Поручение выполнено')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: 'Продолжить поручение'})).not.toBeInTheDocument();
  expect(onResume).not.toHaveBeenCalled();
});

it('keeps an unknown postcondition incomplete even when the phase write has a succeeded receipt', async () => {
  const succeeded = {...proposal, status: 'succeeded' as const, result: {verification: {status: 'unverified' as const, summary: 'Запись получена, результат требует отдельной проверки.'}}};
  vi.mocked(api.read).mockResolvedValue(view('partial', succeeded));
  render(<Page/>);
  expect(await screen.findByText(/Поручение не завершено/)).toBeVisible();
  const card = screen.getByRole('region', {name: 'Предложение: Сохранить черновик'});
  expect(within(card).getByRole('status')).toHaveTextContent('Действие завершилось. Результат требует проверки');
  expect(screen.queryByText('Поручение выполнено')).not.toBeInTheDocument();
});

it('refreshes a confirmed macro phase to planned and waits for explicit resume without clearing a draft', async () => {
  const user = userEvent.setup();
  let confirmed = false;
  const receipt = {...proposal, status: 'succeeded' as const, result: {verification: {status: 'confirmed' as const, summary: 'Черновик сохранён и проверен.'}}};
  vi.mocked(api.read).mockImplementation(async () => confirmed ? view('planned', receipt, [pendingFile]) : view('awaiting_confirmation', proposal, [pendingFile]));
  vi.spyOn(api, 'confirm').mockImplementation(async () => {confirmed = true; return receipt;});
  render(<Page/>);
  const input = await screen.findByLabelText('Сообщение помощнику');
  await user.type(input, 'Новый самостоятельный вопрос');
  await user.click(screen.getByRole('checkbox', {name: 'Я проверил параметры и подтверждаю это изменение'}));
  await user.click(screen.getByRole('button', {name: 'Подтвердить и выполнить'}));
  expect(await screen.findByText(/Поручение не завершено/)).toBeVisible();
  expect(api.send).not.toHaveBeenCalled();
  expect(input).toHaveValue('Новый самостоятельный вопрос');
  await user.click(screen.getByRole('button', {name: 'Продолжить поручение'}));
  await waitFor(() => expect(api.send).toHaveBeenCalledWith('macro-chat', 'Продолжить сохранённое поручение.', expect.any(String), [], undefined, 'macro-turn'));
  expect(input).toHaveValue('Новый самостоятельный вопрос');
  expect(screen.getByRole('list', {name: 'Вложения к сообщению'})).toHaveTextContent(pendingFile.original_name);
});

it('reuses the resume attempt after a lost response and preserves unrelated draft and pending files', async () => {
  const user = userEvent.setup();
  vi.mocked(api.read).mockResolvedValue(view('planned', undefined, [pendingFile]));
  vi.mocked(api.send).mockRejectedValueOnce(new Error('Ответ потерян')).mockResolvedValueOnce({turn_id: 'same-retried-turn', status: 'running'});
  render(<Page/>);
  const input = await screen.findByLabelText('Сообщение помощнику');
  await user.type(input, 'Черновик не относится к продолжению');
  await user.click(screen.getByRole('button', {name: 'Продолжить поручение'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Ответ потерян');
  const first = vi.mocked(api.send).mock.calls[0];
  expect(first[2]).toBeTruthy();
  await user.click(screen.getByRole('button', {name: 'Продолжить поручение'}));
  await waitFor(() => expect(api.send).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.send).mock.calls[1]).toEqual(first);
  expect(input).toHaveValue('Черновик не относится к продолжению');
  expect(screen.getByRole('list', {name: 'Вложения к сообщению'})).toHaveTextContent(pendingFile.original_name);
});

it('replaces an executing confirmation response with the newer verified phase from the server', async () => {
  const user = userEvent.setup();
  let dispatched = false;
  const verified = {...proposal, status: 'succeeded' as const, result: {verification: {status: 'confirmed' as const, summary: 'Первая фаза проверена.'}}};
  vi.mocked(api.read).mockImplementation(async () => dispatched ? view('planned', verified) : view('awaiting_confirmation', proposal));
  // A concurrent confirmer may receive executing while the first worker owns
  // dispatch; subsequent authenticated GET is the newer authority.
  vi.spyOn(api, 'confirm').mockImplementation(async () => {dispatched = true; return {...proposal, status: 'executing'};});
  render(<Page/>);
  await screen.findByText(/Поручение ожидает подтверждения/);
  await user.click(screen.getByRole('checkbox', {name: 'Я проверил параметры и подтверждаю это изменение'}));
  await user.click(screen.getByRole('button', {name: 'Подтвердить и выполнить'}));
  await screen.findByRole('button', {name: 'Продолжить поручение'});
  const card = screen.getByRole('region', {name: 'Предложение: Сохранить черновик'});
  await waitFor(() => expect(within(card).getByRole('status')).toHaveTextContent('Выполнено и проверено'));
  expect(screen.getByText(/Поручение не завершено/)).toBeVisible();
  expect(api.send).not.toHaveBeenCalled();
});

it('restores drafts and server pending attachments per chat through Back and Forward', async () => {
  const user = userEvent.setup();
  const firstFile = {...pendingFile, attachment_id: 'first-file', original_name: 'First-private.xlsx'};
  vi.mocked(api.read).mockImplementation(async id => ({...view('planned', undefined, id === 'first' ? [firstFile] : [pendingFile]), conversation: {...conversation, conversation_id: id}}));
  render(<Page entries={['/assistant?chat=first', '/assistant?chat=second']}/>);
  await user.type(await screen.findByLabelText('Сообщение помощнику'), 'Черновик второго чата');
  await user.click(screen.getByRole('button', {name: 'QA Back'}));
  const firstInput = await screen.findByLabelText('Сообщение помощнику');
  expect(firstInput).toHaveValue('');
  await user.type(firstInput, 'Черновик первого чата');
  expect(screen.getByRole('list', {name: 'Вложения к сообщению'})).toHaveTextContent(firstFile.original_name);
  await user.click(screen.getByRole('button', {name: 'QA Forward'}));
  expect(await screen.findByLabelText('Сообщение помощнику')).toHaveValue('Черновик второго чата');
  expect(screen.getByRole('list', {name: 'Вложения к сообщению'})).toHaveTextContent(pendingFile.original_name);
  expect(screen.queryByText(firstFile.original_name)).not.toBeInTheDocument();
});

it('drops prior role and site UI state before an unauthorized chat read resolves', async () => {
  const user = userEvent.setup();
  vi.mocked(api.read).mockResolvedValue(view('planned', undefined, [pendingFile]));
  const {rerender} = render(<Page/>);
  await user.type(await screen.findByLabelText('Сообщение помощнику'), 'PRIVATE OLD SCOPE DRAFT');
  session.profile = {userId: 'QA-USER', siteId: 'OTHER-SITE', role: 'executor'};
  vi.mocked(api.list).mockResolvedValue({items: [], total: 0});
  vi.mocked(api.read).mockRejectedValue(new Error('Диалог не найден в текущем контексте'));
  rerender(<Page/>);
  expect(screen.queryByDisplayValue('PRIVATE OLD SCOPE DRAFT')).not.toBeInTheDocument();
  expect(screen.queryByText(pendingFile.original_name)).not.toBeInTheDocument();
  expect(await screen.findByText('Диалог не найден в текущем контексте')).toBeVisible();
  expect(api.send).not.toHaveBeenCalled();
});
