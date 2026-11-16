import {useState} from 'react';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,expect,it,vi} from 'vitest';
import {ChatModelPicker} from '@/features/assistant/ChatModelPicker';
import {assistantApi as api,type ChatModelPreference,type ChatModelCatalog} from '@/shared/api/assistant';
import {ApiError} from '@/shared/api/request';

const preference:ChatModelPreference={selection:{provider:'aitunnel',model:'qwen-test'},revision:7,is_default:false,available:true};
const catalog:ChatModelCatalog={providers:[
  {id:'ollama',name:'Локальные модели',status:'ready',error_code:null,models:[{id:'local-test:latest',name:'local-test:latest',description:'Установлена',selectable:true}]},
  {id:'aitunnel',name:'AI Tunnel',status:'ready',error_code:null,models:Array.from({length:95},(_,n)=>({id:'model-'+String(n).padStart(3,'0'),name:'model-'+String(n).padStart(3,'0'),description:'Fixture metadata',selectable:true}))},
]};
beforeEach(()=>{
  vi.restoreAllMocks();
  vi.spyOn(api,'models').mockResolvedValue(catalog);
  vi.spyOn(api,'selectModel').mockImplementation(async(choice,revision)=>({selection:choice,revision:revision+1,is_default:false,available:true}));
});

function Harness(){const [value,setValue]=useState(preference);return <ChatModelPicker preference={value} disabled={false} onChange={setValue} onBusy={()=>{}}/>;}

it('loads the catalog only when opened, bounds DOM and searches every model without network calls per key',async()=>{
  const user=userEvent.setup();render(<Harness/>);
  expect(api.models).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Выбрать модель: qwen-test'}));
  const dialog=await screen.findByRole('dialog',{name:'Выбор модели чата'});
  await screen.findByRole('button',{name:/local-test:latest/});
  expect(dialog.querySelectorAll('.assistant-model-option')).toHaveLength(30);
  await user.click(within(dialog).getByRole('button',{name:'Далее'}));
  expect(dialog.querySelectorAll('.assistant-model-option')).toHaveLength(30);
  await user.type(screen.getByRole('searchbox',{name:'Поиск модели'}),'model-094');
  expect(await screen.findByRole('button',{name:/model-094/})).toBeVisible();
  expect(dialog.querySelectorAll('.assistant-model-option')).toHaveLength(1);
  expect(api.models).toHaveBeenCalledTimes(1);
});

it('persists the exact provider/model with the current revision and updates the visible selection',async()=>{
  const user=userEvent.setup();render(<Harness/>);
  await user.click(screen.getByRole('button',{name:'Выбрать модель: qwen-test'}));
  await user.click(await screen.findByRole('button',{name:/local-test:latest/}));
  await waitFor(()=>expect(api.selectModel).toHaveBeenCalledWith({provider:'ollama',model:'local-test:latest'},7));
  expect(await screen.findByRole('button',{name:'Выбрать модель: local-test:latest'})).toHaveFocus();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('keeps a failed selection visible without silently replacing the previous model',async()=>{
  const user=userEvent.setup();vi.mocked(api.selectModel).mockRejectedValue(new ApiError(503,'Провайдер недоступен'));
  render(<Harness/>);await user.click(screen.getByRole('button',{name:'Выбрать модель: qwen-test'}));
  await user.click(await screen.findByRole('button',{name:/local-test:latest/}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Провайдер недоступен');
  expect(screen.getByRole('button',{name:'Выбрать модель: qwen-test'})).toBeInTheDocument();
});

it('refreshes another-tab conflict, keeps the menu and reports that the write did not win',async()=>{
  const user=userEvent.setup();vi.mocked(api.selectModel).mockRejectedValue(new ApiError(409,'Модель уже изменена'));
  vi.spyOn(api,'modelPreference').mockResolvedValue({...preference,selection:{provider:'aitunnel',model:'other-tab'},revision:8});
  render(<Harness/>);await user.click(screen.getByRole('button',{name:'Выбрать модель: qwen-test'}));
  await user.click(await screen.findByRole('button',{name:/local-test:latest/}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Модель уже изменена');
  expect(await screen.findByRole('button',{name:'Выбрать модель: other-tab'})).toBeInTheDocument();
});

it('closes with Escape and restores focus without changing the model',async()=>{
  const user=userEvent.setup();render(<Harness/>);const trigger=screen.getByRole('button',{name:'Выбрать модель: qwen-test'});
  await user.click(trigger);await screen.findByRole('searchbox');await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(trigger).toHaveFocus();expect(api.selectModel).not.toHaveBeenCalled();
});

it('keeps the other provider usable when the cloud catalog is unavailable',async()=>{
  const user=userEvent.setup();vi.mocked(api.models).mockResolvedValue({providers:[catalog.providers[0],{...catalog.providers[1],status:'unavailable',models:[],error_code:'MODEL_CATALOG_UNAVAILABLE'}]});
  render(<Harness/>);await user.click(screen.getByRole('button',{name:'Выбрать модель: qwen-test'}));
  expect(await screen.findByText(/Не удалось получить список/)).toBeVisible();
  expect(screen.getByRole('button',{name:/local-test:latest/})).toBeEnabled();
});

it('blocks choosing during a running response',()=>{
  render(<ChatModelPicker preference={preference} disabled onChange={()=>{}} onBusy={()=>{}}/>);
  expect(screen.getByRole('button',{name:'Выбрать модель: qwen-test'})).toBeDisabled();expect(api.models).not.toHaveBeenCalled();
});
