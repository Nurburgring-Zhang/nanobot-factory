/* IMDF 绘本生产工坊 — F1.7 */
async function renderPictureBook() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `<div style="margin-bottom:16px">
    <h2 style="font-size:18px;color:#e0e0ff;margin:0">📚 绘本工坊</h2>
  </div>
  <div style="display:grid;grid-template-columns:280px 1fr 260px;gap:16px;height:calc(100vh-200px)">
    <div style="background:#1a1a2e;border-radius:10px;padding:14px;overflow-y:auto;border:1px solid #2a2a4a">
      <h3 style="font-size:14px;color:#ccc;margin:0 0 12px">📖 绘本配置</h3>
      <label style="font-size:11px;color:#888;display:block;margin-bottom:4px">书名</label>
      <input id="bk-title" value="我的故事书" style="width:100%;padding:8px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin-bottom:10px">
      <label style="font-size:11px;color:#888;display:block;margin-bottom:4px">风格</label>
      <select id="bk-style" style="width:100%;padding:8px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin-bottom:10px">
        <option value="storybook">故事绘本</option><option value="watercolor">水彩风格</option>
        <option value="cartoon">卡通风格</option><option value="realistic">写实风格</option>
        <option value="anime">日系动漫</option>
      </select>
      <label style="font-size:11px;color:#888;display:block;margin-bottom:4px">页数</label>
      <input id="bk-pages" type="number" value="8" min="2" max="32" style="width:100%;padding:8px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin-bottom:10px">
      <label style="font-size:11px;color:#888;display:block;margin-bottom:4px">目标读者</label>
      <select id="bk-audience" style="width:100%;padding:8px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin-bottom:10px">
        <option value="3-6">3-6岁</option><option value="6-10">6-10岁</option><option value="10+">10岁以上</option><option value="adult">成人</option>
      </select>
      <label style="font-size:11px;color:#888;display:block;margin-bottom:4px">故事内容</label>
      <textarea id="bk-story" rows="8" placeholder="输入故事内容或点击'AI生成故事'让系统自动创作..." style="width:100%;padding:8px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin-bottom:10px;resize:vertical"></textarea>
      <button onclick="generateBook()" style="width:100%;padding:10px;background:#5d2d6d;color:#e0e0ff;border:none;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:6px">🤖 AI生成故事</button>
      <button onclick="produceBook()" id="bk-produce" style="width:100%;padding:10px;background:#2d5d3d;color:#e0e0ff;border:none;border-radius:6px;cursor:pointer;font-size:13px">🚀 一键生成绘本</button>
      <div id="bk-progress" style="margin-top:8px;display:none">
        <div style="font-size:11px;color:#888;margin-bottom:4px">生成进度</div>
        <div style="height:6px;background:#1a1a2e;border-radius:3px"><div id="bk-bar" style="height:100%;width:0%;background:#5d2d6d;border-radius:3px;transition:width .3s"></div></div>
        <div id="bk-status" style="font-size:10px;color:#666;margin-top:4px"></div>
      </div>
    </div>
    <div id="bk-preview" style="background:#0f0f1a;border-radius:10px;padding:16px;overflow-y:auto;border:1px solid #2a2a4a;display:flex;flex-wrap:wrap;gap:12px;align-content:flex-start">
      <div style="color:#888;font-size:13px;text-align:center;width:100%;margin-top:40%">点击"一键生成绘本"开始创作</div>
    </div>
    <div style="background:#1a1a2e;border-radius:10px;padding:14px;overflow-y:auto;border:1px solid #2a2a4a">
      <h3 style="font-size:14px;color:#ccc;margin:0 0 8px">📋 页面列表</h3>
      <div id="bk-pagelist" style="font-size:11px;color:#888">等待生成...</div>
      <div style="margin-top:12px;padding-top:8px;border-top:1px solid #2a2a4a">
        <div style="font-size:11px;color:#666">导出格式</div>
        <select id="bk-export" style="width:100%;padding:6px;background:#0f0f1a;border:1px solid #333;color:#ccc;border-radius:4px;margin:6px 0">
          <option>PDF</option><option>EPUB</option><option>HTML</option><option>PNG序列</option>
        </select>
        <button onclick="exportBook()" style="width:100%;padding:8px;background:#3d3d5d;color:#ccc;border:none;border-radius:4px;cursor:pointer;font-size:12px">📥 导出绘本</button>
      </div>
    </div>
  </div>`;

  window.generateBook = async function() {
    const story = document.getElementById('bk-story').value;
    const style = document.getElementById('bk-style').value;
    const status = document.getElementById('bk-status') || { textContent: '' };
    try {
      status.textContent = '📡 AI生成中...';
      const r = await apiPost('/api/chat',{messages:[{role:'user',content:`请为绘本创作一个${style}风格的短故事,${document.getElementById('bk-pages').value}个段落,目标读者${document.getElementById('bk-audience').value}`}],model:'auto'});
      if (r && (r.content || r.data?.content)) {
        document.getElementById('bk-story').value = r.content || r.data.content;
        status.textContent = '✅ AI生成完成';
      } else {
        // R4-W4-others: API 真实失败时显示提示, 不再用硬编码小兔子故事兜底
        status.textContent = '⚠️ AI生成失败: ' + ((r && r.error) || '服务暂不可用') + ', 请手动输入故事';
      }
    } catch(e) {
      // R4-W4-others: 网络异常时显示提示, 不再用硬编码小兔子故事兜底
      status.textContent = '⚠️ AI生成异常: ' + (e.message || e) + ', 请手动输入故事';
    }
  };

  window.produceBook = async function() {
    const pages = parseInt(document.getElementById('bk-pages').value)||8;
    const title = document.getElementById('bk-title').value;
    const style = document.getElementById('bk-style').value;
    const story = document.getElementById('bk-story').value;
    const audience = document.getElementById('bk-audience').value;
    
    document.getElementById('bk-progress').style.display = 'block';
    document.getElementById('bk-produce').disabled = true;
    const bar = document.getElementById('bk-bar');
    const status = document.getElementById('bk-status');
    const preview = document.getElementById('bk-preview');
    const pagelist = document.getElementById('bk-pagelist');
    
    window._currentBookId = null;
    
    status.textContent = '📡 发送生成请求...';
    bar.style.width = '5%';
    
    try {
      const r = await apiPost('/api/book/generate', {
        title: title,
        story: story,
        style: style,
        pages: pages,
        audience: audience,
        generate_images: true
      });
      
      if (!r.success) {
        throw new Error(r.error || '生成失败');
      }
      
      const book = r.data;
      window._currentBookId = book.id;
      
      bar.style.width = '100%';
      status.textContent = '✅ 绘本生成完成!';
      
      // 渲染预览
      preview.innerHTML = '';
      const colors = ['#4a3a5a','#3a4a5a','#3a5a4a','#5a4a3a','#4a5a3a','#5a3a4a'];
      const emojis = ['🐰','🌈','🦊','🐻','🦉','🌟','🦋','🌺'];
      
      (book.pages || []).forEach((page, i) => {
        const bg = colors[i % colors.length];
        const emoji = emojis[i % emojis.length];
        const imgTag = page.image_url 
          ? `<img src="${page.image_url}" style="width:100%;height:60%;object-fit:cover;border-radius:6px;margin-bottom:6px" onerror="this.style.display='none'">`
          : `<div style="font-size:48px;margin-bottom:8px">${emoji}</div>`;
        
        preview.insertAdjacentHTML('beforeend', 
          `<div style="width:calc(33% - 8px);min-width:160px;aspect-ratio:3/4;background:${bg};border-radius:8px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;padding:8px;border:1px solid #3a3a5a;overflow:hidden">
            ${imgTag}
            <div style="font-size:11px;color:#ccc;text-align:center;font-weight:600">第${page.page_num}页</div>
            <div style="font-size:9px;color:#888;text-align:center;margin-top:2px;line-height:1.4">${(page.text||'').substring(0,50)}</div>
          </div>`
        );
      });
      
      // 更新页面列表
      pagelist.innerHTML = (book.pages || []).map((page, i) => 
        `<div style="padding:4px 6px;margin:2px 0;font-size:11px;color:#ccc;border-left:2px solid #5d2d6d;padding-left:8px">
          📄 第${page.page_num}页 — ${(page.text||'').substring(0,20)}...
          <span style="color:${page.image_url?'#5d5':'#888'};font-size:9px">${page.image_url?'🖼️':'⏳'}</span>
        </div>`
      ).join('');
      
      document.getElementById('bk-produce').disabled = false;
      setTimeout(()=>{ document.getElementById('bk-progress').style.display='none'; },3000);
      
    } catch(e) {
      status.textContent = '❌ 生成失败: ' + (e.message || e);
      bar.style.width = '100%';
      bar.style.background = '#8B0000';
      console.error('Book generation error:', e);
      document.getElementById('bk-produce').disabled = false;
      setTimeout(()=>{ document.getElementById('bk-progress').style.display='none'; },5000);
    }
  };

  window.exportBook = function() {
    const format = (document.getElementById('bk-export')?.value || 'HTML').toLowerCase();
    const bookId = window._currentBookId;
    if (!bookId) {
      (window.toastError || ((m) => alert(m)))('请先生成绘本');
      return;
    }
    // 浏览器直接下载
    window.open(`/api/book/${bookId}/export?format=${format}`, '_blank');
  };
}
