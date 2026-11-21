import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { preloadPage } from '@/app/pageModules';
import { assistantApi, type ChatModelPreference } from '@/shared/api/assistant';
import { DEMO_MODE } from '@/shared/api/request';
import { useApiQueryCache } from '@/shared/lib/ApiQueryProvider';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Callout } from '@/shared/ui/Callout';
import { AssistantComposer, type ComposerHandle } from './AssistantComposer';
import { DEFAULT_STARTERS, EXECUTOR_STARTERS, transferAssistantDraft } from './assistantEntry';
import { useConversationStart } from './useConversationStart';

export function WorkdayAssistant({executor = false, chiefWorkday = false}: {executor?: boolean; chiefWorkday?: boolean}) {
  const composer = useRef<ComposerHandle>(null);
  const draft = useRef('');
  const [model, setModel] = useState<ChatModelPreference>();
  const entry = useRef<HTMLElement>(null);
  const cache = useApiQueryCache();
  const navigate = useNavigate();
  const capabilities = useApiQuery(() => DEMO_MODE ? Promise.resolve(null) : assistantApi.capabilities(),
    [], undefined, DEMO_MODE ? undefined : 'assistant:capabilities');
  const serverModel = capabilities.data?.model_preference;
  const preference = model && model.revision >= (serverModel?.revision ?? 0) ? model : serverModel;
  const start = useConversationStart({
    model: preference,
    onModelChange: setModel,
    onOpen(id, remainingDraft) {
      transferAssistantDraft(cache, id, remainingDraft, entry.current?.querySelector('form')?.getBoundingClientRect());
      composer.current?.replaceDraft('');
      navigate(`/assistant?chat=${encodeURIComponent(id)}`);
    },
  });
  const starters = executor ? EXECUTOR_STARTERS : DEFAULT_STARTERS;
  const available = capabilities.data?.available ?? false;
  const warm = () => { void preloadPage('/assistant')?.catch(() => {}); };

  return <section ref={entry} className="e3-workday-assistant" aria-label="FixRate AI" onFocus={warm} onPointerEnter={warm}>
    <AssistantComposer ref={composer} showMark chiefWorkday={chiefWorkday} available={available} running={false} onDraftChange={text => { draft.current = text; }}
      busy={start.operation === 'send'} uploading={start.operation === 'upload'}
      onSend={text => void start.start(text)} onUpload={(file, text) => void start.start(text, {file})}
      modelPreference={preference} onModelChange={setModel}/>
    <div className="e3-starters">
      {starters.map(preset => <button type="button" key={preset.label} disabled={!!start.operation || !(preference?.available ?? available)}
        onClick={() => void start.start(preset.prompt, {remainingDraft: draft.current})}>
        {preset.label}
      </button>)}
      <Link to="/assistant" className="e3-chat-link">Открыть диалоги <span aria-hidden="true">→</span></Link>
    </div>
    {capabilities.status==="success" && capabilities.data && !(preference?.available??available) &&
      <p className="e3-model-status" role="status">Чтобы отправить сообщение, выберите доступную модель.</p>}
    {(start.error || capabilities.error) && <div role="alert"><Callout tone="danger">{start.error || capabilities.error}</Callout></div>}
  </section>;
}
