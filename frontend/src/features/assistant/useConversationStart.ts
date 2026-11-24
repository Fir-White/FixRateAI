import { useEffect, useRef, useState } from 'react';
import { assistantApi as api, type ChatModelPreference } from '@/shared/api/assistant';
import { ApiError } from '@/shared/api/request';

type StartOptions = {
  model?: ChatModelPreference;
  subjectTaskId?: string;
  readDraft?: () => string;
  onModelChange: (model: ChatModelPreference) => void;
  onOpen: (id: string, draft: string) => void;
};

export function useConversationStart({model, subjectTaskId, readDraft, onModelChange, onOpen}: StartOptions) {
  const creation = useRef<Promise<string> | null>(null);
  const attempt = useRef<{payload: string; key: string} | null>(null);
  const version = useRef(0);
  const running = useRef(false);
  const [operation, setOperation] = useState<'send' | 'upload' | null>(null);
  const [error, setError] = useState('');

  useEffect(() => () => { version.current += 1; }, []);

  function reset() {
    version.current += 1;
    running.current = false;
    creation.current = null;
    attempt.current = null;
    setError('');
    setOperation(null);
  }

  async function start(text: string, {files = [], remainingDraft = files.length ? text : ''}: {files?: File[]; remainingDraft?: string} = {}) {
    const message = text.trim();
    if (running.current || (!files.length && !message)) return;
    if (files.length > 4) {
      setError('К одному сообщению можно отправить не больше четырёх изображений');
      return;
    }
    const activeVersion = version.current;
    running.current = true;
    setError('');
    setOperation(files.length ? 'upload' : 'send');
    try {
      if (!creation.current) {
        const created = subjectTaskId ? api.create('assistant', subjectTaskId) : api.create('assistant');
        creation.current = created.then(chat => chat.conversation_id).catch(error => {
          if (activeVersion === version.current) creation.current = null;
          throw error;
        });
      }
      const id = await creation.current;
      if (activeVersion !== version.current) return;
      if (files.length) {
        for (const file of files) {
          if (activeVersion !== version.current) return;
          await api.upload(id, file);
        }
      } else {
        const payload = JSON.stringify([id, message, model?.revision]);
        if (attempt.current?.payload !== payload) attempt.current = {payload, key: crypto.randomUUID()};
        await api.send(id, message, attempt.current.key, [], model?.revision);
      }
      if (activeVersion === version.current) onOpen(id, files.length ? readDraft?.() ?? remainingDraft : remainingDraft);
    } catch (failure) {
      if (activeVersion !== version.current) return;
      setError(failure instanceof Error ? failure.message : 'Не удалось начать диалог');
      if (failure instanceof ApiError && failure.status === 409 && model) {
        try {
          const current = await api.modelPreference();
          if (activeVersion === version.current) onModelChange(current);
        } catch { /* Keep the draft available for retry. */ }
      }
    } finally {
      if (activeVersion === version.current) {
        running.current = false;
        setOperation(null);
      }
    }
  }

  return { start, reset, operation, error };
}
