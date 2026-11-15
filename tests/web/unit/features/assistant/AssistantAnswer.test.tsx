import {expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import {AssistantAnswer} from '@/features/assistant/AssistantAnswer';

it('renders a substantial analysis with headings, lists, tables and code',()=>{
  const {container}=render(<AssistantAnswer answer={'## Анализ таблицы\n\nСумма: **20 часов**.\n\n- Насос: 12\n- Вентилятор: 8\n\n| Работа | Часы |\n|---|---|\n| Насос | 12 |\n\n```text\nA1: вид работ\n```'}/>);
  expect(screen.getByRole('heading',{name:'Анализ таблицы'})).toBeInTheDocument();
  expect(screen.getByRole('list')).toBeInTheDocument();
  expect(screen.getByRole('table')).toHaveTextContent('Насос');
  expect(container.querySelector('strong')).toHaveTextContent('20 часов');
  expect(container.querySelector('pre')).toHaveTextContent('A1: вид работ');
});

it('never executes model HTML, unsafe URLs or external image requests',()=>{
  const {container}=render(<AssistantAnswer answer={'<script>alert(1)</script>\n\n<img src="https://tracker.example/secret" onerror="alert(1)">\n\n![image](https://tracker.example/secret)\n\n[unsafe](javascript:alert%281%29)\n\n[safe](https://example.test/doc)'}/>);
  expect(container.querySelector('script,img')).toBeNull();
  expect(screen.getByText('unsafe').getAttribute('href')).not.toMatch(/^javascript:/);
  expect(screen.getByRole('link',{name:'safe'})).toHaveAttribute('rel','noopener noreferrer');
});
