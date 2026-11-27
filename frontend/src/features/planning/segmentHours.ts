/** Keep Decimal(…,3) effort exact even beyond Number.MAX_SAFE_INTEGER. */
export function splitPersonHours(value:string,count:number):string[] {
  if(!Number.isInteger(count)||count<2||count>25)throw new Error('Выберите от 2 до 25 частей');
  const match=/^(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(value);
  if(!match)throw new Error('Не удалось прочитать подтверждённую норму');
  const digits=BigInt(match[1]+(match[2]??'')),scale=3+Number(match[3]??0)-(match[2]?.length??0);
  if(Math.abs(scale)>30)throw new Error('Норма вне допустимой точности');
  const units=scale>=0?digits*10n**BigInt(scale):digits/10n**BigInt(-scale);
  if(scale<0&&digits%10n**BigInt(-scale)!==0n)throw new Error('Норма требует более трёх знаков после запятой');
  const portion=units/BigInt(count);if(portion===0n)throw new Error('Норма слишком мала для такого числа частей');
  return Array.from({length:count},(_,index)=>{const part=index===count-1?units-portion*BigInt(count-1):portion;return `${part/1000n}.${String(part%1000n).padStart(3,'0')}`;});
}
