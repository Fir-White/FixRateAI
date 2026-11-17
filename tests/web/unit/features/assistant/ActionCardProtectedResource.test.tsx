import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {ActionCard} from '@/features/assistant/ActionCard';
import {assistantApi,type ChatAction} from '@/shared/api/assistant';

const url='/api/v1/maintenance/management/enrollment';
const record:ChatAction={action_id:'protected-action',conversation_id:'chat',turn_id:'turn',tool_name:'enrollment_create',arguments:{},payload_sha256:'a'.repeat(64),before_snapshot:null,explanation:'Создать код компании',status:'succeeded',result:{data:{protected_output:true,code_present:true,resource:{url,title:'Открыть код компании',protected:true}},verification:{status:'unverified',summary:'Откройте защищённый просмотр.'}},expires_at:'2099-01-01T00:00:00Z',created_at:'2026-11-16T00:00:00Z'};
function show(action:ChatAction=record){render(<MemoryRouter><ActionCard action={action} title="Код компании" onChanged={vi.fn()}/></MemoryRouter>);}
beforeEach(()=>vi.restoreAllMocks());

it('opens the protected current API resource after confirmation without exposing a credential',()=>{
  show();const link=screen.getByRole('link',{name:/Открыть код компании/});
  expect(link).toHaveAttribute('href',url);expect(link).toHaveAttribute('target','_blank');
  expect(link).toHaveAttribute('rel','noopener noreferrer');
  expect(link).toHaveTextContent('Защищённый просмотр');
  expect(screen.getByRole('status')).toHaveTextContent('результат требует проверки');
});

it.each(['https://external.test/code','//external.test/code','javascript:alert(1)','data:text/html,x','/settings/company','api/v1/maintenance/management/enrollment','/api/v1/../../auth/session','/api/v1/%2e%2e/%2e%2e/auth/session','/api/v1/\\external.test/code','/api/v1/maintenance/\ncode'])('rejects an unsafe resource URL %j',unsafe=>{
  show({...record,result:{data:{resource:{url:unsafe,title:'Unsafe resource',protected:true}}}});
  expect(screen.queryByRole('link',{name:/Unsafe resource/})).not.toBeInTheDocument();
});

it.each(['proposed','executing','failed','uncertain','stale','rejected'] as const)('does not offer a completed resource for %s action',status=>{
  show({...record,status});expect(screen.queryByRole('link',{name:/Открыть код компании/})).not.toBeInTheDocument();
});

it('shows the clickable protected view immediately after an actual confirmation response',async()=>{
  const pending:ChatAction={...record,status:'proposed',result:null};
  vi.spyOn(assistantApi,'confirm').mockResolvedValue(record);const user=userEvent.setup();show(pending);
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  await user.click(screen.getByRole('checkbox'));
  await user.click(screen.getByRole('button',{name:'Подтвердить и выполнить'}));
  expect(await screen.findByRole('link',{name:/Открыть код компании/})).toHaveAttribute('href',url);
  expect(assistantApi.confirm).toHaveBeenCalledExactlyOnceWith(pending);
});

it('preserves ordinary export resource rendering and treats server labels as text',()=>{
  show({...record,result:{data:{resource:{url,title:'<img src=x onerror=alert(1)>',protected:true}}}});
  expect(screen.getByRole('link',{name:/<img src=x onerror=alert\(1\)>/})).toBeVisible();
  expect(document.querySelector('img')).toBeNull();
});

it('leaves resources without the protected marker in the existing result details',()=>{
  show({...record,result:{data:{resource:{url:'/api/v1/maintenance/export.xlsx',title:'Export'}}}});
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByText('Результат действия')).toBeInTheDocument();
});
