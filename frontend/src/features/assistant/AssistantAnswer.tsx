import {memo} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const plugins=[remarkGfm];
const components={
  table:({children}:{children?:React.ReactNode})=><div className="assistant-answer-table" tabIndex={0}><table>{children}</table></div>,
  a:({href,children}:{href?:string;children?:React.ReactNode})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
};

// Never interpret model HTML or automatically fetch external images.
export const AssistantAnswer=memo(function AssistantAnswer({answer}:{answer:string}){
  return <div className="assistant-answer"><Markdown remarkPlugins={plugins} components={components} skipHtml disallowedElements={['img']}>{answer}</Markdown></div>;
});
