"""Deterministic candidate model, greedy baseline and bounded CP-SAT search.

Only placement changes. Norms, assets, segment identities and locks stay frozen.
All returned variants are checked by the same validator used by manual edits.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,field
from datetime import datetime,time,timedelta,timezone
from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR
from math import ceil,floor
from threading import Thread,Event
from time import monotonic
from uuid import UUID
from zoneinfo import ZoneInfo
import json

from app.assignment.schemas import Worker
from app.assignment.selection import _merge,_subtract
from app.schemas.draft_plans import WorkOccurrence,WorkSegment,GenerationInput
from app.schemas.optimization import OptimizationOptions
from app.scheduling.draft_validator import validate,_parts,_hours,_contains,digest
from app.scheduling.planning_policy import access_intervals,intersect

MODEL_VERSION='placement-candidates-v2'
OBJECTIVE_VERSION='coverage-then-segments-then-weighted-balance-v1'
MAX_SEGMENTS=500
MAX_CANDIDATES=20000
MAX_CHOICES_PER_GROUP=512
MAX_VARIABLES=200000
UTC=timezone.utc
ZERO=Decimal(0)

class Cancelled(Exception): pass
class BudgetExceeded(Exception): pass

@dataclass
class Candidate:
    parts:list
    eligible:tuple
    forced_team:tuple=()
    @property
    def start(self): return self.parts[0][0]
    @property
    def end(self): return self.parts[-1][1]

@dataclass
class Group:
    root:WorkOccurrence
    segments:list
    fixed:bool=False
    choices:list=field(default_factory=list)


def _seconds(a,b): return int(Decimal(str((b-a).total_seconds())).to_integral_value(rounding=ROUND_CEILING))
def _span_key(s): return (s.start_at,s.end_at,tuple(sorted(s.worker_ids,key=str)))
def _known(w): return w.active and w.membership_active and w.can_execute and w.availability_data_complete and w.booking_data_complete and w.workload_data_complete


class Problem:
    def __init__(self,payload,cancel=None):
        self.started=monotonic();self.cancel=cancel or Event()
        self.options=OptimizationOptions.model_validate(payload['options'])
        self.deadline=self.started+self.options.time_limit_seconds
        from app.schemas.portfolio import planning_input
        self.request=planning_input(payload['source_snapshot']['input'])
        self.tz=ZoneInfo(payload['source_snapshot']['source']['timezone'])
        self.now=datetime.fromisoformat(payload['resources']['as_of'])
        self.cutoff=self.now+timedelta(minutes=self.options.start_buffer_minutes)
        self.roots=[WorkOccurrence.model_validate(o) for o in payload['occurrences']]
        self.original=[WorkSegment.model_validate(s) for s in payload['segments']]
        self.people=[Worker.model_validate_json(json.dumps(w)) for w in payload['resources']['workers']]
        self.people.sort(key=lambda w:str(w.worker_id));self.workers={w.worker_id:w for w in self.people}
        self.assets={UUID(k):[(datetime.fromisoformat(a).astimezone(UTC),datetime.fromisoformat(b).astimezone(UTC)) for a,b in v] for k,v in payload['resources']['equipment_bookings'].items()}
        self.unknown_assets=set(map(UUID,payload['resources']['equipment_unknown']))
        self.known=[w for w in self.people if _known(w)]
        self.free={};self.cap=defaultdict(int);self.by_day=defaultdict(int);self.worker_capacity=defaultdict(int)
        self.diagnostics=[];self.counts=Counter();self.complete=all(_known(w) for w in self.people if w.active and w.membership_active and w.can_execute)
        if self.unknown_assets&{a for r in self.roots for a in r.equipment_ids}: self.complete=False
        self.reason='finished';self.candidate_count=0;self.variable_count=0
        try:self.access=access_intervals(self.request.policy,self.request.starts_on,self.request.ends_on,self.tz)
        except ValueError:
            self.access=None;self.issue('ACCESS_TIME_UNRESOLVED','Уточните границы доступа в часовом поясе объекта')
        if self.access is None:
            self.complete=False
            self.issue('ACCESS_UNCONFIRMED','Окна доступа объекта не подтверждены; вариант не готов к публикации')
        for w in self.known:
            available=_subtract(_merge([(a.start_at.astimezone(UTC),a.end_at.astimezone(UTC)) for a in w.availability if a.status=='available']),
                [(a.start_at.astimezone(UTC),a.end_at.astimezone(UTC)) for a in w.availability if a.status=='unavailable'])
            booked=_merge([(b.start_at.astimezone(UTC),b.end_at.astimezone(UTC)) for b in w.bookings if b.blocks_time])
            free=_subtract(available,booked)
            if self.access is not None and self.request.policy.format_version==2:free=intersect(free,self.access)
            self.free[w.worker_id]=(free,[a for a,_ in free])
            raw=defaultdict(Decimal);used=defaultdict(Decimal)
            access_seconds=defaultdict(Decimal)
            for a,b in free:
                for day,left,right in _parts(a,b,self.tz):access_seconds[day]+=_hours(left,right)*3600
            for a,b in available:
                for day,left,right in _parts(a,b,self.tz):
                    if self.request.starts_on<=day<=self.request.ends_on+timedelta(days=1):
                        raw[day]+=_hours(left,right)*3600*(self.request.policy.capacity_hours_per_24h or 0)/24
            for a,b in booked:
                for day,left,right in _parts(a,b,self.tz): used[day]+=_hours(left,right)*3600
            for day,seconds in raw.items():
                capacity=max(0,int((seconds-used[day]).to_integral_value(rounding=ROUND_FLOOR)))
                if self.request.policy.format_version==2:capacity=min(capacity,int(access_seconds[day].to_integral_value(rounding=ROUND_FLOOR)))
                self.cap[w.worker_id,day]=capacity;self.by_day[day]+=capacity;self.worker_capacity[w.worker_id]+=capacity
        grouped=defaultdict(list)
        for s in self.original: grouped[s.occurrence_id].append(s)
        self.groups=[]
        for root in self.roots:
            pieces=grouped[root.occurrence_id]
            if root.interpretation=='CONTINUOUS_WORK':
                order=self._order(pieces);self.groups.append(Group(root,order))
            else:
                self.groups.extend(Group(root,[s]) for s in sorted(pieces,key=lambda s:str(s.segment_id)))
        self.groups.sort(key=lambda g:(g.root.latest_date,g.root.earliest_date,str(g.segments[0].segment_id)))
        for group in self.groups: group.fixed=any(self.frozen(s) for s in group.segments)
        if not self.complete: self.issue('RESOURCE_DATA_INCOMPLETE','Часть данных ресурсов неизвестна; поиск использует только подтверждённую доступность и не доказывает глобальную невозможность')

    def _order(self,pieces):
        remaining={s.segment_id:s for s in pieces};ordered=[]
        while remaining:
            ready=[s for s in remaining.values() if not set(s.depends_on_segment_ids)&remaining.keys()]
            if not ready: return sorted(pieces,key=lambda s:str(s.segment_id))
            for s in sorted(ready,key=lambda s:str(s.segment_id)): ordered.append(s);remaining.pop(s.segment_id)
        return ordered

    def frozen(self,s): return bool(s.start_at and (s.locked or not self.options.replan_existing))
    def tick(self):
        if self.cancel.is_set(): raise Cancelled()
        if monotonic()>=self.deadline: raise BudgetExceeded()
    def issue(self,code,message,group=None):
        self.counts[code]+=1
        if len(self.diagnostics)<25: self.diagnostics.append(dict(code=code,message=message,row_number=group.root.source_row if group else None))
    def parts_load(self,candidate):
        # A continuous group uses one crew through every adjacent part.
        result=defaultdict(int)
        for a,b in candidate.parts:
            for day,left,right in _parts(a,b,self.tz): result[day]+=_seconds(left,right)
        return result

    def team_for(self,group,parts,forced=()):
        root=group.root;left,right=parts[0][0],parts[-1][1]
        if not root.qualifications_confirmed or any(a in self.unknown_assets for s in group.segments for a in s.equipment_ids): return ()
        allowed=_merge([(w.start_at.astimezone(UTC),w.end_at.astimezone(UTC)) for w in root.allowed_intervals])
        if not _contains(allowed,[a for a,_ in allowed],left,right): return ()
        if left.astimezone(self.tz).date()<self.request.starts_on or (right-timedelta(microseconds=1)).astimezone(self.tz).date()>self.request.ends_on+timedelta(days=root.source_slot=='night'): return ()
        for segment,(a,b) in zip(group.segments,parts):
            if any(a<y and x<b for asset in segment.equipment_ids for x,y in self.assets.get(asset,())): return ()
        dummy=Candidate(parts,());daily=self.parts_load(dummy);end_day=(right-timedelta(microseconds=1)).astimezone(self.tz).date()
        eligible=[]
        for worker in self.known:
            if worker.site_id!=root.site_id or forced and worker.worker_id not in forced: continue
            intervals,starts=self.free[worker.worker_id]
            if not _contains(intervals,starts,left,right): continue
            if any(self.cap[worker.worker_id,day]<seconds for day,seconds in daily.items()): continue
            quals={q.skill_id:q for q in worker.qualifications}
            if any(skill not in quals or not quals[skill].verified_at or quals[skill].verified_at.astimezone(UTC)>left or
                (quals[skill].valid_until is not None and quals[skill].valid_until<end_day) or
                (quals[skill].validity_required and quals[skill].valid_until is None) for skill in root.qualification_ids): continue
            eligible.append(worker.worker_id)
        if len(eligible)<root.crew_size or forced and set(eligible)!=set(forced): return ()
        return tuple(sorted(eligible,key=str))

    def enumerate(self):
        for group in self.groups:
            self.tick();root=group.root
            durations=[_seconds(s.start_at,s.end_at) if self.frozen(s) else max(root.minimum_duration_minutes or 0,int((s.person_hours*60/root.crew_size).to_integral_value(rounding=ROUND_CEILING)))*60 for s in group.segments]
            offsets=[];offset=0
            for duration in durations: offsets.append(offset);offset+=duration
            forced=[(s,i) for i,s in enumerate(group.segments) if self.frozen(s)]
            forced_team=tuple(sorted(forced[0][0].worker_ids,key=str)) if forced else ()
            if forced:
                start=forced[0][0].start_at.astimezone(UTC)-timedelta(seconds=offsets[forced[0][1]])
                candidates=[start]
            else:
                candidates=set()
                for window in root.allowed_intervals:
                    left=max(window.start_at.astimezone(UTC),self.cutoff.astimezone(UTC));right=window.end_at.astimezone(UTC)
                    if right<=left: continue
                    for _,a,b in _parts(left,right,self.tz):
                        midnight=datetime.combine(a.astimezone(self.tz).date(),time.min,self.tz).astimezone(UTC)
                        step=self.options.grid_minutes*60
                        current=midnight+timedelta(seconds=ceil((a-midnight).total_seconds()/step)*step)
                        while current<min(b,right):
                            self.tick();candidates.add(current);current+=timedelta(seconds=step)
                            if len(candidates)>MAX_CHOICES_PER_GROUP*4: break
                        # Exact availability boundaries avoid missing shifts off the grid.
                        for worker in self.known:
                            for boundary,end in self.free[worker.worker_id][0]:
                                if a<=boundary<b: candidates.add(datetime.fromtimestamp(ceil(boundary.timestamp()/60)*60,UTC))
                        if len(candidates)>MAX_CHOICES_PER_GROUP*4: break
                    if len(candidates)>MAX_CHOICES_PER_GROUP*4: break
                candidates=sorted(candidates)
            # Preserve a previously valid full layout as an explicit candidate.
            originals=[]
            if all(s.start_at for s in group.segments):
                originals=[(s.start_at.astimezone(UTC),s.end_at.astimezone(UTC)) for s in group.segments]
                if any(a[1]!=b[0] for a,b in zip(originals,originals[1:])) or len({tuple(sorted(s.worker_ids,key=str)) for s in group.segments})!=1: originals=[]
            seen=set()
            for parts,team in ([(originals,tuple(sorted(group.segments[0].worker_ids,key=str)))] if originals else []):
                eligible=self.team_for(group,parts,team)
                if eligible and parts[0][0]>=self.now.astimezone(UTC):
                    group.choices.append(Candidate(parts,eligible,team));seen.add(tuple(parts));self.candidate_count+=1;self.variable_count+=len(eligible)+1
            for start in candidates:
                self.tick()
                parts=[(start+timedelta(seconds=o),start+timedelta(seconds=o+d)) for o,d in zip(offsets,durations)]
                if any(parts[i]!=(s.start_at.astimezone(UTC),s.end_at.astimezone(UTC)) or tuple(sorted(s.worker_ids,key=str))!=forced_team for s,i in forced): continue
                if tuple(parts) in seen: continue
                eligible=self.team_for(group,parts,forced_team)
                if not eligible: continue
                if len(group.choices)>=MAX_CHOICES_PER_GROUP or self.candidate_count>=MAX_CANDIDATES or self.variable_count+len(eligible)+1>MAX_VARIABLES:
                    self.complete=False;self.reason='model_limit';self.issue('MODEL_LIMIT','Часть пространства поиска не рассмотрена: сократите горизонт/состав или увеличьте шаг',group);break
                group.choices.append(Candidate(parts,eligible,forced_team));seen.add(tuple(parts));self.candidate_count+=1;self.variable_count+=len(eligible)+1
            if len(candidates)>MAX_CHOICES_PER_GROUP*4:
                self.complete=False;self.reason='model_limit';self.issue('CANDIDATE_DOMAIN_LIMIT','Превышен лимит стартовых интервалов; доказательство невозможности не выдаётся',group)
            if not group.choices:
                message='Нет общего свободного интервала, полного состава с допусками и достаточной полезной ёмкости'
                if root.splittable and len(group.segments)==1: message+='; при необходимости сначала разделите делимую работу'
                self.issue('NO_CANDIDATE',message,group)

    def report(self,segments):
        return validate(self.roots,segments,self.people,self.request.policy,self.request.starts_on,self.request.ends_on,str(self.tz),self.now,
            equipment_bookings=self.assets,equipment_unknown=self.unknown_assets,previous_segments=self.original)

    def initial(self):
        return {s.segment_id:s if self.frozen(s) or not s.start_at else s.model_copy(update={'start_at':None,'end_at':None,'worker_ids':[]}) for s in self.original}

    def materialize(self,chosen):
        result=self.initial()
        for index,(candidate,team) in chosen.items():
            for segment,(a,b) in zip(self.groups[index].segments,candidate.parts):
                result[segment.segment_id]=segment.model_copy(update={'start_at':a,'end_at':b,'worker_ids':list(team)})
        return [result[s.segment_id] for s in self.original]

    def baseline(self):
        chosen={};working=self.initial();pending=list(range(len(self.groups)))
        # Place fixed groups first. Keep a partial locked group intact if no full candidate exists.
        pending.sort(key=lambda i:(not self.groups[i].fixed,self.groups[i].root.latest_date,i))
        def fits(i,candidate,team):
            group=self.groups[i];own={s.segment_id for s in group.segments};others=[s for k,s in working.items() if k not in own and s.start_at]
            daily=self.parts_load(candidate)
            for worker in team:
                for day,seconds in daily.items():
                    used=sum(_seconds(a,b) for s in others if worker in s.worker_ids for d,a,b in _parts(s.start_at,s.end_at,self.tz) if d==day)
                    if used+seconds>self.cap[worker,day]: return False
                if any(worker in s.worker_ids and s.start_at<candidate.end and candidate.start<s.end_at for s in others): return False
            for segment,(a,b) in zip(group.segments,candidate.parts):
                if any(set(segment.equipment_ids)&set(s.equipment_ids) and a<s.end_at and s.start_at<b for s in others): return False
                for identity in segment.depends_on_segment_ids:
                    predecessor=working.get(identity)
                    if identity in own: continue
                    if not predecessor or not predecessor.end_at or predecessor.end_at>a: return False
                if any(segment.segment_id in s.depends_on_segment_ids and s.start_at<b for s in others): return False
            return True
        for _ in range(len(pending)+1):
            progress=False
            for index in list(pending):
                self.tick();group=self.groups[index]
                for candidate in group.choices:
                    self.tick()
                    team=[]
                    # Greedy team selection is deterministic; CP-SAT explores other teams.
                    for identity in candidate.eligible:
                        if fits(index,candidate,[identity]): team.append(identity)
                        if len(team)==group.root.crew_size: break
                    if len(team)==group.root.crew_size and fits(index,candidate,team):
                        chosen[index]=(candidate,tuple(team))
                        for s,(a,b) in zip(group.segments,candidate.parts): working[s.segment_id]=s.model_copy(update={'start_at':a,'end_at':b,'worker_ids':team})
                        progress=True;break
                pending.remove(index) if index in chosen else None
            if not progress: break
        return self.materialize(chosen)

    def metrics(self,segments,report):
        by_root=defaultdict(list);worker_load=defaultdict(Decimal)
        for s in segments:
            by_root[s.occurrence_id].append(s)
            if s.start_at:
                for w in s.worker_ids: worker_load[w]+=_hours(s.start_at,s.end_at)*3600
        indexed={s.segment_id:s for s in segments}
        covered=sum(all(s.start_at and len(s.worker_ids)==r.crew_size and all(i in indexed and indexed[i].end_at and indexed[i].end_at<=s.start_at for i in s.depends_on_segment_ids)
            for s in by_root[r.occurrence_id]) and bool(by_root[r.occurrence_id]) for r in self.roots)
        ratios=[d.reserved_person_hours/d.available_person_hours for d in report.days if d.available_person_hours and d.available_person_hours>0]
        mean=sum(ratios,ZERO)/len(ratios) if ratios else ZERO
        spread=[worker_load[w]/capacity for w,capacity in self.worker_capacity.items() if capacity>0]
        capacity=sum(self.worker_capacity.values())
        originals={s.segment_id:s for s in self.original}
        return dict(total_occurrences=len(self.roots),covered_occurrences=covered,mandatory_work_coverage=Decimal(covered)/len(self.roots) if self.roots else Decimal(1),
            total_person_hours=report.total_person_hours,placed_person_hours=report.placed_person_hours,unplaced_segments=report.unplaced_segments,
            peak_daily_person_hours=max((d.planned_person_hours for d in report.days),default=ZERO),
            peak_daily_utilization=max(ratios,default=ZERO) if self.complete else None,
            daily_load_balance=sum(((v-mean)**2 for v in ratios),ZERO)/len(ratios) if ratios and self.complete else None,
            staff_utilization=sum(worker_load.values(),ZERO)/capacity if capacity and self.complete else None,
            fairness_spread=max(spread,default=ZERO)-min(spread,default=ZERO) if self.complete else None,
            changed_assignments=sum(bool(originals[s.segment_id].start_at) and _span_key(originals[s.segment_id])!=_span_key(s) for s in segments),
            unfilled_slots=sum(r.crew_size for r in self.roots for s in by_root[r.occurrence_id] if not s.start_at))

    def variant(self,kind,segments,status,seconds,objective=None,bound=None):
        report=self.report(segments);metrics=self.metrics(segments,report)
        fully=metrics['covered_occurrences']==len(self.roots) and report.status=='valid'
        return dict(kind=kind,method_version=MODEL_VERSION if kind=='optimized' else 'earliest-due-first-v1',solver_status=status,
            coverage_status='FEASIBLE' if fully else 'INFEASIBLE' if kind=='optimized' and status=='OPTIMAL' and self.complete else 'UNKNOWN',
            optimality_proven=kind=='optimized' and status=='OPTIMAL' and self.complete,model_complete=self.complete,
            duration_seconds=seconds,objective_value=objective,objective_bound=bound,metrics=metrics,validation=report.model_dump(mode='json'),
            applicable=report.status!='invalid' and any(_span_key(a)!=_span_key(b) for a,b in zip(self.original,segments)))

    def solve(self,baseline):
        from ortools.sat.python import cp_model
        model=cp_model.CpModel();xs={};ys={};presences={};part_start={};part_end={};worker_intervals=defaultdict(list);asset_intervals=defaultdict(list)
        loads=defaultdict(list);day_load=defaultdict(list);worker_load=defaultdict(list);changes=[];lateness=[]
        origin=datetime.combine(self.request.starts_on,time.min,self.tz).astimezone(UTC)
        def stamp(value): return floor((value-origin).total_seconds())
        def finish(value): return ceil((value-origin).total_seconds())
        for i,group in enumerate(self.groups):
            self.tick();p=model.new_bool_var(f'g{i}');presences[i]=p
            choices=[]
            for j,c in enumerate(group.choices):
                self.tick()
                x=model.new_bool_var(f'x{i}_{j}');xs[i,j]=x;choices.append(x)
                start,end=stamp(c.start),finish(c.end);duration=end-start
                crew=[];daily=self.parts_load(c)
                for worker in c.eligible:
                    y=model.new_bool_var(f'y{i}_{j}_{worker}');ys[i,j,worker]=y;model.add(y<=x);crew.append(y)
                    worker_intervals[worker].append(model.new_optional_fixed_size_interval_var(start,duration,y,f'wi{i}_{j}_{worker}'))
                    for day,seconds in daily.items(): loads[worker,day].append(seconds*y)
                    worker_load[worker].append(sum(daily.values())*y)
                model.add(sum(crew)==group.root.crew_size*x)
                for part_index,(segment,(a,b)) in enumerate(zip(group.segments,c.parts)):
                    for asset in segment.equipment_ids:
                        asset_intervals[asset].append(model.new_optional_fixed_size_interval_var(stamp(a),finish(b)-stamp(a),x,f'ai{i}_{j}_{part_index}_{asset}'))
                for day,seconds in daily.items(): day_load[day].append(seconds*group.root.crew_size*x)
                lateness.append(max(0,(c.start.astimezone(self.tz).date()-group.root.earliest_date).days)*x)
                if any(s.start_at for s in group.segments):
                    same=all(s.start_at and (s.start_at.astimezone(UTC),s.end_at.astimezone(UTC))==part for s,part in zip(group.segments,c.parts))
                    if same:
                        original=set(group.segments[0].worker_ids)
                        equal=model.new_bool_var(f'equal{i}_{j}')
                        terms=[ys[i,j,w] for w in original if (i,j,w) in ys]
                        if len(terms)==group.root.crew_size:
                            model.add(equal<=x)
                            for y in terms: model.add(equal<=y)
                            model.add(equal>=sum(terms)-group.root.crew_size+1)
                            changes.append(-equal)
            model.add(sum(choices)==p)
            if group.fixed and group.choices: model.add(p==1)
            if group.fixed and not group.choices:
                for s in group.segments:
                    if not self.frozen(s): continue
                    a,b=stamp(s.start_at),finish(s.end_at)
                    for worker in s.worker_ids:
                        worker_intervals[worker].append(model.new_fixed_size_interval_var(a,b-a,f'fixedw{s.segment_id}_{worker}'))
                        for day,left,right in _parts(s.start_at,s.end_at,self.tz): loads[worker,day].append(_seconds(left,right))
                        worker_load[worker].append(b-a)
                    for asset in s.equipment_ids: asset_intervals[asset].append(model.new_fixed_size_interval_var(a,b-a,f'fixeda{s.segment_id}_{asset}'))
                    for day,left,right in _parts(s.start_at,s.end_at,self.tz): day_load[day].append(_seconds(left,right)*len(s.worker_ids))
            for k,s in enumerate(group.segments):
                part_start[s.segment_id]=sum(stamp(c.parts[k][0])*xs[i,j] for j,c in enumerate(group.choices))
                part_end[s.segment_id]=sum(finish(c.parts[k][1])*xs[i,j] for j,c in enumerate(group.choices))
                if group.fixed and not group.choices and self.frozen(s):
                    part_start[s.segment_id]=stamp(s.start_at);part_end[s.segment_id]=finish(s.end_at)
        for intervals in worker_intervals.values(): model.add_no_overlap(intervals)
        for intervals in asset_intervals.values(): model.add_no_overlap(intervals)
        for key,terms in loads.items(): model.add(sum(terms)<=self.cap[key])
        owner={s.segment_id:i for i,g in enumerate(self.groups) for s in g.segments}
        segment_presence={s.segment_id:(1 if g.fixed and not g.choices and self.frozen(s) else presences[i]) for i,g in enumerate(self.groups) for s in g.segments}
        for s in self.original:
            for predecessor in s.depends_on_segment_ids:
                if predecessor not in part_end: continue
                p,q=segment_presence[s.segment_id],segment_presence[predecessor]
                model.add(p<=q)
                if owner[s.segment_id]!=owner[predecessor]: model.add(part_start[s.segment_id]>=part_end[predecessor]).only_enforce_if([p,q])
        root_full=[]
        for root in self.roots:
            group_ids=[i for i,g in enumerate(self.groups) if g.root.occurrence_id==root.occurrence_id]
            r=model.new_bool_var(f'root{root.occurrence_id}');ps=[presences[i] for i in group_ids]
            for p in ps: model.add(r<=p)
            model.add(r>=sum(ps)-len(ps)+1);root_full.append(r)
        ratios=[]
        for day,capacity in self.by_day.items():
            if capacity<=0: continue
            ratio=model.new_int_var(0,1000,f'day{day}');model.add(sum(day_load[day])*1000<=ratio*capacity);ratios.append(ratio)
        peak=model.new_int_var(0,1000,'peak');model.add_max_equality(peak,ratios or [0])
        worker_ratios=[]
        for worker,capacity in self.worker_capacity.items():
            if capacity<=0: continue
            ratio=model.new_int_var(0,1000,f'load{worker}')
            model.add(sum(worker_load[worker])*1000<=ratio*capacity)
            model.add(sum(worker_load[worker])*1000>=(ratio-1)*capacity+1).only_enforce_if(model.new_constant(1))
            worker_ratios.append(ratio)
        high=model.new_int_var(0,1000,'high');low=model.new_int_var(0,1000,'low')
        model.add_max_equality(high,worker_ratios or [0]);model.add_min_equality(low,worker_ratios or [0])
        w=self.options.weights;n=len(self.original);horizon=367
        secondary_bound=1000*(w.daily_peak+w.worker_spread)+n*w.changes+n*horizon*w.earliness
        segment_weight=secondary_bound+1;root_weight=(n+1)*segment_weight
        placed_count=sum(segment_presence.values())
        model.maximize(sum(root_full)*root_weight+placed_count*segment_weight-
            (peak*w.daily_peak+(high-low)*w.worker_spread+sum(changes)*w.changes+sum(lateness)*w.earliness))
        solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=max(.01,self.deadline-monotonic())
        solver.parameters.num_search_workers=1;solver.parameters.random_seed=self.options.random_seed
        stop=Event()
        def watch():
            while not stop.wait(.05):
                if self.cancel.is_set(): solver.stop_search();return
        watcher=Thread(target=watch,daemon=True);watcher.start()
        start=monotonic()
        try: status=solver.solve(model)
        finally: stop.set();watcher.join(timeout=.2)
        if self.cancel.is_set(): raise Cancelled()
        name=solver.status_name(status)
        if name not in ('OPTIMAL','FEASIBLE'): return None,name,monotonic()-start,None,None
        chosen={}
        for (i,j),x in xs.items():
            if solver.value(x): chosen[i]=(self.groups[i].choices[j],tuple(w for w in self.groups[i].choices[j].eligible if solver.value(ys[i,j,w])))
        return self.materialize(chosen),name,monotonic()-start,int(round(solver.objective_value)),solver.best_objective_bound


def calculate(payload,cancel=None):
    p=Problem(payload,cancel);baseline=None;optimized=None;baseline_segments=None;optimized_segments=None
    report=p.report(p.original)
    input_codes={'HOURS_NOT_CONSERVED','DUPLICATE_SEGMENT','UNKNOWN_OCCURRENCE','DEPENDENCY_CYCLE','DEPENDENCY_MISSING','CAPACITY_UNCONFIRMED','QUALIFICATIONS_UNCONFIRMED','SEGMENTATION_FORBIDDEN','ASSET_COVERAGE','BATCH_HOURS_NOT_CONSERVED','BATCH_UNIT_REQUIRED','FOREIGN_ASSET','SEGMENT_TOO_SMALL','ACCESS_UNCONFIRMED','ACCESS_TIME_UNRESOLVED'}
    if set(report.issue_counts)&input_codes or len(p.original)>MAX_SEGMENTS:
        p.complete=False;p.reason='needs_input'
        for issue in report.issues:
            if issue.code in input_codes: p.issue(issue.code,issue.message)
        if len(p.original)>MAX_SEGMENTS: p.issue('SEGMENT_LIMIT','Автоматический расчёт ограничен 500 сегментами; сократите сценарий')
    else:
        try:
            p.enumerate();started=monotonic();baseline_segments=p.baseline()
            baseline=p.variant('baseline',baseline_segments,'HEURISTIC',monotonic()-started)
            if monotonic()<p.deadline:
                try:
                    result,status,seconds,objective,bound=p.solve(baseline_segments)
                    if result is not None:
                        if status=='FEASIBLE': p.reason='time_limit'
                        variant=p.variant('optimized',result,status,seconds,objective,bound)
                        # No native solver result bypasses the canonical validator.
                        if variant['validation']['status']!='invalid': optimized_segments=result;optimized=variant
                        else: p.complete=False;p.issue('VALIDATOR_REJECTED','Кандидат решателя отклонён общим валидатором; его применение недоступно')
                    elif status=='INFEASIBLE': p.issue('MODEL_INFEASIBLE','Закрепления или зависимости несовместимы в выбранной модели')
                    else: p.reason='time_limit';p.issue('NO_SOLUTION_BEFORE_LIMIT','До лимита времени допустимый кандидат не найден; это не доказательство невозможности')
                except ImportError:
                    p.reason='solver_unavailable';p.complete=False;p.issue('SOLVER_UNAVAILABLE','Решатель недоступен; базовый и ручной режимы сохраняются')
            else: p.reason='time_limit'
        except BudgetExceeded:
            p.complete=False;p.reason='time_limit';p.issue('TIME_LIMIT','Достигнут общий лимит расчёта; доказательство оптимальности не выдаётся')
    result=dict(model_version=MODEL_VERSION,objective_version=OBJECTIVE_VERSION,candidate_count=p.candidate_count,variable_count=p.variable_count,
        model_complete=p.complete,completion_reason=p.reason,diagnostics=p.diagnostics,diagnostic_counts=dict(p.counts),baseline=baseline,optimized=optimized,ready_for_real_plan=False)
    return dict(result=result,baseline_segments=[s.model_dump(mode='json') for s in baseline_segments] if baseline_segments is not None else None,
        optimized_segments=[s.model_dump(mode='json') for s in optimized_segments] if optimized_segments is not None else None)
