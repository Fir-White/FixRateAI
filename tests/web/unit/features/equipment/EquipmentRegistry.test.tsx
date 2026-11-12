import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { EquipmentRegistry } from '@/features/equipment/EquipmentRegistry';
import { registryApi } from '@/shared/api/registry';
import { patternDefaults } from '@/shared/types/management';
import type { EquipmentRegistry as RegistryData } from '@/shared/types/registry';
let role = 'director';
vi.mock('@/shared/session/SessionContext',()=>({useSession:()=>({profile:{role,siteId:'site',timezone:'UTC'},switchSite:vi.fn()})}));

beforeEach(()=>{
  role='director';vi.restoreAllMocks();
  const service={code:'TO',title:'Осмотр',instructions:'По паспорту',maintenance_type:'ТО1' as const,pattern:patternDefaults('2026-11-01','day'),valid_from:'2026-11-01',valid_until:null,crew_size:1,duration_minutes:60,qualification_ids:[],checklist:[],allowed_lead_days:0,enabled:false};
  const data:RegistryData={site_id:'site',site_name:'Корпус 1',timezone:'UTC',systems:[{id:'system',code:'OLD',name:'Старая система',system_group:null,revision:1,is_active:true}],items:[{
    equipment_id:'equipment',site_id:'site',system_id:'system',equipment_type_id:null,parent_equipment_id:null,asset_code:'P-1',name:'Насос',serial_number:null,commissioned_on:null,location:null,status:'active',properties:{},revision:1,components:[],services:[
      {...service,binding_id:'known',norm_value:'4',norm_unit:'person_hour'},
      {...service,binding_id:'unknown',code:'UNKNOWN',title:'Работа без подтверждённой нормы',norm_value:'8',norm_unit:'unconfirmed'},
    ],
  }]};
  vi.spyOn(registryApi,'load').mockResolvedValue(data);
  vi.spyOn(registryApi,'sites').mockResolvedValue([{site_id:'site',name:'Корпус 1',address:null,timezone:'UTC',role:'director'}]);
});

it('keeps unclassified legacy equipment visible and exposes no director write links',async()=>{
  const user=userEvent.setup();render(<MemoryRouter><EquipmentRegistry/></MemoryRouter>);
  await user.click(await screen.findByRole('tab',{name:/Без группы/}));
  expect(screen.getByRole('link',{name:'Насос'})).toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Добавить оборудование'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Работы и регламенты'})).not.toBeInTheDocument();
  expect(screen.queryByText('Импортировать оборудование, работы и детали')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Экспорт реестра'})).toBeEnabled();
});

it('labels the known hours subtotal and never treats an unconfirmed norm as person-hours',async()=>{
  const user=userEvent.setup();render(<MemoryRouter><EquipmentRegistry/></MemoryRouter>);
  await user.click(await screen.findByRole('tab',{name:/Без группы/}));
  expect(screen.getByText('ТО1: 4 чел.-ч')).toBeInTheDocument();
  expect(screen.getByText('Известная часть; есть неподтверждённые нормы')).toBeInTheDocument();
  expect(screen.queryByText('ТО1: 12 чел.-ч')).not.toBeInTheDocument();
});
