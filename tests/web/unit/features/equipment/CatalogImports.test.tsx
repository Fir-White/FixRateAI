import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CatalogImports } from '@/features/equipment/CatalogImports';
import { catalogImportsApi as api, type CatalogOperation, type CatalogSummary } from '@/shared/api/catalogImports';

const summary:CatalogSummary={operation_count:217,group_count:17,top_level_group_count:16,maintenance_types:{ТО1:38,ТО2:46,'ТО2*':5,ТО3:113,ТОр:15},empty_duration_count:217,mark_count:1275,readiness_counts:{NEEDS_SEMANTICS:217,NEEDS_DURATION:217,NEEDS_ASSET_BINDING:217,NEEDS_POLICY:217},ready_count:0,ready_for_real_plan:false,issue_count:1};
const op=(row:number):CatalogOperation=>({row,code:'1.4',title:`Операция ${row}`,maintenance_type:'ТО2',frequency_raw:'1/мес',group_id:'group',quality_flags:['NEEDS_SEMANTICS','NEEDS_DURATION','NEEDS_ASSET_BINDING','NEEDS_POLICY'],interpretation:'UNKNOWN',mark_count:10,source_cells:{B:`B${row}`},ready_for_real_plan:false});
const metadata={import_id:'draft',filename:'anonymous.xlsx',source_sha256:'a'.repeat(64),parser_version:'hvac-catalog-v1',status:'draft' as const,created_at:'2026-11-13T12:00:00Z',summary};
const groups=[{id:'group',code:'1',title:'Раздел',parent_id:null,row:4}];
beforeEach(()=>{
  vi.restoreAllMocks();
  vi.spyOn(api,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(api,'preview').mockResolvedValue({format:'hvac_catalog',preview_token:'token',can_save_draft:true,source_sha256:'a'.repeat(64),summary,groups,issues:[{code:'NON_NUMERIC_LABOR',sheet:'Лист2',cell:'I6',message:'Текст вместо часов'}],operations:[op(8)],total:217,sheet2_diagnostic:[]});
  vi.spyOn(api,'save').mockResolvedValue({import_id:'draft',already_saved:false,summary});
  vi.spyOn(api,'detail').mockResolvedValue({...metadata,groups,issues:[],sheet2_diagnostic:[],header_context:[]});
  vi.spyOn(api,'operations').mockImplementation(async(_id,offset,q)=>({items:[op(q?216:offset+8)],total:q?1:217}));
  vi.spyOn(api,'operation').mockResolvedValue({...op(8),raw_cells:{E:{address:'E8',present:true,text:'',raw_value:'',cell_type:'n',style:null,formula:null}},calendar_marks:[{address:'H8',day:1,present:true,text:'ТО2',raw_value:'ТО2',cell_type:'s',style:null,formula:null}]});
});

it('previews unknown norms, saves only by explicit action and opens the saved source',async()=>{
  const user=userEvent.setup();render(<CatalogImports mayImport/>);
  await user.upload(screen.getByLabelText('Excel каталога СВиК'),new File(['fixture'],'anonymous.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
  await user.click(screen.getByRole('button',{name:'Проверить каталог'}));
  expect(await screen.findByText(/Нормы времени отсутствуют/)).toHaveTextContent('217');
  expect(screen.getByText(/Лист2!I6/)).toBeVisible();
  expect(api.save).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Сохранить каталог-черновик'}));
  expect(await screen.findByRole('link',{name:'Скачать исходный Excel'})).toHaveAttribute('href','/api/v1/maintenance/catalog-imports/draft/source');
  await user.click(await screen.findByRole('button',{name:'1.4 · Операция 8'}));
  expect(await screen.findByRole('dialog',{name:'Исходная строка каталога'})).toHaveTextContent('Пустая ячейка');
  expect(screen.getByRole('dialog')).toHaveTextContent('Смысл отметок не подтверждён');
});

it('searches and paginates saved operations through bounded API reads',async()=>{
  const user=userEvent.setup();vi.mocked(api.list).mockResolvedValue({items:[metadata],total:1});
  render(<CatalogImports mayImport={false}/>);
  await user.click(await screen.findByRole('button',{name:/anonymous.xlsx/}));
  await user.click(await screen.findByRole('button',{name:'Следующие 25'}));
  await waitFor(()=>expect(api.operations).toHaveBeenCalledWith('draft',25,'','',''));
  await user.type(screen.getByRole('textbox',{name:'Поиск операций каталога'}),'0216');
  await waitFor(()=>expect(api.operations).toHaveBeenLastCalledWith('draft',0,'0216','',''));
  expect(await screen.findByRole('button',{name:'1.4 · Операция 216'})).toBeVisible();
  expect(screen.queryByLabelText('Excel каталога СВиК')).not.toBeInTheDocument();
  expect(api.save).not.toHaveBeenCalled();
});

it('shows preview errors and exposes no save command on failure',async()=>{
  vi.mocked(api.preview).mockRejectedValue(new Error('Неизвестная структура Excel'));
  const user=userEvent.setup();render(<CatalogImports mayImport/>);
  await user.upload(screen.getByLabelText('Excel каталога СВиК'),new File(['invalid'],'invalid.xlsx'));
  await user.click(screen.getByRole('button',{name:'Проверить каталог'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Неизвестная структура Excel');
  expect(screen.queryByRole('button',{name:'Сохранить каталог-черновик'})).not.toBeInTheDocument();
});
