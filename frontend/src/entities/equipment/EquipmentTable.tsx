import { Link } from "react-router-dom";
import type { Equipment } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import { EquipmentStateBadge, OriginBadge } from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";
export function EquipmentTable({items}:{items:Equipment[]}){
 return <div className="equipment-register"><table aria-label="Реестр оборудования"><thead><tr><th scope="col">Оборудование / расположение</th><th scope="col">Инвентарный номер</th><th scope="col">Состояние</th><th scope="col">Следующее ТО</th><th scope="col"><span className="sr-only">Открыть</span></th></tr></thead><tbody>{items.map(equipment=><tr key={equipment.id}><td className="equipment-register-name"><Link to={`/equipment/${equipment.id}`}>{equipment.name}</Link><p>{equipment.equipmentType} · {equipment.location}</p><OriginBadge origin={equipment.dataOrigin}/></td><td data-label="Инвентарный номер" className="font-mono">{equipment.inventoryCode}</td><td data-label="Состояние"><EquipmentStateBadge state={equipment.state}/></td><td data-label="Следующее ТО"><strong>{formatDate(equipment.nextDueDate)}</strong>{!equipment.nextDueDate&&<small>Дата не определена</small>}</td><td className="equipment-register-action"><Link to={`/equipment/${equipment.id}`} aria-label={`Открыть ${equipment.name}`}><span>Паспорт</span><Icon name="chevron" size={17}/></Link></td></tr>)}</tbody></table></div>;
}
