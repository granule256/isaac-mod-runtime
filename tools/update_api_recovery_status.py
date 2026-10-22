#!/usr/bin/env python3
"""合并测试证据和模组依赖，生成三态表；变更保留旧行，历史只追加。"""
from pathlib import Path
import collections,datetime,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs';TABLE=DOC/'API与回调测试修复状态表.md';DATA=TABLE.with_suffix('.json');EVENTS=DOC/'API与回调测试修复历史.jsonl'
STATES={'未测','有问题待修复','已测暂未发现问题'}
def read(path):return json.loads((ROOT/path).read_text())
def norm(key):
    owner,sep,name=key.partition(':')
    return owner.replace('_','').lower()+sep+name

def build():
    snap=read('docs/API与回调恢复进度快照-20261018.json');pc=read('analysis/lua-api-inventory/inventory.json');manual=read('docs/API与回调测试修复判定.json')
    records={}; aliases={}
    def add(key,kind='API',source='',**extra):
        canonical=aliases.get(norm(key),key);aliases[norm(key)]=canonical
        row=records.setdefault(canonical,{'key':canonical,'kind':kind,'status':'未测','basis':'尚缺测试证据','progress':'待测/版本核定','tested_mods':[],'candidate_mods':[],'evidence':[],'sources':[]})
        if source and source not in row['sources']:row['sources'].append(source)
        row.update(extra);return row
    for row in snap['catalog']:add(row['key'],source='当前登记快照',maturity=row['maturity'])
    for row in snap['seven_batch_entries']:add(row['key'],'字段'if row['kind']=='field'else'API',row['source'])
    for row in pc['apis']:add(row['key'],'字段'if 'Variables'in row['kinds']else'API','固定PC候选库存',availability=row.get('availability',[]))
    for row in snap['callbacks']:add('Callback:'+str(row['id']),'回调','tools/callback_surface.json',name=row['name'],callback_id=row['id'])
    # 用户所说的“测试过”包括已有真机加载/功能记录；推定范围不冒充逐分支执行。
    mods=read('dist/corpus-hardware-20261016/test-matrix-progress-08.json');tested={}
    excluded=('paused','prerequisite','author_switch_off','用户暂停')
    for m in mods:
        if any(x in m.get('status','')for x in excluded)or m['name']in ('FiendFolio-CommunityRooms','IsaacOnTwitchReloaded','BOI-Ambush-Indicators'):continue
        tested[m['name']]={'name':m['name'],'scope':m.get('scope',m.get('status','真机测试记录')),'evidence':['docs/语料模组逐项真机恢复与验收-20261016.md']+['dist/corpus-hardware-20261016/'+x for x in m.get('evidence',[])if (ROOT/'dist/corpus-hardware-20261016'/x).exists()]}
    source_map=read('dist/api-recovery-repairs-20261020/dependency-source-map.json')
    code_sources=read('dist/api-recovery-repairs-20261020/dependency-code-source-map.json')
    reports=[ROOT/row['snapshot']for row in source_map]
    global_keys={r['key'].split(':',1)[1]:r['key']for r in records.values()if r['key'].startswith('Global:')and re.fullmatch(r'[A-Za-z_]\w*',r['key'].split(':',1)[1])}
    global_pattern=re.compile(r'(?<![A-Za-z0-9_.:])('+ '|'.join(re.escape(n)for n in sorted(global_keys,key=len,reverse=True))+r')\s*\(')if global_keys else None

    for path in reports:
        d=json.loads(path.read_text());mod=d.get('label',path.stem)
        mod={'eid':'EID','goodtrip':'GoodTrip'}.get(mod.lower(),mod)
        if mod not in tested:continue
        relative=str(path.relative_to(ROOT))
        for usage in d.get('used',[]):
            key=aliases.get(norm(usage['api']))
            if not key:continue
            row=records[key];target='tested_mods'if usage.get('confident',True)else'candidate_mods'
            if mod not in row[target]:row[target].append(mod)
            if relative not in row['evidence']:row['evidence'].append(relative)
        for usage in d.get('field_surface',{}).get('used',[]):
            owners=usage.get('owners',[])
            for owner in owners:
                key=aliases.get(norm(owner+':'+usage['name']))
                if not key:continue
                row=records[key];target='tested_mods'if len(owners)==1 else'candidate_mods'
                if mod not in row[target]:row[target].append(mod)
                if relative not in row['evidence']:row['evidence'].append(relative)
        # 依赖的回调按作者源码中的明确枚举引用关联；动态注册保留未确认。
        modpath=d.get('mod','').rstrip('/')+'/'
        if d.get('mod'):
            # 只读形成依赖结论的逐字源码快照；不依赖本机未跟踪的解包目录。
            for source_row in code_sources:
                if not source_row['original'].startswith(modpath):continue
                source=ROOT/source_row['snapshot']
                assert hashlib.sha256(source.read_bytes()).hexdigest()==source_row['sha256']
                import mod_api_gap_report
                text=mod_api_gap_report.lua_source(source)
                if global_pattern:
                    for name in set(global_pattern.findall(text)):
                        row=records[global_keys[name]]
                        if mod not in row['tested_mods']:row['tested_mods'].append(mod)
                        evidence=str(source.relative_to(ROOT))
                        if evidence not in row['evidence']:row['evidence'].append(evidence)
                for name in set(re.findall(r'ModCallbacks\.(MC_[A-Z_]+)',text)):
                    for callback in snap['callbacks']:
                        if callback['name']==name:
                            row=records['Callback:'+str(callback['id'])]
                            if mod not in row['tested_mods']:row['tested_mods'].append(mod)
                            evidence=str(source.relative_to(ROOT))
                            if evidence not in row['evidence']:row['evidence'].append(evidence)
    for row in records.values():
        if row['tested_mods']:
            row.update(status='已测暂未发现问题',basis='用户授权：已测模组依赖推定',progress='具体分支和边界未逐项覆盖')
        elif row.get('maturity')=='HardwareVerified':row.update(status='已测暂未发现问题',basis='历史单项真机记录',progress='保持原证据范围')
    # 只有明确记录宿主通过的批次/成熟度可算已测，纯静态恢复仍留未测。
    for item in snap['seven_batch_entries']:
        if item.get('recorded_status')!='restored_static_host_verified':continue
        row=records[aliases[norm(item['key'])]]
        if row['status']=='未测':row.update(status='已测暂未发现问题',basis='历史批次宿主验证',progress='尚未逐项真机；仅原批次证据范围')
    for row in records.values():
        if row.get('maturity')=='HostVerified' and row['status']=='未测':row.update(status='已测暂未发现问题',basis='历史单项宿主验证',progress='尚未单项真机')
    evidence=read('tools/api_maturity_evidence.json')['rows']
    for key,info in evidence.items():
        canonical=aliases.get(norm(key))
        if canonical and info.get('maturity')=='HardwareVerified':
            row=records[canonical];row.update(status='已测暂未发现问题',basis='历史单项真机记录',progress='保持原证据范围')
            row['evidence']+=list(dict.fromkeys(e['file']for e in info.get('evidence',[])if 'file'in e))
    for path in ['dist/api-callback-followup-20261020/hardware-verdict.json','dist/api-lifecycle-followup-20261020/hardware-verdict.json']:
        for item in read(path)['query_recheck_25']:
            key=item['api'].replace('Isaac:', 'Isaac:')
            if norm(key)not in aliases:continue
            row=records[aliases[norm(key)]];row.update(status='已测暂未发现问题',basis='单项真机：'+item['status'],progress='仅当前证据场景；不代表全部边界')
            if path not in row['evidence']:row['evidence'].append(path)
    for key in ['Seeds:HasSeedEffect','EntityPlayer:GetMultiShotParams','EntityPlayer:GetMultiShotPositionVelocity','ProjectileParams:Scale','ProjectileParams:FallingSpeedModifier']:
        row=add(key,source='2026-10-20真机补测');row.update(status='已测暂未发现问题',basis='单项真机关系/实际消费',progress='保持已验场景范围');row['evidence'].append('docs/种子与生命周期继续补测-20261020.md'if key.startswith('Seeds:')else'docs/未确认接口与回调补测-20261020.md')
    observed_path='dist/api-callback-hardware-20261018/callback-observed-union.json'
    for identifier in read(observed_path)['observed']:
        row=records['Callback:'+str(identifier)]
        row.update(status='已测暂未发现问题',basis='真实游戏事件到达/参数观察',progress='尚未逐项覆盖全部时序、返回和寿命边界')
        row['evidence'].append(observed_path)
    # 所有明确失败/尚缺条件最后覆盖，绝不被模组加载或早期成熟度吞掉。
    for key,override in manual['overrides'].items():
        row=add(key,'回调'if key.startswith('Callback:')else'API',source='人工缺陷/复验判定');row.update(override);row['basis']='单项真机：修复后复验' if row['status']=='已测暂未发现问题' else ('明确缺陷' if row['status']=='有问题待修复' else '人工核定：尚缺条件')
    row=records['Callback:71'];row.update(status='已测暂未发现问题',basis='单项真机：返回值真实替换实体',progress='未覆盖全部网格/过滤边界');row['evidence'].append('dist/api-callback-verification-20261020/enemy-room-result.json')
    # 已记录行若暂时不在生成来源中，保留原行，不删除历史信息。
    previous=json.loads(DATA.read_text())if DATA.exists()else{}
    for row in previous.get('rows',[]):
        if row['key']not in records:records[row['key']]=row
    rows=sorted(records.values(),key=lambda r:(r['kind']!='回调',r.get('callback_id',9999),r['key']))
    for row in rows:
        assert row['status']in STATES
        for name in ['tested_mods','candidate_mods','sources','evidence']:row[name]=sorted(set(row.get(name,[])))
    assert len({r['key']for r in rows})==len(rows)
    assert next(r for r in rows if r['key']=='Callback:3')['status']=='有问题待修复'
    return {'schema':1,'updated':'2026-10-20','policy':manual['policy'],'tested_mods':list(tested.values()),'counts':dict(collections.Counter(r['status']for r in rows)),'rows':rows},previous

