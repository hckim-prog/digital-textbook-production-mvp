"""Original offline publication themes. No third-party theme assets."""
THEMES = {
    'standard': dict(name='기본 교재형', accent='#285f85', tint='#edf4f9', ink='#203347', paper='#ffffff', font="'Malgun Gothic',sans-serif", body=10.5, leading=17),
    'lab': dict(name='코딩·실습형', accent='#087f78', tint='#eaf6f3', ink='#193336', paper='#ffffff', font="'Malgun Gothic',sans-serif", body=10.5, leading=17),
    'reading': dict(name='본문 중심형', accent='#79553c', tint='#f6f0e8', ink='#392e28', paper='#fffdf8', font="'Batang','Georgia',serif", body=11, leading=19),
}
VERSION = '1.0'


def resolve(master, selected='auto'):
    if selected != 'auto' and selected not in THEMES:
        raise ValueError('지원하지 않는 디자인 테마입니다.')
    code = sum(b.kind in ('code-block','code-output') for b in master.blocks)
    code += sum(k in ('code-block','code-output') for b in master.blocks for row in b.cell_kinds for k in row)
    if selected == 'auto':
        selected = 'lab' if code else ('reading' if sum(len(b.text) for b in master.blocks if b.kind=='paragraph') > 8000 and not any(b.kind=='table' for b in master.blocks) else 'standard')
    return {'id':selected, 'version':VERSION, **THEMES[selected]}


def stylesheet(theme, web=True):
    base = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:__FONT__;color:__INK__;background:__PAPER__;line-height:1.85;margin:0;padding:24px;font-size:17px;overflow-wrap:break-word}
