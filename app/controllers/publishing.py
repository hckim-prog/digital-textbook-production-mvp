"""One-click publication with a preflight gate before paid proofreading."""
from html import escape
from core.qa.checks import check, save_report
from core.manuscript.structure import propose_ai, ai_payload, validate, fingerprint
from core.manuscript.preflight import inspect_structure, heading_level
from core.ai.workflow import read_json
from core.cancellation import check_cancelled


def preflight(job, use_existing_draft=False):
    master=job.master()
    integrity=check(master, job.source, job.work/'assets', {})
    hard=[{'code':'source_integrity','block_id':'', 'message':c['label'] + ': ' + c.get('detail','')}
          for c in integrity['checks'] if not c['passed']]
    if master.blocks and not any(b.text.strip() or b.rows or b.assets for b in master.blocks
                                 if heading_level(b) is None):
        hard.append({'code':'no_body','block_id':master.blocks[0].id,'message':'제목 외에 제작할 본문·표·그림이 없습니다.'})
    try:
        saved=job.structure().load()
        if saved and (use_existing_draft or saved['status']=='approved'):
            structure={'passed':True,'nodes':validate(master,saved['nodes']), 'issues':[]}
            origin='previously-approved'
        else:
            structure=inspect_structure(master)
            origin='automatic-rules'
    except ValueError as exc:
        structure={'passed':False,'nodes':[], 'issues':[{'code':'saved_structure','block_id':'','message':str(exc)}]}
        origin='invalid-saved-structure'
    report={'passed':not hard and structure['passed'], 'hard_issues':hard,
            'issues':hard+structure['issues'], 'nodes':structure['nodes'], 'origin':origin,
            'source_hash':master.source_hash, 'warnings':integrity['warnings'],
            'note':'자동 진단은 제목 단서·순서·범위·원문 보존을 검사하며 내용의 정확성을 보증하지 않습니다.'}
    save_report(report,job.work/'preflight.json')
    rows=''.join('<li>'+escape(i['block_id']+' '+i['message'])+'</li>' for i in report['issues'])
    (job.work/'preflight.html').write_text('<!doctype html><meta charset="utf-8"><title>원고 사전 진단</title><h1>'
        +('자동 제작 가능' if report['passed'] else '원고 보완 필요')+'</h1><ul>'+rows+'</ul><p>'+escape(report['note'])+'</p>',encoding='utf-8')
    return report


def publish(job, formats, destination=None, progress=None, *, run_ai=False, model=None, reasoning='none',
            allow_restructure=False, structure_model=None, structure_reasoning='none', cancelled=None, theme="auto",
            depth_mode=False, max_depth=4, quick=True):
    from core.export.themes import resolve
    resolve(job.master(), theme)
    emit=progress or (lambda _:None)
    check_cancelled(cancelled)
    stopped=cancelled if cancelled is not None else (lambda:False)
    def stop():
        check_cancelled(stopped)
    stop()
    if not formats or set(formats)-{'web','pdf','epub'}: raise ValueError('출력 형식을 선택하세요.')
    job._output_base(destination)  # Fail invalid destinations before any paid request.
    emit({'phase':'원고 사전 진단 중','percent':2})
    report=preflight(job, use_existing_draft=depth_mode)
    stop()
    if report['hard_issues'] or report['origin']=='invalid-saved-structure':
        raise ValueError('원고 보완 필요 (AI 교정 미실행): '+ '\n'.join(i['block_id']+' '+i['message'] for i in report['issues']))
    master=job.master()
    if depth_mode:
        from core.manuscript.depth import enrich
        report.update(enrich(job, master, report['nodes'], structure_model, structure_reasoning,
                             max_depth=max_depth, progress=emit, cancelled=stopped))
        report['issues'] = []
    if not report['passed']:
        if not allow_restructure:
            raise ValueError('구조 보완 필요 (AI 교정 미실행): '+ '\n'.join(i['block_id']+' '+i['message'] for i in report['issues'])
                             +'\n사전 진단 결과를 확인하거나 AI 구조 재구성을 허용하세요.')
        ai_payload(master)  # Enforce input limit before requesting.
        if not structure_model: raise ValueError('구조 분석에 사용할 기술 검토 모델을 선택하세요.')
        emit({'phase':'AI 구조 재구성 중 · 본문은 보존','percent':8})
        stop()
        cache_key={'fingerprint':fingerprint(master),'model':structure_model,'reasoning':structure_reasoning,'policy':'publication-v1'}
        cached=read_json(job.work/'preflight-ai.json',{})
        if cached.get('passed') and cached.get('cache_key')==cache_key:
            nodes=cached['nodes']
        else:
            nodes=propose_ai(job.root, master, structure_model, structure_reasoning, mode='create')
        assessment=inspect_structure(master,nodes,generated=True)
        report.update(nodes=assessment['nodes'], issues=assessment['issues'], passed=assessment['passed'],origin='ai-reconstructed',cache_key=cache_key)
        save_report(report,job.work/'preflight-ai.json')
        stop()
        if not report['passed']:
            raise ValueError('AI 구조 검사 미통과 (교정 미실행): '+ '\n'.join(i['block_id']+' '+i['message'] for i in report['issues']))
    stop()
    if run_ai:
        emit({'phase':'AI 교정 중','percent':15})
        run=job.proofread(model,reasoning,role='proofreading',cancelled=stopped,
            progress=lambda info:emit({'phase':f"AI 교정 {info['done']}/{info['total']} 문단",'percent':15+int(50*info['done']/max(info['total'],1))}))
        stop()
        if run['failure_count'] or run['unprocessed_count']:
            raise RuntimeError('AI 교정 일부가 실패했습니다. 완료된 제안은 저장했습니다. 재시도하거나 AI 교정을 끄고 제작하세요.')
    stop()
    result=job.build(formats,destination,progress,quick=quick,publication=report,theme=theme,cancelled=stopped)
    if not result['qa']['passed']:
        raise RuntimeError('출력 보존 검사 미통과. 배포용 완료로 처리하지 않았습니다. 검사 보고서: '+result['report'])
    return result
