/* vidforge wizard — vanilla JS, no build step. State: raw project.json (editable), P (server view). */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (s) => s == null ? '–' : (s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${s.toFixed(1)} s`);
const fileUrl = (rel, bust) => rel ? `/files/${rel.split('/').map(encodeURIComponent).join('/')}${bust ? '?t=' + bust : ''}` : null;

let P = null, raw = null, lang = new URLSearchParams(location.search).get('lang');
let step = parseInt(new URLSearchParams(location.search).get('step') || localStorage.getItem('vf.step') || '0', 10);
let H = null; // health
let selSeg = null, saveTimer = null, pollTimer = null, picker = { tab: 'search', source: 'pexels', kind: 'image', q: '', page: 1, cands: [], loading: false, err: null };

const api = async (url, body) => {
  const r = await fetch(url, body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || r.statusText); e.data = j; throw e; }
  return j;
};
const isBase = () => lang === P.base_lang;
const textKey = () => isBase() ? 'text' : `text_${lang}`;
const labelKey = () => isBase() ? 'label' : `label_${lang}`;
const variant = () => { raw.variants = raw.variants || {}; raw.variants[lang] = raw.variants[lang] || {}; return raw.variants[lang]; };
const topGet = (k) => isBase() ? raw[k] : (variant()[k] ?? raw[k]);
const topSet = (k, v) => { if (isBase()) raw[k] = v; else variant()[k] = v; markDirty(); };
const nestedGet = (k, sub) => isBase() ? (raw[k] || {})[sub] : ((variant()[k] || {})[sub] ?? (raw[k] || {})[sub]);
const nestedSet = (k, sub, v) => { const o = isBase() ? (raw[k] = raw[k] || {}) : (variant()[k] = variant()[k] || {}); o[sub] = v; markDirty(); };
const segClips = (s) => {
  if (Array.isArray(s.clips)) return s.clips;
  const c = {};
  for (const k of ['image', 'video', 'remotion']) if (k in s) c[k] = s[k];
  if (!Object.keys(c).length) return [];
  if (s.motion) c.motion = s.motion;
  return [c];
};
const normalizeSeg = (s) => { // migrate legacy single-visual to clips in place
  if (!Array.isArray(s.clips)) { s.clips = segClips(s); delete s.image; delete s.video; delete s.remotion; delete s.motion; }
  return s;
};

/* ---------------- load / save ---------------- */
async function load() {
  P = await api(`/api/project?lang=${encodeURIComponent(lang || '')}`);
  raw = P.raw; lang = P.lang;
  $('#path').textContent = P.root;
  $('#lang').innerHTML = P.langs.map(l => `<option ${l === lang ? 'selected' : ''}>${l}</option>`).join('');
  $('#issues').innerHTML = P.issues ? `<div class="banner err">⚠ ${esc(P.issues)}</div>` : '';
  if (!H) await refreshHealth();
  if (!step) { const d = stepStatus(); step = (d.findIndex(x => !x) + 1) || 4; }   // first open: land on the first unfinished step
  render();
}
async function refreshHealth() {
  try {
    const h = await api('/api/health'); H = h;
    if (!h.keys.PEXELS_API_KEY && picker.source === 'pexels' && !picker.cands.length) picker.source = h.keys.PIXABAY_API_KEY ? 'pixabay' : 'commons';
    const dot = (ok, label, title) => `<span title="${esc(title || '')}"><span class="dot ${ok ? 'ok' : 'err'}"></span>${label}</span>`;
    $('#health').innerHTML = dot(h.ffmpeg.ok, `ffmpeg · ${h.encoder}`, h.ffmpeg.path) + dot(h.keys.PEXELS_API_KEY, 'Pexels', 'PEXELS_API_KEY') +
      dot(h.keys.PIXABAY_API_KEY, 'Pixabay', 'PIXABAY_API_KEY') + dot(true, 'Commons', '无需 key') +
      dot(h.node && h.remotion, '动画', h.node ? (h.remotion ? 'Remotion 已安装' : '需 vidforge remotion setup') : '需要 Node.js') +
      dot(h.youtube_secret, 'YouTube', 'client_secret.json');
  } catch { }
}
function markDirty(rerender = false) {
  $('#saveState').textContent = '未保存…'; $('#saveState').className = 'pill';
  clearTimeout(saveTimer); saveTimer = setTimeout(save, 700);
  if (rerender) render();
}
async function save() {
  clearTimeout(saveTimer);
  try { await api('/api/project', { raw }); $('#saveState').textContent = '已保存'; $('#saveState').className = 'pill ok'; $('#issues').innerHTML = ''; return true; }
  catch (e) { $('#saveState').textContent = '未保存'; $('#saveState').className = 'pill err'; $('#issues').innerHTML = `<div class="banner err">⚠ 未保存：${esc(e.message)}</div>`; return false; }
}
async function saveAndReload() { if (await save()) await load(); }

/* ---------------- steps ---------------- */
function setStep(n) { step = Math.max(1, Math.min(5, n)); localStorage.setItem('vf.step', step); render(); }
$('#steps').onclick = e => { const b = e.target.closest('button'); if (b) setStep(+b.dataset.step); };
$('#prev').onclick = () => setStep(step - 1);
$('#next').onclick = () => setStep(step + 1);
$('#lang').onchange = e => { lang = e.target.value; history.replaceState(null, '', `?lang=${lang}`); load(); };

function stepStatus() {
  const segs = raw.segments || [];
  const res = P.resolved || {};
  const scripted = segs.length > 0 && segs.every(s => (s[textKey()] || '').trim());
  const voiced = segs.length > 0 && segs.every(s => res[s.id]?.audio && res[s.id]?.audio_fresh);
  const visual = segs.length > 0 && segs.every(s => segClips(s).length > 0);
  const rendered = !!P.outputs.final;
  return [scripted, voiced, visual, rendered, !!P.outputs.youtube];
}
function render() {
  const done = stepStatus();
  $$('#steps button').forEach((b, i) => { b.classList.toggle('active', i + 1 === step); b.classList.toggle('done', done[i] && i + 1 !== step); });
  $('#prev').disabled = step === 1; $('#next').style.visibility = step === 5 ? 'hidden' : 'visible';
  $('#tour').innerHTML = localStorage.getItem('vf.tour') ? '' : `<div class="banner info">第一次用？流程就是顶上五步：<b>写脚本 → 配音试听 → 每段挑画面 → 渲染 → 发布</b>。每一步只做一件事，右下角「下一步」。所有改动自动保存到 project.json。 <button class="small" onclick="localStorage.setItem('vf.tour','1');render()">知道了</button></div>`;
  const v = $('#view');
  ({ 1: viewScript, 2: viewVoice, 3: viewVisuals, 4: viewRender, 5: viewPublish })[step](v);
  renderChecks();
}

/* ---------------- best-practice checks (docs/best-practices.md; thresholds in best_practices.json) ---------------- */
let BP = null;
fetch('/static/best_practices.json').then(r => r.json()).then(j => { BP = j; renderChecks(); }).catch(() => {});
const wordsOf = t => (t || '').trim() ? (t.match(/[\u4e00-\u9fff]/g) || []).length > (t.length * 0.3) ? { n: (t.match(/[\u4e00-\u9fff]/g) || []).length, cjk: true } : { n: t.trim().split(/\s+/).length, cjk: false } : { n: 0, cjk: false };
const secondsOf = t => { const w = wordsOf(t); return w.cjk ? w.n / (BP?.cjk_per_second || 3.8) : w.n / (BP?.words_per_second || 2.6); };
function checks() {
  if (!BP || !raw) return [];
  const out = [], segs = raw.segments || [], res = P.resolved || {};
  const tk = textKey();
  if (step === 1 && segs.length) {
    const hook = segs[0][tk] || ''; const w = wordsOf(hook);
    if ((w.cjk && w.n > BP.hook_max_cjk) || (!w.cjk && w.n > BP.hook_max_words)) out.push(`B1 钩子太长：第一段 ${w.n} ${w.cjk ? '字' : '词'}（≤ ${w.cjk ? BP.hook_max_cjk + ' 字' : BP.hook_max_words + ' 词'} ≈ 30 秒）——观众 30 秒内要知道为什么看下去`);
    if (!/[0-9０-９一二三四五六七八九十百千万亿]|\?|？/.test(hook)) out.push('B1 钩子里没有数字、问题或反差——试试用一个具体数字或问题开场');
    const long = segs.filter(s => secondsOf(s[tk]) > BP.segment_max_seconds).map(s => s.id);
    if (long.length) out.push(`B3 这些段超过 ${BP.segment_max_seconds} 秒，建议拆开：${long.join(', ')}`);
    const total = segs.reduce((a, s) => a + secondsOf(s[tk]) + 0.5, 0) / 60;
    if (total < BP.total_minutes_range[0]) out.push(`B6 预计总长 ${total.toFixed(1)} 分钟，历史/科普长视频 ${BP.total_minutes_range[0]}–${BP.total_minutes_range[1]} 分钟更稳（Shorts 另做）`);
    if (total > BP.total_minutes_range[1]) out.push(`B6 预计总长 ${total.toFixed(1)} 分钟，超过 ${BP.total_minutes_range[1]} 分钟考虑拆成两集`);
    const chapters = segs.filter(s => s[labelKey()] || s.label).length;
    if (segs.length >= BP.chapter_every_segments && chapters < Math.floor(segs.length / BP.chapter_every_segments)) out.push(`B5 章节名太少（${chapters}）：每 ${BP.chapter_every_segments} 段左右给一个章节名，YouTube 章节和标题卡都用它`);
    const tt = topGet('thumbnail_text') || ''; const tw = wordsOf(tt.replace(/\n/g, ' '));
    if (tt && ((tw.cjk && tw.n > BP.thumbnail_max_cjk) || (!tw.cjk && tw.n > BP.thumbnail_max_words))) out.push(`C3 封面文字太多（${tw.n}）：≤ ${tw.cjk ? BP.thumbnail_max_cjk + ' 字' : BP.thumbnail_max_words + ' 词'}，且与标题互补不重复`);
  }
  if (step === 3 && segs.length) {
    const slow = segs.filter(s => { const cl = segClips(s); const sec = (res[s.id]?.need) || secondsOf(s[tk]); return cl.length === 1 && cl[0].image && sec > BP.visual_change_seconds * 2.5; }).map(s => s.id);
    if (slow.length) out.push(`B4 这些段 30 秒以上只有一张图，画面应每 ${BP.visual_change_seconds} 秒左右变化一次：${slow.join(', ')}——加片段或换成视频`);
    const custom = segs.reduce((a, s) => a + segClips(s).filter(c => c.remotion).length, 0);
    if (custom < BP.min_custom_visuals && !raw.auto_title_cards) out.push(`A2 自制画面只有 ${custom} 个（建议 ≥ ${BP.min_custom_visuals}：时间轴/图表/标题卡），或在第 4 步开「章节标题卡」——这是审核可见的原创增值`);
  }
  if (step === 5) {
    const title = nestedGet('youtube', 'title') || topGet('title') || '';
    if (title.length > BP.title_max_chars) out.push(`C1 标题 ${title.length} 字符，移动端 ${BP.title_max_chars} 后截断`);
    const cb = BP.clickbait_words.filter(w => title.toLowerCase().includes(w.toLowerCase()));
    if (cb.length) out.push(`C1 标题含易被限流的词：${cb.join('、')}`);
    const tags = nestedGet('youtube', 'tags') || [];
    if (tags.length < BP.tags_range[0]) out.push(`C5 标签 ${tags.length} 个，建议 ${BP.tags_range[0]}–${BP.tags_range[1]} 个（2 个宽词 + 长尾）`);
    if (!(nestedGet('youtube', 'description') || '').trim()) out.push('C4 简介为空：前两行要含核心关键词，再列来源（A5）');
    out.push('A6 披露：YouTube 仅在有"看似真实的合成人物/事件"时勾选合成内容；发国内平台请在简介注明"内容含 AI 生成"（2025-09-01 法规）');
  }
  return out;
}
function renderChecks() {
  const host = $('#checks') || (() => { const d = document.createElement('div'); d.id = 'checks'; $('#issues').after(d); return d; })();
  const items = checks();
  host.innerHTML = items.length ? `<details class="banner info" open><summary>规范检查（${items.length}）· 依据 docs/best-practices.md</summary><ul style="margin:6px 0 0 18px">${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></details>` : '';
}

/* ---------------- 1 script ---------------- */
function viewScript(v) {
  const segs = raw.segments || [];
  v.innerHTML = `
  <div class="card">
    <div class="grid2">
      <div><label class="muted">视频标题</label><input id="f_title" value="${esc(topGet('title') || '')}"></div>
      <div><label class="muted">封面文字（\\n 换行）</label><input id="f_thumb" value="${esc((topGet('thumbnail_text') || '').replace(/\n/g, '\\n'))}"></div>
    </div>
  </div>
  <div class="card">
    <div class="row" style="justify-content:space-between"><b>段落（${segs.length}）</b>
      <span><button class="small" id="addSeg">＋ 添加一段</button> <button class="small" id="togglePaste">${segs.length ? '从整篇脚本重新拆段…' : ''}</button></span></div>
    <p class="hint">一段 = 一个画面（或几个片段）+ 讲这段时说的话。旁白<b>按口语写、短句、标点齐全</b>——标点决定字幕断行和停顿。${isBase() ? '' : `<span class="warn">当前编辑的是 <b>${lang}</b> 版旁白；空着的段会用红框提示。</span>`}</p>
    <details id="topicPanel"><summary>🔎 选题助手：看 YouTube 上同类视频的数据，让 AI 判断值不值得做、用什么视角</summary>
      <div class="row" style="margin-top:6px"><input id="t_q" class="grow" placeholder="候选主题，例：year without a summer 1816" value="${esc(topGet('title') || '')}"><input id="t_pos" class="grow" placeholder="频道定位（可选），例：英文历史解说，15 分钟长视频"><button id="t_search">看同类视频</button></div>
      <div id="t_table"></div>
      <div class="row" id="t_actions" hidden><select id="t_site"></select><button class="primary" id="t_ai">让 AI 评估（我的浏览器）</button><button id="t_copy">只复制提示词</button><span class="muted" id="t_status"></span></div>
      <div id="t_result"></div>
    </details>
    <div id="paste" ${segs.length ? 'hidden' : ''}>
      <details id="genPanel" ${segs.length ? '' : 'open'}><summary>✨ 用我的浏览器里的 AI 生成脚本（ChatGPT / Claude / Gemini / DeepSeek / Grok / 千问 / Kimi / 文心）</summary>
        <div class="grid2" style="margin-top:6px">
          <div><label class="muted">主题 / 标题</label><input id="g_topic" value="${esc(topGet('title') || '')}"></div>
          <div><label class="muted">目标时长（分钟）</label><input id="g_minutes" type="number" min="1" max="60" value="10"></div>
          <div><label class="muted">受众 / 语气</label><input id="g_audience" placeholder="例：对历史感兴趣的普通观众，轻松但准确"></div>
          <div><label class="muted">用哪个网站</label><select id="g_site"></select></div>
        </div>
        <label class="muted">要点 / 参考资料（可选，越具体越好）</label>
        <textarea id="g_points" rows="4" placeholder="- 1815 年 4 月坦博拉喷发&#10;- 1816 年欧洲北美夏季异常&#10;- 玛丽·雪莱与《弗兰肯斯坦》"></textarea>
        <div class="row">
          <button class="primary" id="g_go">在我的浏览器里生成</button>
          <button id="g_copy">只复制提示词（我自己去贴）</button>
          <button class="small" id="g_login">登录各站点…</button>
          <span class="muted" id="g_status"></span>
        </div>
        <p class="hint">会打开一个专用的 Edge 窗口（第一次点「登录各站点」登录一次即可）。生成期间不要在那个窗口里操作；遇到验证码就手动点一下。回答会自动填入下面的文本框，再点「拆成段落」。</p>
      </details>
      <textarea id="script" rows="10" placeholder="把整篇脚本贴在这里，一段一空行；每段 2–4 句最合适。&#10;&#10;第一行如果以 # 开头会成为该段的章节名。"></textarea>
      <div class="row"><button class="primary" id="splitBtn">拆成段落</button><span class="muted" id="splitInfo"></span></div>
    </div>
    <div class="seglist" id="seglist">
      <div class="seg-row muted" style="border:0"><span>id</span><span>章节名（可选）</span><span>旁白</span><span></span></div>
      ${segs.map((s, i) => `
      <div class="seg-row" data-i="${i}">
        <input data-k="id" value="${esc(s.id)}">
        <input data-k="${labelKey()}" value="${esc(s[labelKey()] || '')}" placeholder="${isBase() ? '' : esc(s.label || '')}">
        <textarea data-k="${textKey()}" style="${(s[textKey()] || '').trim() ? '' : 'border-color:var(--err)'}" placeholder="${isBase() ? '这一段的旁白' : esc(s.text)}">${esc(s[textKey()] || '')}</textarea>
        <div class="ops"><button class="small" data-act="up" ${i === 0 ? 'disabled' : ''}>↑</button><button class="small" data-act="down" ${i === segs.length - 1 ? 'disabled' : ''}>↓</button><button class="small" data-act="del">✕</button></div>
      </div>`).join('')}
    </div>
  </div>`;
  $('#f_title').oninput = e => topSet('title', e.target.value);
  $('#f_thumb').oninput = e => topSet('thumbnail_text', e.target.value.replace(/\\n/g, '\n'));
  $('#addSeg').onclick = () => { raw.segments.push({ id: newId(), text: isBase() ? '' : '(en)', [textKey()]: '', clips: [] }); markDirty(true); };
  $('#togglePaste').onclick = () => { $('#paste').hidden = !$('#paste').hidden; };
  // ---- topic research
  let tVideos = [];
  $('#t_search').onclick = async () => {
    const qv = $('#t_q').value.trim(); if (!qv) return;
    $('#t_table').innerHTML = '<span class="muted">正在读取 YouTube…</span>';
    try {
      const j = await api(`/api/research/youtube?q=${encodeURIComponent(qv)}&n=20`); tVideos = j.videos;
      const s = j.summary;
      $('#t_table').innerHTML = `<p class="hint">${j.source === 'api' ? '数据来自 YouTube Data API' : '数据来自 YouTube 搜索页（无 key，近似值；设 YOUTUBE_API_KEY 可得精确统计）'} · ${s.count} 条 · 中位播放 ${(s.median_views || 0).toLocaleString()} · 近 12 个月新发 ${s.recent_12m} 条（中位 ${(s.recent_median_views || 0).toLocaleString()}） · ≥8 分钟占 ${Math.round((s.long_form_share || 0) * 100)}% · 中位时长 ${s.median_duration_min} 分</p>
        <div style="max-height:260px;overflow:auto"><table class="yt"><tr><th>播放</th><th>每天</th><th>年龄</th><th>时长</th><th>频道</th><th>标题</th></tr>
        ${j.videos.sort((a, b) => b.views - a.views).map(v => `<tr><td>${v.views.toLocaleString()}</td><td>${v.views_per_day ?? '–'}</td><td>${v.age_days != null ? Math.round(v.age_days / 30) + ' 月' : '–'}</td><td>${v.duration_s ? fmt(v.duration_s) : '–'}</td><td>${esc(v.channel)}</td><td><a href="${esc(v.url)}" target="_blank">${esc(v.title)}</a></td></tr>`).join('')}</table></div>`;
      $('#t_actions').hidden = false;
      if (!$('#t_site').children.length) { const st = await api('/api/chat/sites'); $('#t_site').innerHTML = st.sites.map(x => `<option value="${x.id}" ${x.id === (localStorage.getItem('vf.site') || 'deepseek') ? 'selected' : ''}>${esc(x.label)}</option>`).join(''); }
    } catch (e) { $('#t_table').innerHTML = `<div class="banner err">${esc(e.message)}</div>`; }
  };
  const tBody = () => ({ q: $('#t_q').value.trim(), positioning: $('#t_pos').value.trim(), site: $('#t_site').value });
  $('#t_copy').onclick = async () => { const j = await api(`/api/research/analyze?lang=${lang}`, { ...tBody(), prompt_only: true }); await navigator.clipboard.writeText(j.prompt); $('#t_status').textContent = '提示词已复制（含同类视频数据），贴到任意 AI。'; };
  $('#t_ai').onclick = async () => {
    localStorage.setItem('vf.site', $('#t_site').value);
    $('#t_ai').disabled = true; $('#t_status').textContent = '正在浏览器里提问，通常 30–90 秒…';
    try {
      const j = await api(`/api/research/analyze?lang=${lang}`, tBody()); const r = j.result;
      const li = (arr, f = x => esc(typeof x === 'string' ? x : JSON.stringify(x))) => (arr || []).map(x => `<li>${f(x)}</li>`).join('');
      $('#t_result').innerHTML = r.raw ? `<pre class="log">${esc(r.why)}</pre>` : `
        <div class="card" style="margin-top:8px">
          <div class="row"><span class="pill ${r.verdict === 'do' ? 'ok' : r.verdict === 'skip' ? 'err' : 'warn'}">${{ do: '值得做', do_with_angle: '换视角做', skip: '跳过' }[r.verdict] || esc(r.verdict)}</span><span class="muted">饱和度：${esc(r.saturation || '')}</span></div>
          <p>${esc(r.why || '')}</p>
          <b>差异化视角</b><ul>${li(r.angles, a => `<b>${esc(a.title || a)}</b>${a.why ? ' — ' + esc(a.why) : ''} <button class="small" data-angle="${esc(a.title || a)}">用这个视角</button>`)}</ul>
          <div class="grid2"><div><b>标题候选</b><ul>${li(r.titles, t => `${esc(t)} <button class="small" data-title="${esc(t)}">用</button>`)}</ul></div>
          <div><b>开场钩子</b><ul>${li(r.hooks)}</ul></div>
          <div><b>头部视频的优点</b><ul>${li(r.strengths_of_top)}</ul></div><div><b>没人讲的空白</b><ul>${li(r.gaps)}</ul></div>
          <div><b>封面大字</b><ul>${li(r.thumbnail_text, t => `${esc(t)} <button class="small" data-thumb="${esc(t)}">用</button>`)}</ul></div><div><b>风险</b><ul>${li(r.risks)}</ul></div></div>
        </div>`;
      $('#t_status').textContent = '';
      $('#t_result').onclick = e => {
        const b = e.target.closest('button'); if (!b) return;
        if (b.dataset.angle) { $('#g_topic').value = $('#t_q').value; $('#g_points').value = `视角：${b.dataset.angle}\n` + ($('#g_points').value || ''); $('#genPanel').open = true; $('#g_topic').scrollIntoView({ behavior: 'smooth' }); }
        if (b.dataset.title) topSet('title', b.dataset.title), $('#f_title').value = b.dataset.title;
        if (b.dataset.thumb) topSet('thumbnail_text', b.dataset.thumb), $('#f_thumb').value = b.dataset.thumb;
      };
    } catch (e) { $('#t_status').innerHTML = `<span class="err">${esc(e.message)}</span>${e.data?.prompt ? ' <button class="small" id="t_copy2">复制提示词自己去贴</button>' : ''}`; if ($('#t_copy2')) $('#t_copy2').onclick = () => navigator.clipboard.writeText(e.data.prompt); }
    $('#t_ai').disabled = false;
  };
  api('/api/chat/sites').then(j => { $('#g_site').innerHTML = j.sites.map(s => `<option value="${s.id}" ${s.id === (localStorage.getItem('vf.site') || 'deepseek') ? 'selected' : ''}>${esc(s.label)}</option>`).join(''); }).catch(() => {});
  const buildPrompt = () => {
    const zh = (isBase() ? P.base_lang : lang).startsWith('zh');
    const topic = $('#g_topic').value.trim(), mins = +$('#g_minutes').value || 10, aud = $('#g_audience').value.trim(), pts = $('#g_points').value.trim();
    const words = Math.round(mins * (zh ? 240 : 150));
    return zh
      ? `请为一条约 ${mins} 分钟的讲解类视频写完整旁白脚本。主题：${topic}。${aud ? '受众/语气：' + aud + '。' : ''}${pts ? '\n必须覆盖的要点/参考：\n' + pts + '\n' : ''}
要求：
1. 总字数约 ${words} 字，口语化、短句、标点齐全（标点决定字幕断行和停顿）。
2. 前 30 秒是钩子：用一个反差、问题或具体数字抓住观众。
3. 按内容分成 8–15 个段落，每个段落一个意思、2–4 句；每个段落前用 Markdown 二级标题写章节名（格式：## 章节名）。
4. 每个段落标题下面先写一行 "画面：" 给出适合的画面/素材描述（英文关键词 2–4 个，便于搜图），再写旁白正文。
5. 数字和年份用汉字读法或明确写法；涉及具体史实处如不确定请标注 [核实]。
6. 结尾一段是简短总结 + 引出下一集。只输出脚本本身，不要前言和解释。`
      : `Write the complete narration script for a ~${mins}-minute explainer video. Topic: ${topic}. ${aud ? 'Audience/tone: ' + aud + '.' : ''}${pts ? '\nPoints/sources that must be covered:\n' + pts + '\n' : ''}
Requirements:
1. About ${words} words, spoken style, short sentences, full punctuation (it drives subtitle breaks and pauses).
2. The first 30 seconds are a hook: a contrast, a question or a concrete number.
3. Split into 8-15 segments, one idea each, 2-4 sentences; put a Markdown level-2 heading before each (format: ## Chapter title).
4. Under each heading first write one line "Visual: <2-4 English search keywords for stock footage>", then the narration.
5. Spell out numbers the way they should be read aloud; mark uncertain facts with [verify].
6. End with a short recap and a teaser for the next episode. Output only the script, no preamble.`;
  };
  $('#g_copy').onclick = async () => { await navigator.clipboard.writeText(buildPrompt()); $('#g_status').textContent = '提示词已复制，贴到任意 AI，再把回答贴回下面的框。'; };
  $('#g_login').onclick = async () => { await api('/api/chat', { login: true }); $('#g_status').textContent = '已打开浏览器窗口：逐个登录，完成后关闭窗口。'; };
  $('#g_go').onclick = async () => {
    const site = $('#g_site').value; localStorage.setItem('vf.site', site);
    $('#g_go').disabled = true; $('#g_status').textContent = `正在 ${$('#g_site').selectedOptions[0].textContent} 里提问并等待回答（通常 30–120 秒）…`;
    try { const j = await api('/api/chat', { site, prompt: buildPrompt() }); $('#script').value = j.text; $('#g_status').textContent = `收到 ${j.text.length} 字，点「拆成段落」。`; $('#script').scrollIntoView({ behavior: 'smooth' }); }
    catch (e) { $('#g_status').innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    $('#g_go').disabled = false;
  };
  $('#splitBtn').onclick = async () => {
    const text = $('#script').value.trim(); if (!text) return;
    const j = await api('/api/script/split', { text });
    const pieces0 = j.segments; if (!pieces0.length) return;
    // preview table: label / text / words / est. seconds — accept or cancel
    const est = t => { const cjk = (t.match(/[\u4e00-\u9fff]/g) || []).length; return cjk > t.length * 0.3 ? cjk / 3.8 : t.split(/\s+/).length / 2.6; };
    const total = pieces0.reduce((a, p) => a + est(p.text), 0);
    const m = $('#modal');
    m.innerHTML = `<div class="modal"><div class="box" style="max-height:90vh;overflow:auto">
      <div class="row" style="justify-content:space-between"><b>拆分预览：${pieces0.length} 段 · 预计 ${fmt(total)}</b><button class="ghost" id="close">✕</button></div>
      <p class="hint">识别到的章节名在第一列；每段字数/预计时长在右侧。可以在这里直接改，或取消后调整原文再拆。</p>
      <div class="seglist">${pieces0.map((p, i) => `<div class="seg-row" data-i="${i}" style="grid-template-columns:150px 1fr 90px"><input data-k="label" value="${esc(p.label || '')}" placeholder="章节名"><textarea data-k="text">${esc(p.text)}</textarea><span class="muted">${p.text.split(/\s+/).length} 词<br>${fmt(est(p.text))}${p.visual_hint ? `<br title="${esc(p.visual_hint)}">🖼 画面提示` : ''}</span></div>`).join('')}</div>
      <div class="row" style="justify-content:flex-end;margin-top:8px"><button id="cancel">取消</button><button class="primary" id="ok">采用这 ${pieces0.length} 段${segs.length ? `（替换现有 ${segs.length} 段）` : ''}</button></div></div></div>`;
    $('#close').onclick = $('#cancel').onclick = () => { m.innerHTML = ''; };
    $('#ok').onclick = () => {
      const pieces = $$('.seg-row', m).map((row, i) => ({ label: row.querySelector('[data-k=label]').value.trim() || null, text: row.querySelector('[data-k=text]').value.trim(), visual_hint: pieces0[i].visual_hint })).filter(p => p.text);
      m.innerHTML = '';
      raw.segments = pieces.map((pc, i) => {
        const s = { id: `seg${i + 1}`, text: isBase() ? pc.text : '(en)', clips: [] };
        if (!isBase()) s[textKey()] = pc.text;
        if (pc.label) s[labelKey()] = pc.label;
        if (pc.visual_hint) s.visual_hint = pc.visual_hint;
        return s;
      });
      markDirty(true);
    };
    return;
  };
  $('#seglist').oninput = e => {
    const row = e.target.closest('.seg-row'); if (!row) return;
    const s = raw.segments[+row.dataset.i]; const k = e.target.dataset.k; let val = e.target.value;
    if (k === 'id') { val = val.trim().replace(/[^A-Za-z0-9_\-\u4e00-\u9fff]+/g, '_'); if (!val) return; }
    if (val === '' && k !== 'id') delete s[k]; else s[k] = val;
    markDirty();
  };
  $('#seglist').onclick = e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const i = +b.closest('.seg-row').dataset.i, a = b.dataset.act;
    if (a === 'del') { if (!confirm(`删除段「${raw.segments[i].id}」？`)) return; raw.segments.splice(i, 1); }
    if (a === 'up') raw.segments.splice(i - 1, 0, raw.segments.splice(i, 1)[0]);
    if (a === 'down') raw.segments.splice(i + 1, 0, raw.segments.splice(i, 1)[0]);
    markDirty(true);
  };
}
function newId() { let n = raw.segments.length + 1, id = `seg${n}`; while (raw.segments.some(s => s.id === id)) id = `seg${++n}`; return id; }

/* ---------------- 2 voice ---------------- */
function viewVoice(v) {
  const segs = raw.segments || [], res = P.resolved || {};
  const provider = nestedGet('tts', 'provider') || 'edge';
  v.innerHTML = `
  <div class="card">
    <div class="grid2">
      <div><label class="muted">配音服务</label><select id="f_provider">
        <option value="edge" ${provider === 'edge' ? 'selected' : ''}>edge（免费，微软神经语音）</option>
        <option value="elevenlabs" ${provider === 'elevenlabs' ? 'selected' : ''}>ElevenLabs（付费，需 key）</option>
        <option value="silent" ${provider === 'silent' ? 'selected' : ''}>静音占位（只看画面，不联网）</option></select></div>
      <div><label class="muted">声音</label><div class="row" style="margin:0"><input id="f_voice" class="grow" value="${esc(topGet('voice') || '')}" placeholder="点「浏览」按口音/性别挑"><button id="browseVoice">浏览…</button><button id="designVoice" title="用文字描述设计一个专属声音（ElevenLabs Voice Design，不克隆任何真人）">✨ 设计品牌声音…</button></div></div>
      <div><label class="muted">语速 <span id="rateVal">${esc(topGet('rate') || '+0%')}</span></label><input type="range" id="f_rate" min="-30" max="30" step="1" value="${parseInt(topGet('rate') || '0', 10) || 0}"></div>
      <div><label class="muted">试听</label><div class="row"><button id="ttsFirst">▶ 用第一段试听这个声音</button><button class="primary" id="ttsAll">全部配音</button></div></div>
    </div>
    <p class="hint">改了声音或语速后，所有段的配音都要重做（缓存按声音+文字区分，不会重复扣费同一段）。</p>
    <div id="ttsProgress" class="muted"></div>
  </div>
  <div class="card" id="voiceList2">
    ${segs.map(s => { const r = res[s.id] || {}; return `
    <div class="voice-row" data-id="${esc(s.id)}">
      <b>${esc(s.id)}</b>
      <span class="txt">${esc(s[textKey()] || '')}</span>
      <span class="audio">${r.audio ? `<audio controls preload="none" src="${fileUrl(r.audio)}?t=${r.duration}"></audio>` : '<span class="muted">尚未配音</span>'}</span>
      <span class="${r.audio_fresh ? '' : 'warn'}" title="${r.audio_fresh ? '' : '文字改过，需重新配音'}">${r.duration ? fmt(r.duration) : ''}${r.audio && !r.audio_fresh ? ' ⟳' : ''}</span>
      <span></span><span class="muted">${s.voice ? `声音：${esc(s.voice)} <button class="small" data-act="clearvoice" title="恢复全局声音">×</button>` : ''}</span><span><button class="small" data-act="tts">▶ 试听</button> <button class="small" data-act="voice" title="只给这一段换声音（引用、对话）">换声</button></span><span></span>
    </div>`; }).join('')}
  </div>`;
  $('#f_provider').onchange = e => nestedSet('tts', 'provider', e.target.value);
  $('#f_voice').oninput = e => topSet('voice', e.target.value);
  $('#browseVoice').onclick = () => openVoiceBrowser($('#f_provider').value, v => { $('#f_voice').value = v; topSet('voice', v); });
  $('#designVoice').onclick = () => {
    const m = $('#modal');
    m.innerHTML = `<div class="modal"><div class="box">
      <div class="row" style="justify-content:space-between"><b>设计品牌声音</b><button class="ghost" id="close">✕</button></div>
      <p class="hint">用文字描述想要的声音，ElevenLabs 会合成 3 个候选（不克隆任何真人，可商用）。需要 .env 里的 ELEVENLABS_API_KEY（Creator 及以上套餐）。</p>
      <textarea id="vd_desc" rows="3" placeholder="例：四十岁左右的男声，低沉、温暖、有磁性，语速从容，像纪录片解说，带一点英式口音">${esc(localStorage.getItem('vf.vd_desc') || '')}</textarea>
      <textarea id="vd_text" rows="2" placeholder="试听文本（可空，默认用一段解说样例；≥100 字符）"></textarea>
      <div class="row"><button class="primary" id="vd_go">生成 3 个候选</button><span class="muted" id="vd_status"></span></div>
      <div id="vd_list"></div></div></div>`;
    $('#close').onclick = () => { m.innerHTML = ''; };
    $('#vd_go').onclick = async () => {
      const desc = $('#vd_desc').value.trim(); if (!desc) return; localStorage.setItem('vf.vd_desc', desc);
      $('#vd_go').disabled = true; $('#vd_status').textContent = '合成中（约 20–40 秒）…';
      try {
        const j = await api(`/api/voice/design?lang=${lang}`, { desc, text: $('#vd_text').value });
        $('#vd_list').innerHTML = j.previews.map((p, i) => `<div class="row"><b>候选 ${i + 1}</b><audio controls src="${fileUrl(p.audio)}"></audio><input class="grow" value="品牌旁白 ${i + 1}" data-name><button class="small primary" data-keep="${esc(p.id)}">保存并选用</button></div>`).join('');
        $('#vd_status').textContent = '';
        $('#vd_list').onclick = async e => {
          const b = e.target.closest('button[data-keep]'); if (!b) return; b.disabled = true;
          const name = b.closest('.row').querySelector('input[data-name]').value;
          try { const k = await api('/api/voice/keep', { id: b.dataset.keep, name, desc }); $('#f_voice').value = k.voice_id; topSet('voice', k.voice_id); nestedSet('tts', 'provider', 'elevenlabs'); $('#f_provider').value = 'elevenlabs'; m.innerHTML = ''; $('#issues').innerHTML = `<div class="banner info">已保存声音 ${esc(name)}（${esc(k.voice_id)}）并设为项目声音；配音服务已切到 ElevenLabs。</div>`; }
          catch (err) { alert(err.message); b.disabled = false; }
        };
      } catch (err) { $('#vd_status').innerHTML = `<span class="err">${esc(err.message)}</span>`; }
      $('#vd_go').disabled = false;
    };
  };
  $('#f_rate').oninput = e => { const val = `${e.target.value >= 0 ? '+' : ''}${e.target.value}%`; $('#rateVal').textContent = val; topSet('rate', val); };
  $('#ttsFirst').onclick = () => segs.length && ttsOne(segs[0].id);
  $('#ttsAll').onclick = async () => {
    if (!await save()) return;
    for (let i = 0; i < segs.length; i++) {
      $('#ttsProgress').textContent = `配音中 ${i + 1}/${segs.length}：${segs[i].id}`;
      try { await api(`/api/tts?lang=${lang}`, { id: segs[i].id }); } catch (e) { alert(`${segs[i].id}: ${e.message}`); break; }
    }
    load();
  };
  $('#voiceList2').onclick = e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const id = b.closest('.voice-row').dataset.id, s = raw.segments.find(x => x.id === id);
    if (b.dataset.act === 'tts') ttsOne(id);
    if (b.dataset.act === 'voice') openVoiceBrowser($('#f_provider').value, v => { s.voice = v; markDirty(true); }, s[textKey()]);
    if (b.dataset.act === 'clearvoice') { delete s.voice; markDirty(true); }
  };
}
/* voice browser: filter by language / region / gender, 3-second preview, pick */
const REGION = { 'en-US': '美国', 'en-GB': '英国（伦敦）', 'en-AU': '澳大利亚', 'en-NZ': '新西兰', 'en-IE': '爱尔兰', 'en-CA': '加拿大', 'en-IN': '印度', 'en-ZA': '南非', 'en-SG': '新加坡', 'en-HK': '香港英语', 'en-PH': '菲律宾', 'en-NG': '尼日利亚', 'en-KE': '肯尼亚', 'en-TZ': '坦桑尼亚',
  'zh-CN': '普通话', 'zh-CN-liaoning': '东北话', 'zh-CN-shaanxi': '陕西关中话', 'zh-HK': '粤语', 'zh-TW': '台湾国语', 'ja-JP': '日语', 'ko-KR': '韩语', 'de-DE': '德语', 'fr-FR': '法语', 'es-ES': '西班牙语' };
const regionOf = v => { const m = v.name.match(/^([a-z]{2}-[A-Z]{2}(?:-[a-z]+)?)/); return m ? m[1] : v.locale; };
async function openVoiceBrowser(provider, onPick, sampleText) {
  const m = $('#modal');
  m.innerHTML = `<div class="modal"><div class="box" style="max-height:90vh;display:flex;flex-direction:column">
    <div class="row" style="justify-content:space-between"><b>选择声音</b><button class="ghost" id="close">✕</button></div>
    <div class="row"><select id="vb_lang"><option value="${isBase() && lang === 'en' ? 'en' : lang}">当前语言（${isBase() && lang === 'en' ? 'en' : lang}）</option><option value="">全部语言</option></select>
      <select id="vb_region"><option value="">全部口音/地区</option></select>
      <select id="vb_gender"><option value="">男女都看</option><option value="Female">女声</option><option value="Male">男声</option></select>
      <span class="muted" id="vb_count"></span></div>
    <div id="vb_list" style="overflow:auto;flex:1"><span class="muted">加载中…</span></div></div></div>`;
  $('#close').onclick = () => { m.innerHTML = ''; };
  let all = [];
  try { all = await api(`/api/voices?provider=${provider}`); } catch (e) { $('#vb_list').innerHTML = `<div class="banner err">${esc(e.message)}</div>`; return; }
  const regions = [...new Set(all.map(regionOf))].sort();
  $('#vb_region').innerHTML += regions.map(r => `<option value="${r}">${REGION[r] || r} (${r})</option>`).join('');
  const draw = () => {
    const L = $('#vb_lang').value, Rg = $('#vb_region').value, G = $('#vb_gender').value;
    const rows = all.filter(v => (!L || v.locale.toLowerCase().startsWith(L.toLowerCase())) && (!Rg || regionOf(v) === Rg) && (!G || v.gender === G));
    $('#vb_count').textContent = `${rows.length} 个`;
    $('#vb_list').innerHTML = rows.map(v => `<div class="voice-row" style="grid-template-columns:260px 110px 1fr 200px" data-v="${esc(v.name)}">
      <b>${esc(v.name.replace(/Neural$/, ''))}</b><span class="muted">${esc(REGION[regionOf(v)] || v.locale)} · ${v.gender === 'Female' ? '女' : v.gender === 'Male' ? '男' : ''}</span>
      <span class="muted">${esc((v.personalities || []).join(', '))}</span>
      <span><button class="small" data-act="play">▶ 试听</button> <button class="small primary" data-act="pick">选用</button> <span class="vb_audio"></span></span></div>`).join('') || '<span class="muted">没有匹配的声音</span>';
  };
  $('#vb_lang').onchange = $('#vb_region').onchange = $('#vb_gender').onchange = draw;
  draw();
  $('#vb_list').onclick = async e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const row = b.closest('.voice-row'), v = row.dataset.v;
    if (b.dataset.act === 'pick') { m.innerHTML = ''; onPick(v); return; }
    b.disabled = true; b.textContent = '…';
    try { const j = await api(`/api/voices/preview?lang=${lang}`, { voice: v, provider, text: (sampleText || '').slice(0, 160) });
      row.querySelector('.vb_audio').innerHTML = `<audio autoplay controls src="${fileUrl(j.audio)}"></audio>`; }
    catch (err) { alert(err.message); }
    b.disabled = false; b.textContent = '▶ 试听';
  };
}

async function ttsOne(id) {
  if (!await save()) return;
  const row = $(`.voice-row[data-id="${id}"]`);
  const btn = row?.querySelector('button[data-act=tts]'); if (btn) { btn.disabled = true; btn.textContent = '合成中…'; }
  try {
    const j = await api(`/api/tts?lang=${lang}`, { id });
    if (row) row.querySelector('.audio').innerHTML = `<audio controls autoplay src="${fileUrl(j.audio)}?t=${j.stamp}"></audio>`;
    P.resolved[id] = { ...(P.resolved[id] || {}), audio: j.audio, audio_fresh: true, duration: j.duration };
  } catch (e) { alert(e.message); }
  if (btn) { btn.disabled = false; btn.textContent = '▶ 试听'; }
}

/* ---------------- 3 visuals ---------------- */
function clipThumb(s, c, i) {
  const r = (P.resolved[s.id] || {}).clips?.[i] || {};
  if (c.remotion) return `<div class="thumb">${esc(c.remotion.composition)}<br><span class="muted">动画</span></div>`;
  if (r.path && r.kind === 'video') return `<div class="thumb"><img src="/api/poster/${encodeURIComponent(s.id)}/${i}?lang=${lang}&t=${encodeURIComponent(r.path)}" alt=""></div>`;
  if (r.path) return `<div class="thumb"><img src="${fileUrl(r.path)}" alt=""></div>`;
  return `<div class="thumb">${(c.image || c.video || '').startsWith('pexels:') || (c.image || c.video || '').match(/^(pixabay|commons):/) ? '搜索词，渲染时自动取' : '未设置'}</div>`;
}
function clipSeconds(c, r) { if (c.video && c.out != null) return c.out - (c.in || 0); if (c.image && c.duration) return c.duration; return r?.natural || null; }

function viewVisuals(v) {
  const segs = raw.segments || [], res = P.resolved || {};
  segs.forEach(normalizeSeg);
  if (!segs.length) { v.innerHTML = '<div class="card">先在第 1 步写脚本。</div>'; return; }
  if (!selSeg || !segs.some(s => s.id === selSeg)) selSeg = (segs.find(s => !segClips(s).length) || segs[0]).id;
  const seg = segs.find(s => s.id === selSeg); const r = res[seg.id] || {};
  const need = r.need || 0;
  const fixed = seg.clips.reduce((a, c, i) => a + (clipSeconds(c, r.clips?.[i]) || 0), 0);
  const flex = seg.clips.filter((c, i) => !clipSeconds(c, r.clips?.[i])).length;
  const status = !seg.clips.length ? '<span class="err">还没有画面</span>' : fixed > need + 0.5 ? `<span class="warn">已选 ${fmt(fixed)}，超出旁白 ${fmt(fixed - need)}，末尾会被裁掉</span>` : flex ? `<span class="ok">固定 ${fmt(fixed)} + ${flex} 个自适应片段补满 ${fmt(need)}</span>` : fixed < need - 0.5 ? `<span class="warn">已选 ${fmt(fixed)} / 需要 ${fmt(need)}，最后一个片段会${seg.clips[seg.clips.length - 1].video ? '循环' : '延长'}补齐</span>` : `<span class="ok">已选 ${fmt(fixed)} ≈ 需要 ${fmt(need)}</span>`;

  v.innerHTML = `
  <div class="visuals">
    <div class="storyboard" id="storyboard">
      ${segs.map(s => { const rr = res[s.id] || {}; const cl = segClips(s); const c0 = cl[0]; const p0 = rr.clips?.[0]?.path;
        const th = !c0 ? '<span class="err">缺</span>' : c0.remotion ? c0.remotion.composition : p0 ? (rr.clips[0].kind === 'video' ? `<img src="/api/poster/${encodeURIComponent(s.id)}/0?lang=${lang}&t=${encodeURIComponent(p0)}">` : `<img src="${fileUrl(p0)}">`) : '自动';
        return `<div class="sb-card ${s.id === selSeg ? 'sel' : ''}" data-id="${esc(s.id)}"><div class="thumb">${th}</div>
        <div><b>${esc(s.id)}</b> <span class="muted">${fmt(rr.need)}</span><div class="t">${esc(s[textKey()] || s.text || '')}</div>
        <div class="st">${cl.length ? `${cl.length} 个片段` : '<span class="err">● 需要画面</span>'}</div></div></div>`; }).join('')}
    </div>
    <div>
      <div class="card">
        <div class="row" style="justify-content:space-between"><b>${esc(seg.id)}</b> <span class="need">${status}</span></div>
        <div class="muted">${esc(seg[textKey()] || seg.text || '')}</div>
        <div class="clipstrip" id="clipstrip">
          ${seg.clips.map((c, i) => `
          <div class="clip" data-i="${i}">${clipThumb(seg, c, i)}
            <span class="badge">${c.remotion ? '动画' : (c.video ? '视频' : '图片')}</span>
            <div class="ops"><button data-act="left" ${i === 0 ? 'disabled' : ''}>←</button><button data-act="right" ${i === seg.clips.length - 1 ? 'disabled' : ''}>→</button><button data-act="del">✕</button></div>
            <div class="meta">
              ${c.video ? `<span>${c.out != null ? `${(c.in || 0).toFixed(1)} → ${c.out.toFixed(1)} s（${fmt(c.out - (c.in || 0))}）` : '整段'} <button class="small" data-act="trim">选段</button> <button class="small" data-act="more" title="用同一个视频再选几段">再选</button></span>` : ''}
              ${c.image ? `<span>运镜 <select data-act="motion">${['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'none'].map(m => `<option ${(c.motion || 'zoom_in') === m ? 'selected' : ''}>${m}</option>`).join('')}</select></span>
                          <span>时长 <input type="number" data-act="duration" step="0.5" min="1" style="width:60px" value="${c.duration ?? ''}" placeholder="自适应"> s</span>` : ''}
              ${c.remotion ? `<span>${esc(c.remotion.composition)} <button class="small" data-act="props">编辑</button></span>` : ''}
            </div>
          </div>`).join('')}
          <div class="clip" style="display:flex;align-items:center;justify-content:center;min-height:120px;border-style:dashed"><span class="muted">← 在下面添加片段</span></div>
        </div>
        <div class="row" style="margin-top:4px"><b style="font-size:12px">画中画</b>
          ${(seg.overlays || []).map((o, i) => `<span class="pill" data-ov="${i}">${o.avatar ? '主持人' : o.video ? '视频' : '图片'} · ${o.position || 'bottom-right'} · ${Math.round((o.size || 0.3) * 100)}% · ${o.at || 0}s${o.duration ? '→' + (o.at + o.duration) + 's' : '→末'} <button class="small ghost" data-ovdel="${i}">✕</button></span>`).join('')}
          <button class="small" id="ovAdd">＋ 图片/视频</button><button class="small" id="ovAvatar" title="这一段加数字主持人（第 4 步可设外观）">＋ 主持人</button>
          <span class="muted">说到某处时叠一张图或一段无声视频；主持人在第 4 步统一设置</span></div>
        <div class="row"><button id="previewBtn">▶ 预览这一段（草稿质量）</button><button class="small" id="dupBtn" title="复制这一段到后面">复制一段</button><span class="muted" id="previewInfo"></span></div>
        <div id="previewBox"></div>
        <div class="row"><label>片段不够长时 <select id="fit"><option value="stretch" ${seg.fit !== 'trim' ? 'selected' : ''}>延长/循环最后一个片段</option><option value="trim" ${seg.fit === 'trim' ? 'selected' : ''}>同上（保留字段）</option></select></label>
          <label>说完停顿 <input id="pause" type="number" step="0.1" min="0" style="width:64px" value="${seg.pause_after ?? 0.5}"> s</label></div>
      </div>
      <div class="card">
        <div class="tabs" id="ptabs">
          <button data-tab="search" class="${picker.tab === 'search' ? 'active' : ''}">搜索素材</button>
          <button data-tab="upload" class="${picker.tab === 'upload' ? 'active' : ''}">本地文件</button>
          <button data-tab="anim" class="${picker.tab === 'anim' ? 'active' : ''}">动画（Remotion）</button>
        </div>
        <div id="picker"></div>
      </div>
    </div>
  </div>`;
  const autoBtn = document.createElement('button'); autoBtn.className = 'small'; autoBtn.style.marginBottom = '8px'; autoBtn.textContent = '✨ 没画面的段一键自动配图';
  autoBtn.title = '按每段旁白的关键词生成搜索片段（渲染时自动取第一张），之后可逐段替换';
  autoBtn.onclick = async () => { if (!await save()) return; autoBtn.disabled = true; try { const j = await api(`/api/autofill?lang=${lang}`, {}); await load(); $('#issues').innerHTML = `<div class="banner info">已为 ${j.filled} 段生成 ${j.source} 搜索片段，渲染时自动取第一张；不满意的段点开重选。</div>`; } catch (e) { alert(e.message); } };
  $('#storyboard').prepend(autoBtn);
  $('#storyboard').onclick = e => { const c = e.target.closest('.sb-card'); if (c) { selSeg = c.dataset.id; picker.cands = []; picker.q = ''; render(); } };
  $('#fit').onchange = e => { seg.fit = e.target.value; markDirty(); };
  seg.overlays = seg.overlays || [];
  $('#ovAvatar').onclick = () => { seg.overlays.push({ avatar: true, position: raw.presenter?.position || 'bottom-right', size: raw.presenter?.size || 0.28 }); markDirty(true); };
  $('#ovAdd').onclick = () => openOverlayDialog(seg, null);
  v.querySelectorAll('[data-ovdel]').forEach(b => b.onclick = e => { e.stopPropagation(); seg.overlays.splice(+b.dataset.ovdel, 1); markDirty(true); });
  v.querySelectorAll('.pill[data-ov]').forEach(pl => pl.onclick = e => { if (e.target.closest('button')) return; const o = seg.overlays[+pl.dataset.ov]; if (!o.avatar) openOverlayDialog(seg, o); });
  $('#previewBtn').onclick = async () => {
    if (!seg.clips.length) return alert('先给这一段加画面');
    if (!await save()) return;
    const b = $('#previewBtn'); b.disabled = true; $('#previewInfo').textContent = '渲染中（配音 + 画面，通常 5–30 秒）…';
    try { const j = await api(`/api/preview?lang=${lang}`, { id: seg.id });
      $('#previewBox').innerHTML = `<video controls autoplay style="max-width:640px;margin:6px 0" src="${fileUrl(j.video)}?t=${j.stamp}"></video>`;
      $('#previewInfo').textContent = `${fmt(j.duration)} · 草稿质量，成片会更清晰`; }
    catch (e) { $('#previewInfo').innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    b.disabled = false;
  };
  $('#dupBtn').onclick = () => { const i = raw.segments.indexOf(seg); const copy = JSON.parse(JSON.stringify(seg)); copy.id = newId(); raw.segments.splice(i + 1, 0, copy); selSeg = copy.id; markDirty(true); };
  $('#pause').onchange = e => { seg.pause_after = parseFloat(e.target.value) || 0; markDirty(); };
  $('#clipstrip').onclick = async e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const i = +b.closest('.clip').dataset.i, a = b.dataset.act, c = seg.clips[i];
    if (a === 'del') seg.clips.splice(i, 1);
    if (a === 'left') seg.clips.splice(i - 1, 0, seg.clips.splice(i, 1)[0]);
    if (a === 'right') seg.clips.splice(i + 1, 0, seg.clips.splice(i, 1)[0]);
    if (a === 'trim') { const rr = (res[seg.id] || {}).clips?.[i]; return openTrim({ url: fileUrl(rr?.path), duration: null, ranges: [{ in: c.in || 0, out: c.out }] }, (ranges) => { c.in = ranges[0].in; c.out = ranges[0].out; ranges.slice(1).forEach((r, k) => seg.clips.splice(i + 1 + k, 0, { video: c.video, in: r.in, out: r.out, credit: c.credit })); markDirty(true); }); }
    if (a === 'more') { const rr = (res[seg.id] || {}).clips?.[i]; return openTrim({ url: fileUrl(rr?.path), duration: null, ranges: [{ in: (c.out || 0), out: null }] }, (ranges) => { ranges.forEach((r, k) => seg.clips.splice(i + 1 + k, 0, { video: c.video, in: r.in, out: r.out, credit: c.credit })); markDirty(true); }); }
    if (a === 'props') return openProps(c);
    markDirty(true);
  };
  $('#clipstrip').onchange = e => {
    const el = e.target.closest('[data-act]'); if (!el) return;
    const c = seg.clips[+el.closest('.clip').dataset.i];
    if (el.dataset.act === 'motion') c.motion = el.value;
    if (el.dataset.act === 'duration') { const d = parseFloat(el.value); if (d > 0) c.duration = d; else delete c.duration; }
    markDirty();
  };
  $('#ptabs').onclick = e => { const b = e.target.closest('button'); if (b) { picker.tab = b.dataset.tab; render(); } };
  renderPicker(seg, r);
}

function renderPicker(seg, r) {
  const box = $('#picker');
  if (!box || step !== 3 || selSeg !== seg.id) return;      // user moved on while a search was in flight
  if (picker.tab === 'upload') {
    box.innerHTML = `<div class="drop" id="drop">点击选择或拖入图片 / 视频文件（会复制到 assets/local/）<input type="file" id="file" hidden accept="image/*,video/*" multiple></div>`;
    const drop = $('#drop'); drop.onclick = () => $('#file').click();
    drop.ondragover = e => { e.preventDefault(); drop.style.borderColor = 'var(--accent)'; };
    drop.ondrop = e => { e.preventDefault(); uploadFiles(seg, e.dataTransfer.files); };
    $('#file').onchange = e => uploadFiles(seg, e.target.files);
    return;
  }
  if (picker.tab === 'anim') {
    box.innerHTML = `<p class="hint">动画段在渲染时用 Remotion 生成，时长自动等于它在本段的份额。</p>
      <div class="row">${['TitleCard', 'Timeline', 'BarChart'].map(c => `<button data-comp="${c}">＋ ${c}</button>`).join('')}</div>
      <p class="hint">TitleCard：章节标题卡 · Timeline：时间轴逐条出现 · BarChart：动画柱状对比。加入后点片段上的「编辑」改文字。</p>`;
    box.onclick = e => { const b = e.target.closest('button[data-comp]'); if (!b) return;
      const defaults = { TitleCard: { title: seg[labelKey()] || seg.label || seg.id, subtitle: '' }, Timeline: { title: '', events: [{ date: '1815', text: '…' }, { date: '1816', text: '…' }] }, BarChart: { title: '', items: [{ label: 'A', value: 3 }, { label: 'B', value: 5 }] } };
      seg.clips.push({ remotion: { composition: b.dataset.comp, props: defaults[b.dataset.comp] } }); markDirty(true); };
    return;
  }
  // search tab
  const kws = r.keywords || [];
  if (!picker.q) picker.q = seg.visual_hint || kws[0] || '';   // a pasted script's 画面: line wins
  box.innerHTML = `
    <div class="row">
      <select id="src"><option value="pexels" ${picker.source === 'pexels' ? 'selected' : ''}>Pexels</option><option value="pixabay" ${picker.source === 'pixabay' ? 'selected' : ''}>Pixabay</option><option value="commons" ${picker.source === 'commons' ? 'selected' : ''}>Wikimedia Commons（公有领域/CC）</option>
        <option value="google" ${picker.source === 'google' ? 'selected' : ''}>Google 图片 · 仅 CC 许可（用我的浏览器）</option><option value="google_all" ${picker.source === 'google_all' ? 'selected' : ''}>Google 图片 · 全部 ⚠ 版权未知</option><option value="baidu" ${picker.source === 'baidu' ? 'selected' : ''}>百度图片 ⚠ 版权未知</option></select>
      <select id="kind"><option value="image" ${picker.kind === 'image' ? 'selected' : ''}>图片</option><option value="video" ${picker.kind === 'video' ? 'selected' : ''}>视频</option></select>
      <input id="q" class="grow" value="${esc(picker.q)}" placeholder="英文关键词效果最好">
      <button class="primary" id="go">搜索</button>
    </div>
    <div class="row"><span class="muted">建议：</span>${kws.map(k => `<span class="kw" data-kw="${esc(k)}">${esc(k)}</span>`).join('')}</div>
    <div id="cands" class="cands">${picker.loading ? '<span class="muted">搜索中…</span>' : picker.err ? `<div class="banner err">${esc(picker.err)}</div>` : picker.cands.map((c, i) => `
      <div class="cand" data-i="${i}" title="${esc(c.title || '')} · ${esc(c.author)} · ${esc(c.license)}">
        <div class="thumb">${c.kind === 'video' ? `<video muted loop preload="none" poster="${esc(c.thumb_url)}" src="${esc(c.preview_url)}"></video>` : `<img loading="lazy" src="${esc(c.thumb_url)}" alt="">`}</div>
        <div class="meta"><span>${esc(c.author || c.title || '')}</span><span>${c.kind === 'video' ? fmt(c.duration) : `${c.width}×${c.height}`}</span></div>
      </div>`).join('')}</div>
    ${picker.cands.length ? `<div class="row" style="justify-content:center"><button class="small" id="more">更多结果</button></div>` : ''}`;
  const doSearch = async (page = 1) => {
    picker.q = $('#q').value.trim(); picker.source = $('#src').value; picker.kind = $('#kind').value; picker.page = page; picker.loading = true; picker.err = null; renderPicker(seg, r);
    try {
      if (['commons', 'google', 'google_all', 'baidu'].includes(picker.source) && picker.kind === 'video') throw new Error('这个来源只提供图片；视频请用 Pexels / Pixabay');
      const j = await api(`/api/search?source=${picker.source}&kind=${picker.kind}&q=${encodeURIComponent(picker.q)}&page=${page}`);
      picker.cands = page > 1 ? picker.cands.concat(j.candidates) : j.candidates;
      if (!picker.cands.length) picker.err = '没有结果，换个关键词（英文）试试。';
    } catch (e) { picker.err = e.data?.needs_key ? `需要 ${e.data.needs_key}：在项目目录的 .env 里加一行 ${e.data.needs_key}=你的key（Pexels 免费注册 pexels.com/api，Pixabay 在 pixabay.com/api/docs）。或切换来源为 Commons（无需 key）。` : e.message; }
    picker.loading = false; renderPicker(seg, r);
  };
  $('#go').onclick = () => doSearch(1);
  $('#q').onkeydown = e => { if (e.key === 'Enter') doSearch(1); };
  $('#src').onchange = $('#kind').onchange = () => { picker.cands = []; doSearch(1); };
  $$('.kw', box).forEach(k => k.onclick = () => { $('#q').value = k.dataset.kw; doSearch(1); });
  if ($('#more')) $('#more').onclick = () => doSearch(picker.page + 1);
  const cands = $('#cands');
  cands.onmouseover = e => { const v = e.target.closest('.cand')?.querySelector('video'); if (v) v.play().catch(() => { }); };
  cands.onmouseout = e => { const v = e.target.closest('.cand')?.querySelector('video'); if (v) { v.pause(); } };
  cands.onclick = e => {
    const el = e.target.closest('.cand'); if (!el) return;
    const c = picker.cands[+el.dataset.i];
    if (c.kind === 'video') openTrim({ url: c.preview_url, duration: c.duration, ranges: [{ in: 0, out: Math.min(c.duration || 10, Math.max(3, Math.ceil((r.need || 8) - (segFixed(seg, r) || 0)))) }] }, (ranges) => addCandidate(seg, c, ranges));
    else {
      if (/版权未知/.test(c.license || '') && !confirm(`这张图来自网页，版权未知：\n${c.page_url}\n\n用于变现视频可能收到版权投诉。确定加入？（来源会记入 credits.txt）`)) return;
      addCandidate(seg, c, null);
    }
  };
  if (!picker.cands.length && picker.q && !picker.loading && !picker.err) doSearch(1);
}
function segFixed(seg, r) { return seg.clips.reduce((a, c, i) => a + (clipSeconds(c, r.clips?.[i]) || 0), 0); }

async function addCandidate(seg, c, io) {
  $('#issues').innerHTML = `<div class="banner info">下载中：${esc(c.title || c.author)}…</div>`;
  try {
    const j = await api('/api/assets/fetch', { candidate: c });
    const ranges = c.kind === 'video' ? (Array.isArray(io) ? io : [io]) : [null];
    for (const rg of ranges) {
      const clip = rg ? { video: j.path, in: +rg.in.toFixed(2), out: +rg.out.toFixed(2) } : { image: j.path, motion: 'zoom_in' };
      clip.credit = j.credit;
      seg.clips.push(clip);
    }
    $('#issues').innerHTML = '';
    if (await save()) await load();
  } catch (e) { $('#issues').innerHTML = `<div class="banner err">${esc(e.message)}</div>`; }
}
async function uploadFiles(seg, files) {
  for (const f of files) {
    $('#issues').innerHTML = `<div class="banner info">上传 ${esc(f.name)}…</div>`;
    const b64 = await new Promise(res => { const rd = new FileReader(); rd.onload = () => res(rd.result.split(',')[1]); rd.readAsDataURL(f); });
    try {
      const j = await api('/api/assets/upload', { name: f.name, data_b64: b64 });
      seg.clips.push(j.kind === 'video' ? { video: j.path } : { image: j.path, motion: 'zoom_in' });
    } catch (e) { alert(e.message); }
  }
  $('#issues').innerHTML = '';
  if (await save()) await load();
}

/* trim dialog: one or more [in,out] ranges over a preview player; each range becomes a clip */
function openTrim(opts, onDone) {
  const m = $('#modal');
  let dur = opts.duration || 0;
  let ranges = (opts.ranges || [{ in: 0, out: null }]).map(r => ({ in: r.in || 0, out: r.out }));
  let cur = 0;
  m.innerHTML = `<div class="modal"><div class="box">
    <div class="row" style="justify-content:space-between"><b>选择片段范围</b><button class="ghost" id="close">✕</button></div>
    <video id="pv" src="${esc(opts.url || '')}" controls muted playsinline></video>
    <div class="rangebar" id="bar"></div>
    <div id="rlist" class="row"></div>
    <div class="trim"><span class="muted">开始</span><input type="range" id="tin" min="0" step="0.1"><span class="t" id="tinv"></span></div>
    <div class="trim"><span class="muted">结束</span><input type="range" id="tout" min="0" step="0.1"><span class="t" id="toutv"></span></div>
    <div class="row" style="justify-content:space-between"><span class="muted" id="info"></span>
      <span><button id="addRange">＋ 再加一段</button> <button id="playSel">▶ 播放所选</button> <button class="primary" id="ok">加入</button></span></div>
  </div></div>`;
  const pv = $('#pv'), a = $('#tin'), b = $('#tout');
  const clamp = () => { const r = ranges[cur]; if (r.out == null || r.out <= r.in + 0.2) r.out = Math.min(dur || 1e9, r.in + Math.max(3, 0.2)); if (dur) { r.in = Math.min(r.in, dur - 0.2); r.out = Math.min(r.out, dur); } };
  const drawBar = () => {
    $('#bar').innerHTML = dur ? ranges.map((r, i) => `<div class="sel" style="left:${r.in / dur * 100}%;width:${(r.out - r.in) / dur * 100}%;opacity:${i === cur ? 1 : .45}"></div>`).join('') : '';
    $('#rlist').innerHTML = ranges.map((r, i) => `<button class="small ${i === cur ? 'primary' : ''}" data-i="${i}">段 ${i + 1}: ${r.in.toFixed(1)}–${(r.out ?? 0).toFixed(1)} s</button>${ranges.length > 1 ? `<button class="small ghost" data-del="${i}" title="删除这一段">✕</button>` : ''}`).join('');
    const total = ranges.reduce((t, r) => t + ((r.out ?? r.in) - r.in), 0);
    $('#info').textContent = `共 ${ranges.length} 段 · 已选 ${total.toFixed(1)} s${dur ? ` / 素材 ${dur.toFixed(1)} s` : ''}`;
  };
  const show = () => { const r = ranges[cur]; clamp(); a.max = b.max = (dur || 60).toFixed(1); a.value = r.in; b.value = r.out; $('#tinv').textContent = r.in.toFixed(1); $('#toutv').textContent = r.out.toFixed(1); drawBar(); };
  pv.onloadedmetadata = () => { if (!opts.duration) dur = pv.duration; show(); };
  show();
  a.oninput = () => { ranges[cur].in = +a.value; if (ranges[cur].out <= ranges[cur].in + 0.2) ranges[cur].out = ranges[cur].in + 0.2; show(); pv.currentTime = ranges[cur].in; };
  b.oninput = () => { ranges[cur].out = Math.max(+b.value, ranges[cur].in + 0.2); show(); pv.currentTime = ranges[cur].out; };
  $('#rlist').onclick = e => { const t = e.target.closest('button'); if (!t) return; if (t.dataset.del != null) { ranges.splice(+t.dataset.del, 1); cur = Math.min(cur, ranges.length - 1); } else cur = +t.dataset.i; show(); };
  $('#addRange').onclick = () => { const last = ranges[ranges.length - 1]; const start = Math.min(last.out ?? 0, (dur || 1e9) - 0.5); ranges.push({ in: start, out: Math.min(dur || start + 5, start + 5) }); cur = ranges.length - 1; show(); };
  let stopAt = null;
  pv.ontimeupdate = () => { if (stopAt != null && pv.currentTime >= stopAt) { pv.pause(); stopAt = null; } };
  $('#playSel').onclick = () => { pv.currentTime = ranges[cur].in; stopAt = ranges[cur].out; pv.play(); };
  $('#close').onclick = () => { m.innerHTML = ''; };
  $('#ok').onclick = () => { m.innerHTML = ''; onDone(ranges.map(r => ({ in: r.in, out: r.out }))); };
}
/* overlay (picture-in-picture) dialog: file from this segment's clips or upload, timing, position, size */
function openOverlayDialog(seg, existing) {
  const m = $('#modal');
  const o = existing || { image: null, at: 0, position: 'bottom-right', size: 0.3, animate: 'slide', border: true };
  const cand = seg.clips.filter(c => c.image || c.video).map(c => c.image || c.video);
  const need = (P.resolved[seg.id] || {}).need || 10;
  m.innerHTML = `<div class="modal"><div class="box">
    <div class="row" style="justify-content:space-between"><b>画中画</b><button class="ghost" id="close">✕</button></div>
    <div class="grid2">
      <div><label class="muted">素材</label><select id="ov_src">${cand.map(p => `<option value="${esc(p)}" ${(o.image || o.video) === p ? 'selected' : ''}>${esc(p.split('/').pop())}</option>`).join('')}<option value="__upload">上传新文件…</option></select><input type="file" id="ov_file" hidden accept="image/*,video/*"></div>
      <div><label class="muted">位置</label><select id="ov_pos">${['top-left', 'top', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom', 'bottom-right'].map(p => `<option ${o.position === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
      <div><label class="muted">出现于（秒，从本段开始；旁白约 ${fmt(need)}）</label><input id="ov_at" type="number" step="0.5" min="0" value="${o.at || 0}"></div>
      <div><label class="muted">持续（秒，空 = 到段末）</label><input id="ov_dur" type="number" step="0.5" min="0.5" value="${o.duration ?? ''}"></div>
      <div><label class="muted">宽度（画面的 %）</label><input id="ov_size" type="range" min="10" max="60" value="${Math.round((o.size || 0.3) * 100)}"><span id="ov_sizev">${Math.round((o.size || 0.3) * 100)}%</span></div>
      <div><label class="muted">进场</label><select id="ov_anim">${[['slide', '滑入'], ['fade', '淡入'], ['none', '直接出现']].map(([v, l]) => `<option value="${v}" ${(o.animate || 'slide') === v ? 'selected' : ''}>${l}</option>`).join('')}</select> <label><input type="checkbox" id="ov_border" ${o.border !== false ? 'checked' : ''}> 白边</label></div>
    </div>
    <p class="hint">视频素材一律静音；比窗口短会循环。提示：说到某个名词时出现，看第 2 步该段的字幕时间即可。</p>
    <div class="row" style="justify-content:flex-end"><button class="primary" id="ov_ok">${existing ? '保存' : '加入'}</button></div></div></div>`;
  $('#close').onclick = () => { m.innerHTML = ''; };
  $('#ov_size').oninput = e => $('#ov_sizev').textContent = e.target.value + '%';
  $('#ov_src').onchange = e => { if (e.target.value === '__upload') $('#ov_file').click(); };
  $('#ov_file').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const b64 = await new Promise(res => { const rd = new FileReader(); rd.onload = () => res(rd.result.split(',')[1]); rd.readAsDataURL(f); });
    try { const j = await api('/api/assets/upload', { name: f.name, data_b64: b64 }); const opt = document.createElement('option'); opt.value = j.path; opt.textContent = f.name; opt.selected = true; $('#ov_src').insertBefore(opt, $('#ov_src').lastElementChild); } catch (err) { alert(err.message); }
  };
  $('#ov_ok').onclick = () => {
    const src = $('#ov_src').value; if (!src || src === '__upload') return alert('先选素材');
    const isVideo = /\.(mp4|mov|mkv|webm|m4v)$/i.test(src);
    const nv = { [isVideo ? 'video' : 'image']: src, at: parseFloat($('#ov_at').value) || 0, position: $('#ov_pos').value, size: +$('#ov_size').value / 100, animate: $('#ov_anim').value, border: $('#ov_border').checked };
    const d = parseFloat($('#ov_dur').value); if (d > 0) nv.duration = d;
    if (existing) { Object.keys(existing).forEach(k => delete existing[k]); Object.assign(existing, nv); } else seg.overlays.push(nv);
    m.innerHTML = ''; markDirty(true);
  };
}

function openProps(c) {
  const m = $('#modal');
  m.innerHTML = `<div class="modal"><div class="box">
    <div class="row" style="justify-content:space-between"><b>${esc(c.remotion.composition)} 的内容</b><button class="ghost" id="close">✕</button></div>
    <p class="hint">JSON。文字可以写成 {"en": "...", "zh": "..."} 供多语言使用。</p>
    <textarea id="props" rows="14" spellcheck="false" style="font-family:ui-monospace,Consolas,monospace;font-size:12px">${esc(JSON.stringify(c.remotion.props || {}, null, 2))}</textarea>
    <div class="row" style="justify-content:space-between"><span class="err" id="perr"></span><button class="primary" id="ok">保存</button></div></div></div>`;
  $('#close').onclick = () => { m.innerHTML = ''; };
  $('#ok').onclick = () => { try { c.remotion.props = JSON.parse($('#props').value); m.innerHTML = ''; markDirty(true); } catch (e) { $('#perr').textContent = 'JSON 有误：' + e.message; } };
}

/* ---------------- 4 render ---------------- */
function viewRender(v) {
  const o = P.outputs;
  v.innerHTML = `
  <div class="card">
    <div class="grid2">
      <div><label class="muted">质量</label><select id="f_quality"><option value="draft" ${raw.quality === 'draft' ? 'selected' : ''}>草稿（快 3 倍，看效果）</option><option value="final" ${(raw.quality || 'final') === 'final' ? 'selected' : ''}>成片（CRF 18，2× 超采样）</option></select></div>
      <div><label class="muted">字幕</label><select id="f_burn"><option value="false" ${!nestedGet('subtitles', 'burn') ? 'selected' : ''}>只出 .srt（上传时作字幕轨）</option><option value="true" ${nestedGet('subtitles', 'burn') ? 'selected' : ''}>烧进画面</option></select>
        <select id="f_substyle" style="margin-top:4px"><option value="outline" ${(nestedGet('subtitles', 'style') || 'outline') === 'outline' ? 'selected' : ''}>白字黑边</option><option value="box" ${nestedGet('subtitles', 'style') === 'box' ? 'selected' : ''}>白字 + 半透明底框</option></select></div>
      <div><label class="muted">片段间转场（秒，0 = 硬切）</label><input id="f_trans" type="number" step="0.1" min="0" max="2" value="${raw.transition ?? 0}"></div>
      <div><label class="muted">背景音乐</label><input id="f_bgm" value="${esc(raw.bgm?.file || '')}" placeholder="assets/bgm.mp3（留空则无）"></div>
      <div><label class="muted">章节标题卡</label><select id="f_cards"><option value="false" ${!raw.auto_title_cards ? 'selected' : ''}>不加</option><option value="true" ${raw.auto_title_cards ? 'selected' : ''}>有章节名的段前加 3 秒标题卡（需 Remotion）</option></select></div>
      <div><label class="muted">旁白响度归一</label><select id="f_norm"><option value="true" ${raw.normalize_audio !== false ? 'selected' : ''}>开（-16 LUFS，推荐）</option><option value="false" ${raw.normalize_audio === false ? 'selected' : ''}>关</option></select></div>
    </div>
    <details ${raw.presenter && raw.presenter.provider !== 'none' && raw.presenter.where !== 'none' ? 'open' : ''}><summary>数字主持人（画中画里"你"的形象）</summary>
      <div class="grid2" style="margin-top:6px">
        <div><label class="muted">类型</label><select id="p_prov">${[['host', '风格化插画主持人（本地生成，免费，无需披露）'], ['heygen', 'HeyGen 逼真数字分身（需 key + 你的 avatar；自动勾选合成内容披露）'], ['none', '不用']].map(([v, l]) => `<option value="${v}" ${(raw.presenter?.provider || 'host') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div><label class="muted">出现在</label><select id="p_where">${[['none', '不自动加（在第 3 步按段添加）'], ['first_last', '开场段 + 收尾段'], ['all', '每一段']].map(([v, l]) => `<option value="${v}" ${(raw.presenter?.where || 'none') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div><label class="muted">位置</label><select id="p_pos">${['bottom-right', 'bottom-left', 'top-right', 'top-left', 'right', 'left'].map(p => `<option ${(raw.presenter?.position || 'bottom-right') === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
        <div><label class="muted">大小（画面宽的 %）</label><input id="p_size" type="number" min="15" max="50" value="${Math.round((raw.presenter?.size || 0.28) * 100)}"></div>
        <div><label class="muted">发型</label><select id="p_hair">${[['side', '侧分'], ['short', '短发'], ['long', '长发'], ['bald', '光头']].map(([v, l]) => `<option value="${v}" ${(raw.presenter?.style?.hairStyle || 'side') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div><label class="muted">肤色 / 发色 / 衣服 / 背景</label><div class="row" style="margin:0"><input type="color" id="p_skin" value="${esc(raw.presenter?.style?.skin || '#e8b98f')}"><input type="color" id="p_hairc" value="${esc(raw.presenter?.style?.hair || '#2b2118')}"><input type="color" id="p_shirt" value="${esc(raw.presenter?.style?.shirt || '#264653')}"><input type="color" id="p_bg" value="${esc(raw.presenter?.style?.bg || '#0f1115')}"></div></div>
        <div><label class="muted">署名（角落小字）</label><input id="p_name" value="${esc(raw.presenter?.style?.name || '')}" placeholder="频道名或你的名字"></div>
        <div><label class="muted">配饰</label><label><input type="checkbox" id="p_glasses" ${raw.presenter?.style?.glasses ? 'checked' : ''}> 眼镜</label> <label><input type="checkbox" id="p_beard" ${raw.presenter?.style?.beard ? 'checked' : ''}> 胡须</label></div>
        <div><label class="muted">HeyGen avatar id（仅逼真分身）</label><input id="p_heygen" value="${esc(raw.presenter?.heygen_avatar_id || '')}"></div>
      </div>
      <p class="hint">插画主持人的口型由配音音量驱动，眨眼与微动作自动生成；换成基于你照片的分层插画在路线图里。逼真分身属于"合成人物"，YouTube 会显示"合成内容"标签——这不影响获利，不披露才有风险。</p>
    </details>
    <details><summary>高级参数（编码器 / 并行 / 超采样 / 运镜幅度 / 分辨率）</summary>
      <div class="grid2" style="margin-top:6px">
        <div><label class="muted">视频编码器</label><select id="a_enc"><option value="auto" ${(raw.encoder || 'auto') === 'auto' ? 'selected' : ''}>auto（有显卡硬编就用）</option>${(H?.encoders || ['libx264']).map(e => `<option ${raw.encoder === e ? 'selected' : ''}>${e}</option>`).join('')}</select></div>
        <div><label class="muted">并行渲染段数（0 = 核数/2）</label><input id="a_par" type="number" min="0" max="32" value="${raw.parallel ?? 0}"></div>
        <div><label class="muted">运镜超采样（空 = 按质量：草稿 1 / 成片 2；3 更细腻慢 2 倍）</label><input id="a_ss" type="number" min="1" max="3" value="${raw.supersample ?? ''}" placeholder="按质量"></div>
        <div><label class="muted">运镜幅度（0.08 克制 · 0.15 默认 · 0.25 明显）</label><input id="a_motion" type="number" step="0.01" min="0" max="0.5" value="${raw.motion_amount ?? 0.15}"></div>
        <div><label class="muted">画幅</label><select id="a_size">${[['1920x1080', '1080p 横屏（YouTube）'], ['3840x2160', '4K 横屏（渲染 ×4）'], ['1080x1920', '竖屏 1080×1920（Shorts / 抖音）'], ['1280x720', '720p（快速）']].map(([v, l]) => `<option value="${v}" ${`${raw.width || 1920}x${raw.height || 1080}` === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div><label class="muted">帧率</label><select id="a_fps">${[24, 25, 30, 60].map(f => `<option ${(raw.fps || 30) == f ? 'selected' : ''}>${f}</option>`).join('')}</select></div>
      </div>
      <p class="hint">这些都写进 project.json；渲染日志里第一行会显示实际选用的编码器。qsv = Intel 显卡，nvenc = NVIDIA，amf = AMD，videotoolbox = Mac。</p>
    </details>
    <div class="row" style="margin-top:10px">
      <button class="primary" id="buildBtn">▶ 渲染</button>
      <button id="cancelBtn" hidden>停止</button>
      <span class="pill" id="buildState">空闲</span><span class="muted" id="elapsed"></span>
    </div>
    <div class="progress" id="progress" hidden><div class="bar" id="bar"></div><span id="ptext"></span></div>
    <pre class="log" id="log" hidden></pre>
  </div>
  <div class="card" id="result" ${o.final ? '' : 'hidden'}>
    <div class="row" style="justify-content:space-between"><b>成片</b><span class="muted" id="resultMeta"></span></div>
    <video id="player" controls playsinline></video>
    <div class="row" style="margin-top:8px"><a id="dlVideo" download>final.mp4</a> · <a id="dlSrt" download>final.srt</a> · <a id="dlThumb" target="_blank">thumbnail.jpg</a> · <span class="muted" id="buildPath"></span></div>
    <div class="row"><img id="thumbImg" style="width:200px;border-radius:4px" alt=""><div class="chapters" id="chapters"></div></div>
  </div>`;
  $('#f_quality').onchange = e => { raw.quality = e.target.value; markDirty(); };
  $('#f_burn').onchange = e => nestedSet('subtitles', 'burn', e.target.value === 'true');
  $('#f_substyle').onchange = e => nestedSet('subtitles', 'style', e.target.value);
  $('#f_trans').onchange = e => { raw.transition = parseFloat(e.target.value) || 0; markDirty(); };
  $('#f_cards').onchange = e => { raw.auto_title_cards = e.target.value === 'true'; markDirty(); };
  $('#f_norm').onchange = e => { raw.normalize_audio = e.target.value === 'true'; markDirty(); };
  $('#f_bgm').onchange = e => { const f = e.target.value.trim(); raw.bgm = f ? { ...(raw.bgm || {}), file: f, volume_db: raw.bgm?.volume_db ?? -18, fade_out: raw.bgm?.fade_out ?? 3 } : null; markDirty(); };
  $('#buildBtn').onclick = async () => {
    if (!await save()) return;
    try { await api(`/api/build?lang=${lang}&burn=${nestedGet('subtitles', 'burn') ? 1 : 0}`, {}); } catch (e) { return alert(e.message); }
    $('#log').hidden = false; poll();
  };
  $('#cancelBtn').onclick = () => api('/api/build/cancel', {});
  $('#a_enc').onchange = e => { raw.encoder = e.target.value; markDirty(); };
  const pres = () => { raw.presenter = raw.presenter || {}; raw.presenter.style = raw.presenter.style || {}; return raw.presenter; };
  $('#p_prov').onchange = e => { pres().provider = e.target.value; markDirty(); };
  $('#p_where').onchange = e => { pres().where = e.target.value; markDirty(); };
  $('#p_pos').onchange = e => { pres().position = e.target.value; markDirty(); };
  $('#p_size').onchange = e => { pres().size = (+e.target.value || 28) / 100; markDirty(); };
  $('#p_hair').onchange = e => { pres().style.hairStyle = e.target.value; markDirty(); };
  for (const [id, key] of [['p_skin', 'skin'], ['p_hairc', 'hair'], ['p_shirt', 'shirt'], ['p_bg', 'bg']]) $('#' + id).onchange = e => { pres().style[key] = e.target.value; markDirty(); };
  $('#p_name').onchange = e => { pres().style.name = e.target.value; markDirty(); };
  $('#p_glasses').onchange = e => { pres().style.glasses = e.target.checked; markDirty(); };
  $('#p_beard').onchange = e => { pres().style.beard = e.target.checked; markDirty(); };
  $('#p_heygen').onchange = e => { pres().heygen_avatar_id = e.target.value.trim() || null; markDirty(); };
  $('#a_par').onchange = e => { raw.parallel = parseInt(e.target.value, 10) || 0; markDirty(); };
  $('#a_ss').onchange = e => { const v = parseInt(e.target.value, 10); if (v >= 1) raw.supersample = v; else delete raw.supersample; markDirty(); };
  $('#a_motion').onchange = e => { raw.motion_amount = parseFloat(e.target.value) || 0.15; markDirty(); };
  $('#a_size').onchange = e => { const [w, h] = e.target.value.split('x').map(Number); raw.width = w; raw.height = h; markDirty(); };
  $('#a_fps').onchange = e => { raw.fps = parseInt(e.target.value, 10); markDirty(); };
  renderResult(); poll();
}
async function poll() {
  clearTimeout(pollTimer);
  if (step !== 4) return;
  const st = await api('/api/build/status').catch(() => null); if (!st) return;
  const pill = $('#buildState'); if (!pill) return;
  pill.textContent = { idle: '空闲', running: '渲染中', done: '完成', error: '失败', cancelled: '已停止' }[st.state];
  pill.className = 'pill ' + ({ running: 'run', done: 'ok', error: 'err', cancelled: 'warn' }[st.state] || '');
  $('#buildBtn').disabled = st.state === 'running'; $('#cancelBtn').hidden = st.state !== 'running';
  $('#elapsed').textContent = st.started ? `${Math.round(st.elapsed)} s` : '';
  const pr = $('#progress'); if (pr) {
    pr.hidden = !(st.state === 'running' || st.state === 'done');
    $('#bar').style.width = `${st.progress || 0}%`;
    const ph = { tts: '配音', assets: '取素材', remotion: '动画', render: '渲染', assemble: '合成' }[st.phase] || '';
    $('#ptext').textContent = st.state === 'running' ? `${st.progress || 0}% · ${ph}${st.segments_total ? ` ${st.segments_done}/${st.segments_total} 段` : ''}${st.eta ? ` · 预计还需 ${fmt(st.eta)}` : ''}` : (st.state === 'done' ? '完成' : '');
  }
  if (st.lines.length) { $('#log').hidden = false; $('#log').innerHTML = st.lines.map(logLine).join('\n'); $('#log').scrollTop = 1e9; }
  if (st.state === 'running') pollTimer = setTimeout(poll, 1000);
  else if (st.finished && Date.now() / 1000 - st.finished < 4 && !poll.reloaded) { poll.reloaded = true; await load(); setTimeout(() => poll.reloaded = false, 5000); }
}
/* colour + Chinese label per log line; the raw English stays for grep/bug reports */
function logLine(l) {
  const t = esc(l.replace(/^\[vidforge\] /, ''));
  if (/^ERROR/.test(l) || /ERROR:/.test(l)) return `<span class="lg-err">✖ ${t}</span>`;
  if (/warning:/.test(l)) return `<span class="lg-warn">⚠ ${t}</span>`;
  if (/^\[vidforge\]\s+tts /.test(l)) return `<span class="lg-dim">🎙 配音 ${t.replace(/^tts\s+/, '')}</span>`;
  if (/^\[vidforge\]\s+asset /.test(l)) return `<span class="lg-dim">🖼 素材 ${t.replace(/^asset\s+/, '')}</span>`;
  if (/\[remotion\]/.test(l)) return `<span class="lg-dim">✨ 动画 ${t.replace('[remotion] ', '')}</span>`;
  if (/^\[vidforge\]\s+clip /.test(l)) return `<span class="lg-ok">🎬 段完成 ${t.replace(/^clip\s+/, '')}</span>`;
  if (/^\[vidforge\] rendering /.test(l)) return `<span>⚙ ${t.replace('rendering', '并行渲染').replace('segments with', '段，').replace('worker(s)', '个线程')}</span>`;
  if (/^\[vidforge\] done in/.test(l)) return `<span class="lg-ok"><b>✔ 完成 ${t.replace('done in', '用时').replace('video', '视频')}</b></span>`;
  if (/ segments · tts /.test(l)) return `<span><b>▶ ${t.replace('segments', '段').replace('tts', '配音').replace('voice', '声音')}</b>（最后一项是实际编码器）</span>`;
  if (/^\[vidforge\] chapters:/.test(l)) return `<span class="lg-dim">📑 章节：</span>`;
  return `<span class="lg-dim">${t}</span>`;
}
function renderResult() {
  const o = P.outputs; if (!o.final) return;
  const v = $('#player'); const src = fileUrl(o.final, o.final_mtime);
  if (v.dataset.src !== src) { v.src = src; v.dataset.src = src; }
  $('#dlVideo').href = fileUrl(o.final); $('#dlSrt').href = fileUrl(o.srt) || '#'; $('#dlThumb').href = fileUrl(o.thumbnail) || '#';
  $('#thumbImg').src = fileUrl(o.thumbnail, o.final_mtime) || '';
  $('#chapters').textContent = chaptersText(o.timeline);
  const total = o.timeline?.length ? o.timeline[o.timeline.length - 1].end : 0;
  $('#resultMeta').textContent = `${lang} · ${fmt(total)} · ${new Date(o.final_mtime * 1000).toLocaleString()}`;
  $('#buildPath').textContent = `${P.root}\\${P.build_dir.replace(/\//g, '\\')}`;
}
function chaptersText(tl) { return (tl || []).map(t => { const s = Math.floor(t.start); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} ${t.label || t.id}`; }).join('\n'); }

/* ---------------- 5 publish ---------------- */
function viewPublish(v) {
  const o = P.outputs, yt = o.youtube;
  v.innerHTML = `
  <div class="card">
    <div class="grid2">
      <div><label class="muted">YouTube 标题（默认用视频标题）</label><input id="y_title" value="${esc(nestedGet('youtube', 'title') || '')}" placeholder="${esc(topGet('title') || '')}"></div>
      <div><label class="muted">标签（逗号分隔）</label><input id="y_tags" value="${esc((nestedGet('youtube', 'tags') || []).join(', '))}"></div>
      <div><label class="muted">可见性</label><select id="y_priv">${['private', 'unlisted', 'public'].map(p => `<option ${(nestedGet('youtube', 'privacy') || 'private') === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
      <div><label class="muted">分类</label><select id="y_cat">${[[27, 'Education'], [28, 'Science & Technology'], [22, 'People & Blogs'], [24, 'Entertainment'], [25, 'News & Politics']].map(([n, l]) => `<option value="${n}" ${(nestedGet('youtube', 'category_id') || 27) == n ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    </div>
    <div class="row" style="margin:8px 0"><b style="font-size:12px">AI 使用声明</b>
      <label><input type="checkbox" id="d_voice" ${(nestedGet('youtube', 'disclosure')?.ai_voice ?? true) ? 'checked' : ''}> AI 配音</label>
      <label><input type="checkbox" id="d_vis" ${nestedGet('youtube', 'disclosure')?.ai_visuals ? 'checked' : ''}> AI 生成画面</label>
      <label><input type="checkbox" id="d_real" ${nestedGet('youtube', 'disclosure')?.realistic_presenter || raw.presenter?.provider === 'heygen' ? 'checked' : ''} ${raw.presenter?.provider === 'heygen' ? 'disabled' : ''}> 逼真合成主持人/换脸</label>
      <span class="muted" id="d_hint"></span></div>
    <label class="muted">简介（章节、素材署名和 AI 声明会自动追加在后面）</label>
    <textarea id="y_desc" rows="6">${esc(nestedGet('youtube', 'description') || '')}</textarea>
    <details><summary>将自动追加的内容</summary><pre class="chapters">${esc(chaptersText(o.timeline))}\n\n${esc(o.credits || '')}</pre></details>
    <div class="row" style="margin-top:8px">
      <button class="primary" id="uploadBtn" ${o.final ? '' : 'disabled'}>⬆ 上传到 YouTube（${nestedGet('youtube', 'privacy') || 'private'}）</button>
      ${yt?.url ? `<span class="ok">已上传：<a href="${esc(yt.url)}" target="_blank">${esc(yt.url)}</a>（再点会更新元数据）</span>` : ''}
      <span class="muted">${o.final ? '' : '先完成第 4 步渲染'}</span>
    </div>
    <p class="hint">未通过 Google 审核的应用上传的视频会被锁为私有——先私有上传，在 YouTube Studio 里检查后再公开/定时。每天约 5 条配额。首次需要 <code>~/.vidforge/client_secret.json</code>（见 QUICKSTART 第 6 步）。头条/西瓜没有上传接口：用第 4 步的 final.mp4 + thumbnail.jpg 手动发；中文版在右上角切换语言后重新渲染。</p>
    <pre class="log" id="ulog" hidden></pre>
  </div>`;
  $('#y_title').oninput = e => nestedSet('youtube', 'title', e.target.value || null);
  $('#y_tags').oninput = e => nestedSet('youtube', 'tags', e.target.value.split(',').map(s => s.trim()).filter(Boolean));
  $('#y_priv').onchange = e => nestedSet('youtube', 'privacy', e.target.value);
  $('#y_cat').onchange = e => nestedSet('youtube', 'category_id', +e.target.value);
  $('#y_desc').oninput = e => nestedSet('youtube', 'description', e.target.value);
  const disc = () => { const y = isBase() ? (raw.youtube = raw.youtube || {}) : (variant().youtube = variant().youtube || {}); y.disclosure = y.disclosure || { ai_voice: true }; return y.disclosure; };
  const dHint = () => { const d = nestedGet('youtube', 'disclosure') || { ai_voice: true }; const flag = d.realistic_presenter || d.ai_visuals || raw.presenter?.provider === 'heygen'; $('#d_hint').textContent = flag ? 'YouTube「合成内容」标签：会自动勾选（含逼真合成人物/画面）。' : 'YouTube「合成内容」标签：不需要（纯 AI 配音的解说不在披露范围）。国内平台：简介会附"本视频包含人工智能生成内容"。'; };
  dHint();
  $('#d_voice').onchange = e => { disc().ai_voice = e.target.checked; markDirty(); dHint(); };
  $('#d_vis').onchange = e => { disc().ai_visuals = e.target.checked; markDirty(); dHint(); };
  $('#d_real').onchange = e => { disc().realistic_presenter = e.target.checked; markDirty(); dHint(); };
  $('#uploadBtn').onclick = async () => {
    if (!await save()) return;
    $('#ulog').hidden = false; $('#ulog').textContent = '上传中…（第一次会打开浏览器要求授权）';
    try { const j = await api(`/api/upload?lang=${lang}`, {}); $('#ulog').textContent = (j.lines || []).join('\n'); await load(); }
    catch (e) { $('#ulog').textContent = 'ERROR: ' + e.message; }
  };
}

load();