def main():
    current,previous=build();old={r['key']:r for r in previous.get('rows',[])};events=[]
    for row in current['rows']:
        before=old.get(row['key'])
        if before!=row:events.append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'key':row['key'],'before':before,'after':row})
    if previous and current==previous and TABLE.exists():print('状态和证据没有变化，不重写或追加重复历史');return
    if TABLE.exists():
        history=DOC/'API状态表历史';history.mkdir(exist_ok=True)
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        (history/(stamp+'.md')).write_bytes(TABLE.read_bytes())
        if DATA.exists():(history/(stamp+'.json')).write_bytes(DATA.read_bytes())
    with EVENTS.open('a')as f:
        for event in events:f.write(json.dumps(event,ensure_ascii=False)+'\n')
    DATA.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    lines=['# API与回调测试修复状态表','', '本表按用户要求维护三态：未测、有问题待修复、已测暂未发现问题；明确缺陷优先于模组依赖推定。原始历史与旧报告不删除。','', '已测模组明确依赖的接口按用户授权暂定未发现问题；这不是逐分支/全部参数已验，也不自动更改运行时ApiMaturity。候选所属类型不明的引用只列候选，不冒充确定依赖。明确的宿主通过也标已测并注明范围，纯静态恢复不算测试。','', '固定PC库存含继承/版本待核项，入表不表示它们都是当前应新增的接口；14号回调PC不派发，不进入待执行测试队列。','', '更新：python3 tools/update_api_recovery_status.py；修改人工判定文件API与回调测试修复判定.json后刷新。机器数据同名.json，历史API与回调测试修复历史.jsonl保留完整前后记录；旧版可读表存API状态表历史/。','', ' | 状态 | 数量 |',' | --- | --- |']
    for state in ['未测','有问题待修复','已测暂未发现问题']:lines.append(f'| {state} | {current["counts"].get(state,0)} |')
    lines+=['','| 接口/回调 | 状态 | 依据/进度 | 已测依赖模组 | 原因与证据 |','| --- | --- | --- | --- | --- |']
    esc=lambda s:str(s).replace('|','/').replace('\n',' ')
    for row in current['rows']:
        mods='、'.join(row['tested_mods'])or('候选：'+'、'.join(row['candidate_mods'])if row['candidate_mods']else'—')
        links='；'.join(f'[{Path(s).name}](<../{s}>)'for s in row['evidence'][:4])
        name=(str(row.get('callback_id',''))+' '+row.get('name',row['key']))if row['kind']=='回调'else row['key']
        lines.append('| '+' | '.join([esc(name),row['status'],esc(row['basis']+'；'+row['progress']),esc(mods),esc(row.get('reason',''))+' '+links])+' |')
    TABLE.write_text('\n'.join(lines)+'\n');print(json.dumps({'rows':len(current['rows']),'counts':current['counts'],'changes':len(events)},ensure_ascii=False))
if __name__=='__main__':main()
