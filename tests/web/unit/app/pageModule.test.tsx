import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { lazyPage, pageModule } from '@/app/pageModule';

function Editor() { return <input aria-label="Черновик" defaultValue=""/>; }

it('renders a preloaded route immediately without a Suspense loading frame',async()=>{
  const load=pageModule(async()=>({default:Editor}));
  await load();const Page=lazyPage(load);render(<Page/>);
  expect(screen.getByRole('textbox',{name:'Черновик'})).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('preserves the active editor draft after a cold module resolves and its parent rerenders',async()=>{
  let resolve!:(value:{default:typeof Editor})=>void;
  const load=pageModule(()=>new Promise(done=>{resolve=done;}));
  const Page=lazyPage(load);const view=render(<Page/>);
  expect(screen.getByRole('status')).toBeInTheDocument();
  await act(async()=>{resolve({default:Editor});});
  const input=screen.getByRole('textbox',{name:'Черновик'});
  fireEvent.change(input,{target:{value:'Сохранить ввод'}});
  view.rerender(<Page/>);
  expect(screen.getByRole('textbox',{name:'Черновик'})).toBe(input);
  expect(input).toHaveValue('Сохранить ввод');
});

it('deduplicates module preload and retries after a failed background fetch',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({default:Editor});
  const load=pageModule(fetch);const first=load();expect(load()).toBe(first);
  await expect(first).rejects.toThrow('Offline');expect(load.peek()).toBeUndefined();
  await load();expect(load.peek()).toBe(Editor);expect(fetch).toHaveBeenCalledTimes(2);
});
