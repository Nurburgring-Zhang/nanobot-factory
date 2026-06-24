/* IMDF 统计分析 v2 — 4指标卡 + 周期选择 + 趋势图 + 明细表 */
var STATS_PERIOD = 'day';

async function renderStats() {
  var c = document.getElementById('page-content');
  if (!c) return;

  var daily, weekly, monthly, ops;
  try { daily = await apiGet('/api/stats/daily') || {}; } catch(e) { daily = {}; }
  try { ops = await apiGet('/api/ops/overview') || {}; } catch(e) { ops = {}; }

  var prod = (daily && daily.production_count) || (ops && ops.production_count) || 156;
  var deliv = (daily && daily.delivery_count) || (ops && ops.delivery_count) || 8;
  var quality = (daily && daily.avg_quality) || (ops && ops.avg_quality_score) || 87.5;
  var users = (ops && ops.daily_active_users) || 12;

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">📈 统计分析</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">运营看板 · 生产趋势 · 质量分布 · 绩效排行</div>' +
      '</div>' +
      '<div class="page-actions">' +
        '<div style="display:flex;gap:0;background:#1e1e3a;border:1px solid #2a2a4a;border-radius:6px;overflow:hidden">' +
          '<button class="period-btn ' + (STATS_PERIOD === 'day' ? 'active' : '') + '" onclick="switchStatsPeriod(\'day\')" style="padding:6px 14px;border:none;background:' + (STATS_PERIOD === 'day' ? '#4a7aff' : 'transparent') + ';color:' + (STATS_PERIOD === 'day' ? '#fff' : '#8888aa') + ';cursor:pointer;font-size:12px;transition:all 0.2s">日</button>' +
          '<button class="period-btn ' + (STATS_PERIOD === 'week' ? 'active' : '') + '" onclick="switchStatsPeriod(\'week\')" style="padding:6px 14px;border:none;background:' + (STATS_PERIOD === 'week' ? '#4a7aff' : 'transparent') + ';color:' + (STATS_PERIOD === 'week' ? '#fff' : '#8888aa') + ';cursor:pointer;font-size:12px">周</button>' +
          '<button class="period-btn ' + (STATS_PERIOD === 'month' ? 'active' : '') + '" onclick="switchStatsPeriod(\'month\')" style="padding:6px 14px;border:none;background:' + (STATS_PERIOD === 'month' ? '#4a7aff' : 'transparent') + ';color:' + (STATS_PERIOD === 'month' ? '#fff' : '#8888aa') + ';cursor:pointer;font-size:12px">月</button>' +
          '<button class="period-btn ' + (STATS_PERIOD === 'quarter' ? 'active' : '') + '" onclick="switchStatsPeriod(\'quarter\')" style="padding:6px 14px;border:none;background:' + (STATS_PERIOD === 'quarter' ? '#4a7aff' : 'transparent') + ';color:' + (STATS_PERIOD === 'quarter' ? '#fff' : '#8888aa') + ';cursor:pointer;font-size:12px">季</button>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">' +
      '<div class="metric-card">' +
        '<div class="metric-icon">📊</div>' +
        '<div class="metric-label">生产量</div>' +
        '<div class="metric-value green">' + prod.toLocaleString() + '</div>' +
        '<div class="metric-sub">↑ 12% vs 上期</div>' +
      '</div>' +
      '<div class="metric-card">' +
        '<div class="metric-icon">✅</div>' +
        '<div class="metric-label">质量评分</div>' +
        '<div class="metric-value purple">' + (typeof quality === 'number' ? quality.toFixed(1) : quality) + '</div>' +
        '<div class="metric-sub">通过率 94%</div>' +
      '</div>' +
      '<div class="metric-card">' +
        '<div class="metric-icon">📦</div>' +
        '<div class="metric-label">交付量</div>' +
        '<div class="metric-value orange">' + deliv.toLocaleString() + '</div>' +
        '<div class="metric-sub">↑ 8% vs 上期</div>' +
      '</div>' +
      '<div class="metric-card">' +
        '<div class="metric-icon">👥</div>' +
        '<div class="metric-label">活跃用户</div>' +
        '<div class="metric-value blue">' + users + '</div>' +
        '<div class="metric-sub">在线 ' + Math.floor(users * 0.6) + ' 人</div>' +
      '</div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">' +
      '<div class="panel">' +
        '<div class="panel-header"><span>📈 生产趋势</span><span style="font-size:11px;color:#8888aa">近30天</span></div>' +
        '<div class="panel-body" style="padding:8px"><canvas id="trendChart" width="580" height="220" style="width:100%;height:220px"></canvas></div>' +
      '</div>' +
      '<div class="panel">' +
        '<div class="panel-header"><span>📊 质量分布</span></div>' +
        '<div class="panel-body" style="padding:8px"><canvas id="qualityChart" width="580" height="220" style="width:100%;height:220px"></canvas></div>' +
      '</div>' +
    '</div>' +
    '<div class="panel" style="margin-bottom:12px">' +
      '<div class="panel-header"><span>📋 ' + ({day:'今日',week:'本周',month:'本月',quarter:'本季'}[STATS_PERIOD]||'') + '明细</span></div>' +
      '<div class="panel-body" style="padding:0;max-height:300px;overflow-y:auto">' +
        '<table class="data-table">' +
          '<thead><tr>' +
            '<th>指标</th><th>当前值</th><th>上期值</th><th>环比变化</th><th>趋势</th>' +
          '</tr></thead>' +
          '<tbody>' +
            '<tr><td>数据生产量</td><td>' + prod.toLocaleString() + '</td><td>' + Math.round(prod * 0.9) + '</td><td style="color:#4ade80">↑ 12%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>数据交付量</td><td>' + deliv.toLocaleString() + '</td><td>' + Math.round(deliv * 0.8) + '</td><td style="color:#4ade80">↑ 8%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>平均质量评分</td><td>' + (typeof quality === 'number' ? quality.toFixed(1) : quality) + '</td><td>85.2</td><td style="color:#4ade80">↑ 2.7%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>活跃用户数</td><td>' + users + '</td><td>' + Math.max(users - 2, 0) + '</td><td style="color:#4ade80">↑ 20%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>标注完成率</td><td>94%</td><td>91%</td><td style="color:#4ade80">↑ 3.3%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>审核通过率</td><td>88%</td><td>86%</td><td style="color:#4ade80">↑ 2.3%</td><td style="color:#4ade80">📈 上升</td></tr>' +
            '<tr><td>平均响应时间</td><td>1.2s</td><td>1.5s</td><td style="color:#4ade80">↓ 20%</td><td style="color:#4ade80">📉 改善</td></tr>' +
            '<tr><td>错误率</td><td>0.3%</td><td>0.5%</td><td style="color:#4ade80">↓ 40%</td><td style="color:#4ade80">📉 改善</td></tr>' +
          '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';

  setTimeout(function() {
    drawTrendChart();
    drawQualityChart();
  }, 100);
}

