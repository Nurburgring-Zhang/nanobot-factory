async function renderEnhancedTools(){
  const c=$('page-content');if(!c)return;
  c.innerHTML=`<div class="page-header"><div><div class="page-title">🔬 增强工具</div></div><div class="page-stats"><div class="page-stat"><div class="page-stat-val">3层</div><div class="page-stat-label">去重引擎</div></div><div class="page-stat"><div class="page-stat-val">3型</div><div class="page-stat-label">语音分析</div></div><div class="page-stat"><div class="page-stat-val">3型</div><div class="page-stat-label">视频分析</div></div></div></div>
  <div class="dashboard-grid">
    <div>
      <div class="panel"><div class="panel-title">🗜️ 数据去重</div>
        <div class="detail-field"><span class="detail-field-label">精确(MD5)</span><span class="detail-field-value">std::hashlib</span></div>
        <div class="detail-field"><span class="detail-field-label">感知(pHash)</span><span class="detail-field-value">imagehash + SSIM</span></div>
        <div class="detail-field"><span class="detail-field-label">语义(CLIP)</span><span class="detail-field-value">CLIP-ViT-Base</span></div>
        <div style="margin-top:8px"><button class="btn btn-primary btn-sm" onclick="et_runDedup()">▶ 执行去重</button></div>
      </div>
      <div class="panel"><div class="panel-title">🎤 语音分析</div>
        <div class="detail-field"><span class="detail-field-label">ASR</span><span class="detail-field-value">Whisper-large-v3</span></div>
        <div class="detail-field"><span class="detail-field-label">说话人分离</span><span class="detail-field-value">pyannote-3.1</span></div>
        <div class="detail-field"><span class="detail-field-label">情感识别</span><span class="detail-field-value">wav2vec2</span></div>
        <div style="margin-top:8px"><button class="btn btn-outline btn-sm" onclick="et_transcribe()">🎙 转写</button></div>
      </div>
    </div>
    <div>
      <div class="panel"><div class="panel-title">🎬 视频分析</div>
        <div class="detail-field"><span class="detail-field-label">场景检测</span><span class="detail-field-value">PySceneDetect</span></div>
        <div class="detail-field"><span class="detail-field-label">动作识别</span><span class="detail-field-value">VideoMAE-base</span></div>
        <div class="detail-field"><span class="detail-field-label">关键帧提取</span><span class="detail-field-value">ffmpeg I-frame</span></div>
        <div style="margin-top:8px"><button class="btn btn-outline btn-sm" onclick="et_detectScenes()">🔍 场景检测</button></div>
      </div>
      <div class="panel"><div class="panel-title">📥 数据寻源</div>
        <div class="detail-field"><span class="detail-field-label">平台</span><span class="detail-field-value">HuggingFace/Kaggle/arXiv</span></div>
        <div class="detail-field"><span class="detail-field-label">评分维度</span><span class="detail-field-value">可靠性/更新/合规/活跃</span></div>
        <div style="margin-top:8px"><button class="btn btn-outline btn-sm" onclick="et_searchSources()">🔍 搜索数据源</button></div>
      </div>
    </div>
  </div>`;
}
async function et_runDedup(){try{const r=await apiPost('/api/enhanced/dedup',{paths:[],level:'semantic'});showToast('去重完成: 去重率'+(r?.dedup_rate||'N/A'),'success')}catch(e){showToast('去重失败','error')}
async function et_transcribe(){try{const r=await apiPost('/api/enhanced/speech/transcribe',{file:null});showToast('转写: '+(r?.text||'').slice(0,30),'success')}catch(e){showToast('转写失败','error')}
async function et_detectScenes(){try{const r=await apiPost('/api/enhanced/video/scenes',{video_path:prompt('视频路径:')||''});showToast('检测到 '+(r?.scenes||0)+' 个场景','success')}catch(e){showToast('检测失败','error')}
async function et_searchSources(){try{const q=prompt('搜索关键词:')||'image classification';const r=await apiPost('/api/discovery/search',{query:q});showToast('找到 '+(r?.results?.length||0)+' 个数据源','success')}catch(e){showToast('搜索失败','error')}
