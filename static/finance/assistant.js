(() => {
  const form = document.getElementById('assistant-form');
  if (!form) return;
  const history = document.getElementById('chat-history');
  const input = document.getElementById('assistant-input');
  const send = document.getElementById('assistant-send');
  let conversationId = Number(history.dataset.conversation);
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const scroll = () => { history.scrollTop = history.scrollHeight; };
  function bubble(text, role='assistant') {
    const row = document.createElement('div'); row.className = `chat-message ${role}`;
    const el = document.createElement('div'); el.className = 'bubble'; el.textContent = text;
    row.appendChild(el); history.appendChild(row); scroll(); return row;
  }
  function proposalCard(row, entries, token) {
    const card = document.createElement('div'); card.className = 'proposal-card';
    const heading = document.createElement('strong'); heading.textContent = entries.length > 1 ? `Review ${entries.length} transactions` : 'Review before saving'; card.appendChild(heading);
    const fields = [];
    entries.forEach((entry, i) => {
      const box = document.createElement('div'); box.className = 'proposal-entry';
      const title = document.createElement('div'); title.className = 'proposal-entry-title'; title.textContent = `Transaction ${i+1}`; box.appendChild(title);
      const defs = [['description','Description','text'],['amount','Amount','number'],['kind','Type','select'],['date','Date','date'],['category','Category','text'],['account','Account','text']];
      const itemFields = {};
      defs.forEach(([key,label,type]) => {
        const wrap=document.createElement('label'); wrap.className='proposal-field'; wrap.append(document.createTextNode(label));
        let control;
        if (type==='select') { control=document.createElement('select'); [['expense','Expense'],['income','Income']].forEach(([v,l])=>{const o=document.createElement('option');o.value=v;o.textContent=l;control.appendChild(o)}); }
        else { control=document.createElement('input'); control.type=type; if(type==='number'){control.step='0.01';control.min='0.01'} }
        control.value=entry[key] ?? ''; control.required=true; wrap.appendChild(control); box.appendChild(wrap); itemFields[key]=control;
      });
      fields.push(itemFields); card.appendChild(box);
    });
    const rememberLabel=document.createElement('label'); rememberLabel.className='remember-line';
    const remember=document.createElement('input');remember.type='checkbox';rememberLabel.append(remember,document.createTextNode('Remember these category and account choices for next time'));
    card.appendChild(rememberLabel);
    const actions=document.createElement('div');actions.className='proposal-actions';
    const confirm=document.createElement('button');confirm.type='button';confirm.className='btn';confirm.textContent='Confirm and save';
    const cancel=document.createElement('button');cancel.type='button';cancel.className='btn light';cancel.textContent='Cancel';
    const status=document.createElement('div');status.className='proposal-status';
    confirm.onclick=async()=>{
      const payload=fields.map(row=>Object.fromEntries(Object.entries(row).map(([k,v])=>[k,v.value.trim()])));
      confirm.disabled=true;confirm.textContent='Saving…';
      try { const response=await fetch(form.dataset.confirmUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({draft_token:token,transactions:payload,remember:remember.checked})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not save.');status.textContent=data.message;status.classList.add('success');confirm.remove();cancel.remove(); }
      catch(err){status.textContent=err.message;status.classList.add('error');confirm.disabled=false;confirm.textContent='Try saving again'}
    };
    cancel.onclick=()=>{card.remove();bubble('Okay, I didn’t save those proposed entries.')};
    actions.append(confirm,cancel);card.append(actions,status);row.appendChild(card);scroll();
  }
  form.addEventListener('submit', async ev=>{
    ev.preventDefault();const message=input.value.trim();if(!message)return;
    bubble(message,'user');input.value='';send.disabled=true;send.textContent='Thinking…';
    try {
      const response=await fetch(form.dataset.chatUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({message,conversation_id:conversationId})});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'The assistant could not respond.');
      conversationId=data.conversation_id||conversationId;history.dataset.conversation=conversationId;
      const row=bubble(data.reply||'Here’s what I found.');if(data.transactions&&data.transactions.length)proposalCard(row,data.transactions,data.draft_token);
    } catch(err) { bubble(err.message,'error'); }
    finally { send.disabled=false;send.innerHTML='Send <span>➤</span>';input.focus(); }
  });
  input.addEventListener('keydown', e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
  scroll();
})();
