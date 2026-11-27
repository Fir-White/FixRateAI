import {memo, useMemo} from 'react';

interface Item {text: string; children: Item[]}
type Block = {kind: 'heading' | 'text'; text: string} | {kind: 'list'; items: Item[]} |
  {kind: 'link'; text: string; href: string};

// Inverse of the server's _inline escapes, only after identifying a link stanza.
const unescape = (value: string) => value.replace(/\\([\\*_\[\]<>|`])/g, '$1');
const uuid = '[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}';
const single = new RegExp('^/api/v1/(?:assistant/workspace/staff|maintenance/ui/tasks)/' + uuid + '$');

function internalDetails(href: string) {
  if (single.test(href) || href === '/api/v1/maintenance/management/workforce') return true;
  if (!href.startsWith('/api/v1/assistant/workspace/draft-changes?')) return false;
  const url = new URL(href, 'http://facts.invalid');
  const query = url.searchParams;
  return !url.hash && [...query].length === 3 && new RegExp('^' + uuid + '$').test(query.get('identity') ?? '') &&
    ['before_revision', 'after_revision'].every(key => /^[1-9]\d*$/.test(query.get(key) ?? ''));
}

/** Only the server's factual grammar. Unknown syntax remains literal React text. */
function blocksOf(answer: string): Block[] {
  const blocks: Block[] = [];
  let current: Extract<Block, {kind: 'list'}> | undefined;
  let parents: Item[] = [];
  for (const line of answer.split('\n')) {
    if (!line.trim()) continue;
    const bullet = /^((?:  ){0,6})- (.*)$/.exec(line);
    if (bullet) {
      const depth = bullet[1].length / 2;
      if (!current && depth === 0) {current = {kind: 'list', items: []}; blocks.push(current);}
      if (current && depth <= parents.length) {
        const item: Item = {text: unescape(bullet[2]), children: []};
        (depth === 0 ? current.items : parents[depth - 1].children).push(item);
        parents = parents.slice(0, depth); parents.push(item);
        continue;
      }
    }
    current = undefined; parents = [];
    const heading = /^### (.+)$/.exec(line);
    if (heading) {blocks.push({kind: 'heading', text: unescape(heading[1])}); continue;}
    // Match raw bytes BEFORE unescaping. Escaped source data cannot become a link.
    const link = /^\[([^\[\]\\]+)\]\(([^\s()]+)\)\.$/.exec(line);
    if (link && internalDetails(link[2])) {
      blocks.push({kind: 'link', text: unescape(link[1]), href: link[2]}); continue;
    }
    blocks.push({kind: 'text', text: unescape(line)});
  }
  return blocks;
}

function List({items}: {items: Item[]}) {
  return <ul>{items.map((item, index) => <li key={index}>{item.text}{item.children.length > 0 && <List items={item.children}/>}</li>)}</ul>;
}

/** Used only when the backend explicitly marks server-owned generic facts. */
export const FactsAnswer = memo(function FactsAnswer({answer, historical = false}: {answer: string; historical?: boolean}) {
  const blocks = useMemo(() => blocksOf(answer), [answer]);
  return <div className={'assistant-answer assistant-facts' + (historical ? ' assistant-facts-history' : '')}>
    {blocks.map((block, index) => block.kind === 'list' ? <List key={index} items={block.items}/> :
      block.kind === 'heading' ? <h3 key={index}>{block.text}</h3> :
      block.kind === 'link' ? <p key={index}><a href={block.href} target="_blank" rel="noopener noreferrer">{block.text}</a></p> :
      <p key={index}>{block.text}</p>)}
  </div>;
});
