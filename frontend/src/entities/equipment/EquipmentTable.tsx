import { Link } from "react-router-dom";
import type { Equipment } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import {
  EquipmentStateBadge,
  OriginBadge,
} from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";

export function EquipmentTable({ items }: { items: Equipment[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-left">
        <thead>
          <tr className="border-b border-slate-100 text-xs font-bold tracking-wide text-slate-500 uppercase">
            <th className="px-5 py-3 sm:px-6">Оборудование</th>
            <th className="px-4 py-3">Инвентарный номер</th>
            <th className="px-4 py-3">Состояние</th>
            <th className="px-4 py-3">Следующее ТО</th>
            <th className="px-4 py-3">Происхождение</th>
            <th className="px-5 py-3 sm:px-6" />
          </tr>
        </thead>
        <tbody>
          {items.map((equipment) => (
            <tr
              key={equipment.id}
              className="group border-b border-slate-100 last:border-0 hover:bg-slate-50/70"
            >
              <td className="px-5 py-4 sm:px-6">
                <p className="font-semibold text-slate-900">{equipment.name}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {equipment.equipmentType} · {equipment.location}
                </p>
              </td>
              <td className="px-4 py-4 font-mono text-sm text-slate-700">
                {equipment.inventoryCode}
              </td>
              <td className="px-4 py-4">
                <EquipmentStateBadge state={equipment.state} />
              </td>
              <td className="px-4 py-4 text-sm text-slate-700">
                {formatDate(equipment.nextDueDate)}
              </td>
              <td className="px-4 py-4">
                <OriginBadge origin={equipment.dataOrigin} />
              </td>
              <td className="px-5 py-4 text-right sm:px-6">
                <Link
                  to={`/equipment/${equipment.id}`}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
                >
                  Открыть
                  <Icon name="chevron" size={16} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
