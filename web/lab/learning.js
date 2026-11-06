// These checks display build-time answers and request logs computed by the Python reader.
// No Parquet decoding or storage-request planning is duplicated in JavaScript.
export function mountLearning() {
 for (const root of document.querySelectorAll('.learning-check')) {
  const data=JSON.parse(root.querySelector('.learning-data').textContent);
  for(const controls of root.querySelectorAll('.learning-controls')) controls.hidden=false;
  const form=root.querySelector('form');
  if(form)form.addEventListener('submit',event=>{
   event.preventDefault();const input=form.querySelector('input');
   const correct=input.value.trim()!==''&&Number(input.value)===data.answer;
   const status=form.querySelector('.learning-feedback');
   status.textContent=correct?'Correct. '+data.explanation:'Try again. '+data.hint;
   status.dataset.correct=String(correct);input.setAttribute('aria-invalid',String(!correct));
  });
  if(data.cases){
   const mode=root.querySelector('[name=mode]'),prefetch=root.querySelector('[name=prefetch]');
   const draw=()=>{
    const selected=data.cases.find(c=>c.mode===mode.value&&c.prefetch===Number(prefetch.value));
    const host=root.querySelector('.learning-trace');host.replaceChildren();
    const wrap=document.createElement('div');wrap.className='table-wrap';
    const table=document.createElement('table');const header=table.createTHead().insertRow();
    for(const label of ['Request','Range','File bytes returned','Why']){const th=document.createElement('th');th.textContent=label;header.append(th);}
    const body=table.createTBody();for(const r of selected.requests){const tr=body.insertRow();for(const value of [r.method,r.range,r.bytes,r.why])tr.insertCell().textContent=value;}
    wrap.append(table);host.append(wrap);const summary=document.createElement('p');summary.textContent=`${selected.requests.length} requests · ${selected.bytes} file bytes returned.`;summary.setAttribute('role','status');host.append(summary);
   };
   mode.addEventListener('change',draw);prefetch.addEventListener('change',draw);
  }
  root.dataset.ready='true';
 }
}