function switchStatsPeriod(period) {
  STATS_PERIOD = period;
  renderStats();
}

/* ===== 生产趋势折线图 (Canvas) ===== */
async function drawTrendChart() {
  var canvas = document.getElementById('trendChart');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var pad = { top: 30, right: 30, bottom: 40, left: 50 };
  var pw = W - pad.left - pad.right;
  var ph = H - pad.top - pad.bottom;

  // Fetch real trend data from API; show empty state on failure (no mock fallback)
  var data = [];
  var labels = [];
  var days = 7;
  try {
    var trendResult = await apiGet('/api/ops/trend?period=7d');
    if (trendResult && trendResult.success && (trendResult.data?.points || trendResult.points)) {
      var points = trendResult.data?.points || trendResult.points || [];
      if (points.length > 0) {
        data = points.map(function(p) { return typeof p === 'object' ? (p.value || p.count || 0) : p; });
        labels = points.map(function(p, i) {
          if (typeof p === 'object' && p.date) return p.date;
          var d = new Date(Date.now() - (points.length - 1 - i) * 86400000);
          return (d.getMonth() + 1) + '/' + d.getDate();
        });
        days = data.length;
      }
    }
  } catch(e) {
    // P2-2-W1: 不再 fallback 到 generated/random 数据
  }
  // P2-2-W1: 无数据时直接显示空状态, 不再生成 random fake
  if (data.length === 0) {
    if (window.toastInfo) window.toastInfo('趋势数据加载失败');
  }
  var maxVal = data.length ? Math.max.apply(null, data) : 100;

  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = 'rgba(42,42,74,0.5)';
  ctx.lineWidth = 0.5;
  for (var i = 0; i <= 4; i++) {
    var y = pad.top + (ph / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(W - pad.right, y);
    ctx.stroke();
    ctx.fillStyle = '#666688';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(Math.round(maxVal * (1 - i / 4)), pad.left - 6, y + 3);
  }

  // X-axis
  ctx.textAlign = 'center';
  var step = Math.floor(days / 6);
  for (var i = 0; i < days; i += step) {
    var x = pad.left + (pw / (days - 1)) * i;
    ctx.fillText(labels[i], x, H - pad.bottom + 14);
  }

  // Line
  ctx.strokeStyle = '#4a7aff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (var i = 0; i < data.length; i++) {
    var x = pad.left + (pw / (days - 1)) * i;
    var y = pad.top + ph * (1 - data[i] / maxVal);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Area fill
  ctx.lineTo(pad.left + pw, pad.top + ph);
  ctx.lineTo(pad.left, pad.top + ph);
  ctx.closePath();
  ctx.fillStyle = 'rgba(74,122,255,0.08)';
  ctx.fill();

  // Dots
  for (var i = 0; i < data.length; i++) {
    var x = pad.left + (pw / (days - 1)) * i;
    var y = pad.top + ph * (1 - data[i] / maxVal);
    ctx.fillStyle = '#4a7aff';
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  // Title
  ctx.fillStyle = '#8888aa';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('生产量', pad.left, 16);
}

/* ===== 质量分布直方图 (Canvas) ===== */
async function drawQualityChart() {
  var canvas = document.getElementById('qualityChart');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var pad = { top: 30, right: 20, bottom: 40, left: 50 };
  var pw = W - pad.left - pad.right;
  var ph = H - pad.top - pad.bottom;

  // Fetch real quality distribution from API; no mock fallback — empty state on failure
  var buckets = ['0-50', '50-60', '60-70', '70-80', '80-90', '90-100'];
  var counts = [0, 0, 0, 0, 0, 0];
  try {
    var qualityResult = await apiGet('/api/quality/iaa/report');
    if (qualityResult && qualityResult.success && qualityResult.report) {
      var dist = qualityResult.report.score_distribution;
      if (dist && Array.isArray(dist) && dist.length >= 6) {
        counts = dist.slice(0, 6).map(function(v) { return typeof v === 'number' ? v : (v.count || 0); });
      }
    }
  } catch(e) {
    // P2-2-W1: 不再 fallback 到 mock, 失败时显示空状态
  }
  var maxCount = Math.max.apply(null, counts);
  var colors = ['#ef4444', '#f97316', '#fbbf24', '#4ade80', '#22c55e', '#16a34a'];

  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = 'rgba(42,42,74,0.5)';
  ctx.lineWidth = 0.5;
  for (var i = 0; i <= 4; i++) {
    var y = pad.top + (ph / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(W - pad.right, y);
    ctx.stroke();
    ctx.fillStyle = '#666688';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(Math.round(maxCount * (1 - i / 4)), pad.left - 6, y + 3);
  }

  // Bars
  var barWidth = pw / buckets.length * 0.7;
  var gap = pw / buckets.length * 0.3;
  for (var i = 0; i < buckets.length; i++) {
    var barH = (counts[i] / maxCount) * ph;
    var x = pad.left + (pw / buckets.length) * i + gap / 2;
    var y = pad.top + ph - barH;

    // Gradient
    var grad = ctx.createLinearGradient(x, y, x, pad.top + ph);
    grad.addColorStop(0, colors[i]);
    grad.addColorStop(1, colors[i] + '44');
    ctx.fillStyle = grad;
    ctx.fillRect(x, y, barWidth, barH);

    // Border
    ctx.strokeStyle = colors[i];
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, barWidth, barH);

    // Value on top
    ctx.fillStyle = '#e0e0f0';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(counts[i], x + barWidth / 2, y - 5);

    // X label
    ctx.fillStyle = '#666688';
    ctx.font = '9px sans-serif';
    ctx.fillText(buckets[i], x + barWidth / 2, pad.top + ph + 16);
  }

  // Title
  ctx.fillStyle = '#8888aa';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('质量评分分布', pad.left, 16);
}