a{color:__ACCENT__;text-underline-offset:4px}a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid __ACCENT__;outline-offset:3px}
.book-title{border-top:8px solid __ACCENT__;border-bottom:1px solid #d9e1e5;padding:36px 0;margin-bottom:30px;font-weight:700;font-size:2rem;line-height:1.5}
.book-title .cover-title{border:0;padding:0;margin:10px 0;font-size:clamp(1.7rem,3.3vw,2.65rem);letter-spacing:-.04em}.edition{font:700 12px sans-serif;letter-spacing:.18em;color:__ACCENT__}
h1,h2,h3,h4{line-height:1.5;scroll-margin-top:24px;word-break:keep-all}h1{font-size:1.9rem;color:__ACCENT__;border-top:3px solid __ACCENT__;padding-top:24px;margin:48px 0 24px}h2{font-size:1.45rem;border-bottom:1px solid #d9e1e5;padding-bottom:12px;margin:34px 0 18px}h4{font-size:1.03rem;color:__ACCENT__;margin:22px 0 12px}h3{font-size:1.15rem;color:__ACCENT__;margin:28px 0 14px}
.paragraph{margin:.9em 0}section{min-width:0}img{max-width:100%;height:auto;display:block;margin:22px auto}.figure-caption{font-size:.88em;color:#5d6872;text-align:center;margin:12px 0 24px}
pre.code-block,pre.code-output{font:14px/1.7 Consolas,'Cascadia Code',monospace;white-space:pre;overflow-x:auto;max-width:100%;tab-size:4;background:#f1f5f6;border:1px solid #d7e3e3;border-left:4px solid __ACCENT__;border-radius:6px;padding:20px;margin:22px 0;color:#172f37;overflow-wrap:normal}
pre.code-output{background:#f6f6f6;border-left-color:#8a939b}pre code{font:inherit;white-space:inherit}table{border-collapse:collapse;width:100%;font-size:.94em;margin:12px 0}td{border:1px solid #cedadd;padding:12px;vertical-align:top}tr:nth-child(odd){background:__TINT__}td pre{font-size:12px;padding:10px}
.procedure-step{border-left:3px solid __ACCENT__;padding:10px 16px;margin:12px 0;background:__TINT__}.llm-usage,.exercise,.chapter-summary{background:__TINT__;border:1px solid #d9e1e5;border-radius:8px;padding:20px;margin:24px 0}.math-expression{font-family:'Cambria Math',serif;white-space:pre-wrap}.list-label{margin-right:.6em}
.book-toc{font-family:'Malgun Gothic',sans-serif;font-size:14px;line-height:1.65}.book-toc ol{padding-left:19px;list-style:none}.book-toc>ol{padding-left:0}.book-toc a{display:block;padding:6px 8px;color:#4b5963;text-decoration:none;border-radius:4px}.book-toc a:hover,.book-toc a[aria-current=true]{background:__TINT__;color:__ACCENT__}.book-toc strong{display:none}
"""
    if web:
        base += """
.book-shell{max-width:1220px;margin:auto;display:grid;grid-template-columns:250px minmax(0,790px);gap:0 46px}.book-title{grid-column:1/-1}.book-content{min-width:0;padding-bottom:70px}.reader-sidebar{align-self:start;position:sticky;top:24px;max-height:calc(100vh - 48px);overflow:auto;padding:16px;border:1px solid #dce4e7;border-radius:8px;background:#fff}.reader-sidebar summary{font-weight:700;cursor:pointer;color:__ACCENT__}.table-wrap{overflow-x:auto}.code-tools{text-align:right;margin-bottom:-16px}.copy-code{font:12px 'Malgun Gothic',sans-serif;border:1px solid #bfcdd1;background:white;color:__ACCENT__;padding:5px 12px;border-radius:4px;cursor:pointer}.skip-link{position:absolute;top:-80px}.skip-link:focus{top:0;background:white;padding:12px;z-index:10}
@media(max-width:800px){body{padding:18px;font-size:16px}.book-shell{display:block}.reader-sidebar{position:static;max-height:330px;margin-bottom:28px}.book-title{padding:24px 0}.table-wrap table{min-width:520px}h1{font-size:1.65rem}}
@media print{body{font-size:11pt;background:white;padding:0}.book-shell{display:block}.reader-sidebar,.code-tools,.skip-link{display:none}h1{break-before:page}h1,h2,h3,h4{break-after:avoid}img{break-inside:avoid}pre{overflow:visible}a{color:inherit}.book-title .cover-title{break-before:auto}}
"""
    else:
        base += """
body{padding:0;margin:5%;font-size:1em}.book-title{font-size:1.8em}h1{break-before:page;font-size:1.6em}h2{font-size:1.3em}h3{font-size:1.1em}h4{font-size:1em}h1,h2,h3,h4{break-after:avoid}.book-toc strong{display:block}pre.code-block,pre.code-output{font-size:.78em;overflow:auto}table{font-size:.85em}
"""
    for key,value in [('FONT',theme['font']),('INK',theme['ink']),('PAPER',theme['paper']),('ACCENT',theme['accent']),('TINT',theme['tint'])]:
        base=base.replace('__'+key+'__',value)
    return base


READER_JS = """
(()=>{
 const nav=document.querySelector('.reader-sidebar details');
 if(nav && matchMedia('(max-width:800px)').matches) nav.open=false;
 const links=[...document.querySelectorAll('.book-toc a')];
 if('IntersectionObserver' in window){
   const observer=new IntersectionObserver(entries=>{for(const e of entries){if(e.isIntersecting){for(const a of links)a.removeAttribute('aria-current');const a=links.find(a=>a.hash==='#'+e.target.id);if(a)a.setAttribute('aria-current','true');}}},{rootMargin:'-5% 0px -65% 0px'});
   document.querySelectorAll('[data-outline-id]').forEach(h=>observer.observe(h));
 }
 document.querySelectorAll('pre').forEach(pre=>{
   const tools=document.createElement('div');tools.className='code-tools';
   const button=document.createElement('button');button.className='copy-code';button.type='button';button.textContent='코드 복사';button.setAttribute('aria-label','이 코드 원문 복사');
   button.onclick=async()=>{const text=(pre.querySelector('code')||pre).textContent;try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);else{const area=document.createElement('textarea');area.value=text;document.body.appendChild(area);area.select();const copied=document.execCommand('copy');area.remove();if(!copied)throw new Error();}button.textContent='복사됨';}catch{button.textContent='직접 선택해 복사하세요';}};
   tools.appendChild(button);pre.before(tools);
 });
})();
"""
