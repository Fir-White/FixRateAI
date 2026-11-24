import {lazy, memo, startTransition, Suspense, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {FactsAnswer} from './FactsAnswer';

const MarkdownAnswer = lazy(() => import('./AssistantAnswer').then(module => ({default: module.AssistantAnswer})));

/** Only older long answer bodies fold; prompts, workflow and action cards stay outside. */
export const SavedAnswer = memo(function SavedAnswer({answer, facts = false, older = false}: {
  answer: string; facts?: boolean; older?: boolean;
}) {
  const folded = older && answer.length >= 2500;
  const startedVisible = useRef(!folded);
  const [rich, setRich] = useState(!folded);
  const details = useRef<HTMLDetailsElement>(null);
  useLayoutEffect(() => {
    // An answer already being read must not collapse when a new turn arrives.
    if (!folded) startedVisible.current = true;
    if (folded && startedVisible.current && details.current) details.current.open = true;
  }, [folded]);
  useEffect(() => {
    const element = details.current;
    if (!folded || !element) return;
    // Native find may expose the original text; never replace its selected DOM node.
    const expose = () => {element.open = true;};
    element.addEventListener('beforematch', expose);
    return () => element.removeEventListener('beforematch', expose);
  }, [folded]);
  const formatted = facts ? <FactsAnswer answer={answer}/> :
    <Suspense fallback={<div className="assistant-answer whitespace-pre-wrap">{answer}</div>}>
      <MarkdownAnswer answer={answer}/>
    </Suspense>;
  if (answer.length < 2500) return formatted;
  return <details ref={details} open={!older || undefined} className="assistant-saved-answer">
    <summary hidden={!older} onClick={() => {if (!details.current?.open) startTransition(() => setRich(true));}}>
      Сохранённый ответ ({answer.length} символов)
    </summary>
    {rich ? formatted : <div className="assistant-saved-plain">{answer}</div>}
  </details>;
});
