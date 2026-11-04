import { Link } from "react-router-dom";
import { PageHeader } from "./PageHeader";
import { Icon } from "./Icon";
import { buttonClassName } from "./Button";
/** Deliberately no fixtures for editable server-managed entities. */
export function ConnectionRequired({title,description,capabilities,backTo="/equipment",backLabel="Открыть оборудование"}:{title:string;description:string;capabilities:string[];backTo?:string;backLabel?:string}) {
 return <div className="space-y-6"><PageHeader title={title} eyebrow="Настройки / DEMO" description={description}/><section className="connection-required"><div className="connection-symbol"><Icon name="equipment" size={30}/></div><div><span className="ops-kicker">Демонстрационный просмотр</span><h2>Для изменений нужен рабочий API</h2><p>Этот раздел подключён к серверным контрактам, но не имитирует сохранение данных в деморежиме.</p><ul>{capabilities.map(item=><li key={item}><Icon name="chevron" size={14}/>{item}</li>)}</ul><Link to={backTo} className={buttonClassName("secondary")}>{backLabel}<Icon name="chevron" size={16}/></Link></div></section><p className="text-xs leading-6 text-muted">Для интеграционного режима запустите frontend без VITE_DEMO_MODE=true и подключите исходный backend. Подробности — в README.</p></div>;
}
