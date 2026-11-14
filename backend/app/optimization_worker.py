"""Persistent queue, one global CPU slot and an isolated cancellable child.

The child receives JSON only and never receives a Session or database credentials.
"""
import json
import logging
import multiprocessing
import queue
from threading import Thread,Event
from time import monotonic
from uuid import uuid4
from sqlalchemy import text

logger=logging.getLogger('app.optimization')
SLOT=268413094625718


def child_calculate(payload,cancel,output):
    from app.scheduling.optimization import calculate,Cancelled
    try: output.put(dict(ok=True,data=calculate(payload,cancel)))
    except Cancelled: output.put(dict(ok=False,error='CANCELLED'))
    except Exception as error:
        logger.error('Optimization child failed: %s',type(error).__name__)
        output.put(dict(ok=False,error='CALCULATION_FAILED'))


class OptimizationManager:
    def __init__(self,engine):
        self.engine=engine;self.stop_event=Event();self.wake_event=Event();self.thread=None

    def start(self):
        self.thread=Thread(target=self._loop,name='draft-optimization-coordinator',daemon=True);self.thread.start()

    def alive(self): return self.thread is not None and self.thread.is_alive() and not self.stop_event.is_set()
    def wake(self): self.wake_event.set()
    def stop(self):
        self.stop_event.set();self.wake_event.set()
        if self.thread: self.thread.join(timeout=6)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                with self.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as slot:
                    if slot.scalar(text('SELECT pg_try_advisory_lock(:key)'),dict(key=SLOT)):
                        try:
                            # A held global slot proves no other coordinator owns a running job.
                            with self.engine.begin() as conn:
                                conn.execute(text("UPDATE draft_optimization_runs SET state=CASE WHEN state='cancel_requested' THEN 'cancelled' ELSE 'failed' END,error_code=CASE WHEN state='cancel_requested' THEN NULL ELSE 'WORKER_LOST' END,finished_at=now() WHERE state IN ('running','cancel_requested')"))
                                row=conn.execute(text("SELECT run_id,input_snapshot,options FROM draft_optimization_runs WHERE state='queued' ORDER BY created_at,run_id FOR UPDATE SKIP LOCKED LIMIT 1")).mappings().first()
                                if row:
                                    token=uuid4()
                                    conn.execute(text("UPDATE draft_optimization_runs SET state='running',started_at=now(),lease_token=:lease WHERE run_id=:id"),dict(id=row['run_id'],lease=token))
                            if row: self._execute(dict(row),token)
                        finally: slot.execute(text('SELECT pg_advisory_unlock(:key)'),dict(key=SLOT))
            except Exception as error:
                logger.error('Optimization coordinator unavailable: %s',type(error).__name__)
            self.wake_event.wait(.35);self.wake_event.clear()

    def _execute(self,row,lease):
        context=multiprocessing.get_context('spawn');cancel=context.Event();output=context.Queue(maxsize=1)
        process=context.Process(target=child_calculate,args=(row['input_snapshot'],cancel,output),daemon=True)
        process.start();began=monotonic();message=None;stopped=None;error=None
        try:
            while True:
                if self.stop_event.is_set(): error='SERVICE_RESTART';cancel.set();stopped=stopped or monotonic()
                with self.engine.connect() as conn:
                    state=conn.scalar(text('SELECT state FROM draft_optimization_runs WHERE run_id=:id AND lease_token=:lease'),dict(id=row['run_id'],lease=lease))
                if state in ('cancel_requested','cancelled') or state is None:
                    cancel.set();stopped=stopped or monotonic()
                if monotonic()-began>row['options']['time_limit_seconds']+10:
                    error='WALL_TIME_LIMIT';cancel.set();stopped=stopped or monotonic()
                try:
                    message=output.get(timeout=.15);break
                except queue.Empty: pass
                if not process.is_alive(): error=error or 'WORKER_EXITED';break
                if stopped and monotonic()-stopped>1.5: break
            if process.is_alive():
                process.join(timeout=.4)
                if process.is_alive(): process.terminate()
            process.join(timeout=2)
            with self.engine.begin() as conn:
                current=conn.execute(text('SELECT state FROM draft_optimization_runs WHERE run_id=:id AND lease_token=:lease FOR UPDATE'),dict(id=row['run_id'],lease=lease)).scalar()
                if current is None: return
                params=dict(id=row['run_id'],lease=lease)
                if current=='cancel_requested':
                    conn.execute(text("UPDATE draft_optimization_runs SET state='cancelled',finished_at=now(),error_code=NULL WHERE run_id=:id AND lease_token=:lease"),params)
                elif current=='running' and message and message.get('ok') and error is None:
                    data=message['data']
                    conn.execute(text("""UPDATE draft_optimization_runs SET state='succeeded',finished_at=now(),
                        result=CAST(:result AS jsonb),baseline_segments=CAST(:baseline AS jsonb),optimized_segments=CAST(:optimized AS jsonb)
                        WHERE run_id=:id AND lease_token=:lease AND state='running'"""),dict(params,
                        result=json.dumps(data['result'],default=str),
                        baseline=json.dumps(data['baseline_segments']) if data['baseline_segments'] is not None else None,
                        optimized=json.dumps(data['optimized_segments']) if data['optimized_segments'] is not None else None))
                elif current=='running':
                    conn.execute(text("UPDATE draft_optimization_runs SET state='failed',finished_at=now(),error_code=:error WHERE run_id=:id AND lease_token=:lease"),dict(params,error=error or (message or {}).get('error','CALCULATION_FAILED')))
        finally:
            if process.is_alive(): process.terminate();process.join(timeout=2)
            output.close()
