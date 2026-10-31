import { Link } from "react-router-dom";
import type { Equipment } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import {
  EquipmentStateBadge,
  OriginBadge,
} from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";
import { Table, Td, Th, Tr } from "@/shared/ui/Table";

export function EquipmentTable({ items }: { items: Equipment[] }) {
  return (
    <Table label="Реестр оборудования" minWidth={760}>
      <thead>
        <tr>
          <Th>Оборудование</Th>
          <Th>Инвентарный номер</Th>
          <Th>Состояние</Th>
          <Th>Следующее ТО</Th>
          <Th>Происхождение</Th>
          <Th className="text-right">
            <span className="sr-only">Действия</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {items.map((equipment) => (
          <Tr key={equipment.id}>
            <Td>
              <p className="font-semibold text-ink">{equipment.name}</p>
              <p className="mt-1 text-xs text-muted">
                {equipment.equipmentType} · {equipment.location}
              </p>
            </Td>
            <Td className="font-mono text-xs text-ink-soft">
              {equipment.inventoryCode}
            </Td>
            <Td>
              <EquipmentStateBadge state={equipment.state} />
            </Td>
            <Td>{formatDate(equipment.nextDueDate)}</Td>
            <Td>
              <OriginBadge origin={equipment.dataOrigin} />
            </Td>
            <Td className="text-right">
              <Link
                to={`/equipment/${equipment.id}`}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent transition-colors hover:bg-accent/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Открыть
                <Icon name="chevron" size={15} />
              </Link>
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}
