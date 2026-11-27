import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { OrderTable } from '@/features/planning/OrderTable';

const row = (state: string) => ({task_id:'b0cc1547-301f-46bb-8e3a-c522cb602d39',revision:3,state,
  title:'Проверка манометра',equipment:'Манометр',system:'ИТП',due_date:'2027-01-29',planned_start:'2027-01-29T09:00',
  planned_end:'2027-01-29T10:00',normative_hours:'1',normative_unit:'person_hour',planned_person_hours:null,note:'',locked_reason:null});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(['draft','assigned'])('checks before writing and requires a separate confirmation for %s', async state => {
  const assigned=state==='assigned', calls:{path:string;body:any}[]=[];
  vi.stubGlobal('fetch',vi.fn(async (path:string,options:RequestInit) => {
    const body=options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({path,body});
    const payload = path.endsWith('/preview') ? {can_apply:true,requires_assigned_confirmation:assigned,preview_digest:'a'.repeat(64),
      items:[{index:0,action:assigned?'reschedule':'update',task_id:row(state).task_id,title:row(state).title,
        equipment:'Манометр №2',due_date:'2027-01-29',planned_start:'2027-01-29T11:00'}]} :
      path.endsWith('/apply') ? {items:[{task_id:row(state).task_id,action:assigned?'reschedule':'update',revision:4}],replayed:false} :
      {items:[row(state)],has_more:false,timezone:'UTC'};
    return new Response(JSON.stringify(payload),{headers:{'content-type':'application/json'}});
  }));
  render(<MemoryRouter><OrderTable month="2027-01" onMonth={() => {}} timezone="UTC"/></MemoryRouter>);
  const work=await screen.findByRole('row',{name:/Проверка манометра/});
  fireEvent.click(within(work).getByRole('button',{name:/Плановое начало/}));
  const calendar=screen.getByRole('dialog');
  fireEvent.change(within(calendar).getByLabelText('Часы'),{target:{value:'11'}});
  fireEvent.click(within(calendar).getByRole('button',{name:'Применить'}));
  fireEvent.change(screen.getByLabelText('Основание изменения'),{target:{value:'Изменение окна'}});
  expect(calls.every(value=>value.body===null)).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:assigned?'Проверить перенос':'Проверить изменения'}));
  const dialog=await screen.findByRole('dialog');
  expect(within(dialog).getByText(/Проверка манометра · Манометр №2/)).toBeTruthy();
  expect(within(dialog).getByText('Обязательный срок: 2027-01-29')).toBeTruthy();
  const confirm=within(dialog).getByRole('button',{name:assigned?'Подтвердить перенос':'Применить изменения'});
  expect((confirm as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(value=>value.path.endsWith('/apply'))).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole('checkbox'));
  fireEvent.click(confirm);
  await waitFor(()=>expect(calls.filter(value=>value.path.endsWith('/apply'))).toEqual([expect.objectContaining({body:expect.objectContaining({
    changes:[{kind:'existing',task_id:row(state).task_id,expected_revision:3,planned_start:'2027-01-29T11:00'}],
    confirm_assigned:assigned,preview_digest:'a'.repeat(64)})})]));
  expect(await screen.findByText('Изменения сохранены.')).toBeTruthy();
});

it('keeps a new row in the editor without sending an incomplete request', async () => {
  const requests:string[]=[];
  vi.stubGlobal('fetch', vi.fn(async (url:string) => {
    requests.push(url);
    const payload=url.endsWith('/preview') ? {can_apply:false,requires_assigned_confirmation:false,preview_digest:null,items:[{index:0,action:'blocked',issue:'Дата вне окна'}]} :
      url.includes('/bindings?') ? {items:[],has_more:false} : {items:[],has_more:false,timezone:'UTC'};
    return new Response(JSON.stringify(payload),{headers:{'content-type':'application/json'}});
  }));
  render(<MemoryRouter><OrderTable month="2027-01" onMonth={() => {}} timezone="UTC"/></MemoryRouter>);
  await screen.findByText(/Нет нарядов/);
  fireEvent.click(screen.getByRole('button',{name:'Добавить строку'}));
  await screen.findByText('Нет подходящих утверждённых привязок.');
  fireEvent.change(screen.getByLabelText('Основание изменения'),{target:{value:'TEST'}});
  fireEvent.click(screen.getByRole('button',{name:'Проверить изменения'}));
  expect(screen.getByRole('alert').textContent).toMatch(/Укажите регламент/);
  expect(screen.getByRole('group',{name:'Строка 1'})).toBeTruthy();
  expect(requests.some(url=>url.endsWith('/preview')||url.endsWith('/apply'))).toBe(false);
});

it('shows the unsaved value after a revision conflict without retrying the write', async () => {
  let writes=0;
  vi.stubGlobal('fetch',vi.fn(async (url:string) => {
    const current=row('draft');
    if(url.endsWith('/apply')){
      writes++;
      return Response.json({detail:'Предпросмотр устарел'},{status:409});
    }
    if(url.endsWith('/preview'))return Response.json({can_apply:true,requires_assigned_confirmation:false,preview_digest:'a'.repeat(64),
      items:[{index:0,action:'update',task_id:current.task_id,title:current.title,note:'Мои несохранённые данные'}]});
    return Response.json({items:[writes?{...current,revision:4,note:'Правка коллеги'}:current],has_more:false,timezone:'UTC'});
  }));
  render(<MemoryRouter><OrderTable month="2027-01" onMonth={() => {}} timezone="UTC"/></MemoryRouter>);
  const displayed=await screen.findByRole('row',{name:/Проверка манометра/});
  fireEvent.change(within(displayed).getByLabelText(/Примечание/),{target:{value:'Мои несохранённые данные'}});
  fireEvent.change(screen.getByLabelText('Основание изменения'),{target:{value:'Тест конфликта'}});
  fireEvent.click(screen.getByRole('button',{name:'Проверить изменения'}));
  const pending=await screen.findByRole('dialog');
  fireEvent.click(within(pending).getByRole('checkbox'));
  fireEvent.click(within(pending).getByRole('button',{name:'Применить изменения'}));
  await screen.findByText('Правка коллеги');
  const stale=screen.getByRole('row',{name:/Проверка манометра/});
  expect(within(stale).getByText('Примечание: Мои несохранённые данные')).toBeTruthy();
  expect(screen.getByRole('alert').textContent).toBe('Предпросмотр устарел');
  expect(writes).toBe(1);
});
