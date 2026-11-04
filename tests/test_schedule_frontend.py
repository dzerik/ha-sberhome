"""Run the shipped schedule helpers and modal handlers, not a copy of their logic."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.intents.test_schedules import INVALID_RULES, RULE
from tests.test_www_frontend import NODE, _prepare_intent_modal, requires_node


@requires_node
def test_schedule_editor_preserves_opaque_rules_and_validates_drafts(tmp_path: Path):
    _prepare_intent_modal(tmp_path)
    script = """
import assert from 'node:assert/strict';
import {parseSchedule,buildSchedule,editableSchedule,scheduleError} from './schedules.js';
const defined = {};
globalThis.customElements = {define:(name,cls)=>defined[name]=cls,get:()=>undefined};
globalThis.CustomEvent = class {};
await import('./components/sberhome-intent-modal.js?v=schedules');
const rule=RULE;
for(const invalid of INVALID_RULES) assert.equal(parseSchedule(invalid),null,JSON.stringify(invalid));
assert.equal(parseSchedule(rule,'UTC'),null);
assert.equal(parseSchedule(rule).start,'20300115T080000');
assert.equal(buildSchedule([],9,0,'Europe/Moscow'),null);
for(const [days,hour,minute,zone,start] of [
  [['MO','MO'],9,0,'Europe/Moscow',null], [['XX'],9,0,'Europe/Moscow',null],
  [['MO'],24,0,'Europe/Moscow',null], [['MO'],9,60,'Europe/Moscow',null],
  [['MO'],-1,0,'Europe/Moscow',null], [['MO'],9,-1,'Europe/Moscow',null],
  [['MO'],9,0,'Invalid/Zone',null], [['MO'],9,0,'Europe/Moscow','20300230T090000'],
]) assert.equal(buildSchedule(days,hour,minute,zone,start),null);
assert.ok(parseSchedule(buildSchedule(['MO'],9,0,'Europe/Moscow')));
const raw={type:'TIME',time_data:{execute_at:null,rrule:rule},device_data:null};
const trigger={type:'time',data:{rrule:rule,_raw:raw}};
function modal(triggers=[trigger],phrases=['проверка'],language='ru') {
  const m=new defined['sberhome-intent-modal']();
  m.intent={id:'scene',name:'Проверка',enabled:true,is_ha_managed:true,phrases,
    triggers:structuredClone(triggers),raw_extras:{timezone:'Europe/Moscow'},
    actions:[{type:'scenario_status',data:{scenario_id:'target',active:true}}]};
  m.hass={language,callWS:async(payload)=>{m.sent=structuredClone(payload);return {};}};
  m.willUpdate(new Map([['intent',null]]));return m;
}
const m=modal(),snapshot=structuredClone(m.intent);
m._onScheduleChange(0,{time:'10:25'});
assert.equal(parseSchedule(m._draft.triggers[0].data.rrule).start,'20300115T080000');
assert.equal(parseSchedule(m._draft.triggers[0].data.rrule).hour,10);
assert.equal(m._validate(),null);
await m._onSave();
assert.equal(m.sent.type,'sberhome/intents/update');
assert.deepEqual(m.sent.spec.triggers[0].data._raw,raw);
assert.deepEqual(m.intent,snapshot);
const invalid=modal();
invalid._onScheduleChange(0,{days:[]});
assert.match(invalid._validate(),/день/);
await invalid._onSave();assert.equal(invalid.sent,undefined);
assert.deepEqual(invalid._scheduleDrafts[0].days,[]);
assert.equal(invalid._draft.triggers[0].data.rrule,rule);
invalid._onScheduleChange(0,{days:['SU']});
invalid._onScheduleChange(0,{time:''});
await invalid._onSave();assert.equal(invalid.sent,undefined);
assert.equal(invalid._scheduleDrafts[0].time,'');
invalid._onScheduleChange(0,{time:'00:00'});
assert.equal(invalid._validate(),null);
assert.equal(parseSchedule(invalid._draft.triggers[0].data.rrule).hour,0);
assert.deepEqual(parseSchedule(invalid._draft.triggers[0].data.rrule).days,['SU']);

for(const time_data of [null,{},'future',{rrule:null},{rrule:7},
    {execute_at:'2030-01-15T09:00:00Z',rrule:''},{rrule:rule+';COUNT=3'},
    {rrule:rule,future:true}]) {
  const original={type:'TIME',time_data};
  const data={_raw:original};
  if(time_data&&Object.hasOwn(time_data,'rrule')) data.rrule=time_data.rrule;
  const t={type:'time',data};
  assert.equal(editableSchedule(t,'Europe/Moscow'),null);
  assert.equal(scheduleError(t,'Europe/Moscow'),null);
  const readonly=modal([t]);
  assert.match(readonly._triggerDigest(t),/только чтение/);
  assert.ok(!readonly._renderTimeTriggerBody(t,0,false).strings.join('').includes('<input'));
  readonly._onScheduleChange(0,{time:'12:00'});
  assert.deepEqual(readonly._draft.triggers[0],t);
  readonly._draft.name='Другое имя';
  assert.equal(readonly._validate(),null);
  await readonly._onSave();assert.deepEqual(readonly.sent.spec.triggers[0],t);
}
assert.equal(scheduleError({data:{_raw:[]}},'Europe/Moscow'),'schedules.invalid');
assert.equal(scheduleError({data:{_raw:{type:'DEVICE'}}},'Europe/Moscow'),'schedules.invalid');
assert.equal(scheduleError({data:{rrule:''}},'Europe/Moscow'),'schedules.invalid');
const changed=structuredClone(trigger);changed.data.rrule=rule.replace('20300115','20260115');
assert.equal(scheduleError(changed,'Europe/Moscow'),'schedules.read_only');
const opaque=structuredClone(trigger);opaque.data._raw.time_data.rrule+=';COUNT=3';
assert.equal(scheduleError(opaque,'Europe/Moscow'),'schedules.read_only');
const zoneMismatch=modal();zoneMismatch._draft.raw_extras.timezone='UTC';
assert.match(zoneMismatch._triggerDigest(trigger),/только чтение/);
assert.equal(zoneMismatch._validate(),null);
for(const language of ['ru','en','be','kk','uz']) {
  const last=modal([trigger],[],language);last._removeTrigger(0);
  const error=last._validate();assert.ok(error&&!error.startsWith('schedules.'));
  await last._onSave();assert.equal(last.sent,undefined);
}
const shifted=modal([trigger,trigger]);shifted._onScheduleChange(1,{time:''});
shifted._removeTrigger(0);assert.equal(shifted._scheduleDrafts[0].time,'');
assert.ok(shifted._validate());
const external=modal();external._draft.is_ha_managed=false;
external._onScheduleChange(0,{time:'10:00'});
assert.equal(external._draft.triggers[0].data.rrule,rule);
external._onScheduleChange(5,{time:'10:00'});
const newScene=modal([]);newScene.isNew=true;newScene._addTrigger('time');
assert.ok(editableSchedule(newScene._draft.triggers[0],'Europe/Moscow'));
"""
    script = script.replace("RULE;", json.dumps(RULE) + ";", 1).replace(
        "of INVALID_RULES)", "of " + json.dumps(INVALID_RULES) + ")", 1
    )
    driver = tmp_path / "schedule.js"
    driver.write_text(script)
    subprocess.run(  # noqa: S603
        [NODE, str(driver)], capture_output=True, text=True, check=True, timeout=60
    )
