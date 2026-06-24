async function renderAudioTools(){
  const c=$('page-content');if(!c)return;
  c.innerHTML=`<div class="page-header"><div><div class="page-title">🎤 音频工具</div></div><div class="page-stats"><div class="page-stat"><div class="page-stat-val">5</div><div class="page-stat-label">功能</div></div><div class="page-stat"><div class="page-stat-val">Whisper</div><div class="page-stat-label">ASR引擎</div></div></div><div class="page-actions"><button class="btn btn-primary btn-sm" onclick="at_speak()">🔊 TTS转语音</button></div></div>
  <div class="dashboard-grid">
    <div><div class="panel"><div class="panel-title">📝 文字转语音 TTS</div>
      <div class="form-group"><label class="form-label">输入文本</label><textarea class="form-textarea" id="at-tts-text" placeholder="输入要转换的文字..."></textarea></div>
      <div class="form-row"><div class="form-group"><label class="form-label">声音</label><select class="form-select" id="at-tts-voice"><option>default</option><option>female</option><option>male</option></select></div><div class="form-group"><label class="form-label">语速</label><select class="form-select" id="at-tts-speed"><option value="1.0">正常</option><option value="0.8">慢</option><option value="1.3">快</option></select></div></div>
      <button class="btn btn-primary btn-sm" onclick="at_tts()">▶ 生成语音</button>
    </div>
    <div class="panel"><div class="panel-title">🎵 AI音乐生成</div>
      <div class="form-group"><label class="form-label">描述</label><input class="form-input" id="at-music-prompt" placeholder="描述想要的音乐风格..."></div>
      <div class="form-row"><div class="form-group"><label class="form-label">时长(秒)</label><input class="form-input" id="at-music-dur" value="30"></div><div class="form-group"><label class="form-label">风格</label><select class="form-select" id="at-music-style"><option>ambient</option><option>electronic</option><option>classical</option><option>jazz</option></select></div></div>
      <button class="btn btn-primary btn-sm" onclick="at_music()">🎵 生成音乐</button>
    </div></div>
    <div><div class="panel"><div class="panel-title">🎙 语音转文字 ASR</div>
      <div class="form-group"><label class="form-label">音频文件路径</label><input class="form-input" id="at-asr-path" placeholder="/data/audio/xxx.wav"></div>
      <button class="btn btn-outline btn-sm" onclick="at_asr()">📝 转写</button>
      <div id="at-asr-result" style="margin-top:8px;padding:8px;background:var(--bg-primary);border-radius:6px;font-size:12px;display:none"></div>
    </div>
    <div class="panel"><div class="panel-title">🎬 音效生成</div>
      <div class="form-group"><label class="form-label">描述</label><input class="form-input" id="at-sfx-desc" placeholder="如: 爆炸声/雨声/脚步声..."></div>
      <button class="btn btn-outline btn-sm" onclick="at_sfx()">🔊 生成音效</button>
    </div></div>
  </div>`;
}
async function at_tts(){
  const text=document.getElementById('at-tts-text')?.value||'你好';
  const voice=document.getElementById('at-tts-voice')?.value||'default';
  const speed=parseFloat(document.getElementById('at-tts-speed')?.value||'1');
  try{const r=await apiPost('/api/audio/tts',{text,voice,speed});showToast('语音已生成: '+(r?.job?.id||''),'success')}catch(e){showToast('TTS失败','error')}
}
async function at_music(){
  const prompt=document.getElementById('at-music-prompt')?.value||'ambient music';
  const dur=parseFloat(document.getElementById('at-music-dur')?.value||'30');
  const style=document.getElementById('at-music-style')?.value||'ambient';
  try{const r=await apiPost('/api/audio/music',{prompt,duration:dur,style});showToast('音乐已生成','success')}catch(e){showToast('生成失败','error')}
}
async function at_asr(){
  const path=document.getElementById('at-asr-path')?.value;if(!path)return showToast('请输入文件路径','error');
  try{const r=await apiPost('/api/audio/asr',{file_path:path});const el=document.getElementById('at-asr-result');el.style.display='block';el.textContent=r?.text||'无结果';showToast('转写完成')}catch(e){showToast('ASR失败','error')}
}
function at_sfx(){const d=document.getElementById('at-sfx-desc')?.value||'click';apiPost('/api/audio/sfx?description='+d).then(()=>showToast('音效已生成')).catch(()=>showToast('失败','error'))}
function at_speak(){const t=document.getElementById('at-tts-text')?.value||'你好';apiPost('/api/audio/tts',{text:t,voice:'default',speed:1.0}).catch(()=>{})}
